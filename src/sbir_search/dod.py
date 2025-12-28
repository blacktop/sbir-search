from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import httpx

from .config import AppConfig
from .models import Opportunity


@dataclass(slots=True)
class ParsedLine:
    text: str
    hrefs: list[str]


class _LineParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[ParsedLine] = []
        self._text_parts: list[str] = []
        self._hrefs: list[str] = []
        self._current_href: str | None = None
        self._block_tags = {
            "p",
            "div",
            "li",
            "ul",
            "ol",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "br",
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._block_tags:
            self._flush()
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value:
                    self._current_href = value
                    break

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._current_href = None
        if tag in self._block_tags:
            self._flush()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        self._text_parts.append(text)
        if self._current_href:
            self._hrefs.append(self._current_href)

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        if not self._text_parts:
            self._hrefs = []
            return
        text = " ".join(self._text_parts).strip()
        if text:
            hrefs = list(dict.fromkeys(self._hrefs))
            self.lines.append(ParsedLine(text=text, hrefs=hrefs))
        self._text_parts = []
        self._hrefs = []


def fetch_dod_darpa_opportunities(config: AppConfig) -> list[Opportunity]:
    headers = {"User-Agent": config.user_agent}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        resp = client.get(config.dod.darpa_topics_url)
        resp.raise_for_status()
        html = resp.text

    lines = _parse_lines(html)
    active_lines = _slice_active_section(lines)
    topics = _parse_topics(active_lines)

    opportunities: list[Opportunity] = []
    for topic in topics:
        identifier = f"dod_darpa::{topic.get('topic_number') or topic.get('title')}"
        opportunities.append(
            Opportunity(
                id=identifier,
                source="dod_darpa",
                solicitation_title=topic.get("program") or "DARPA SBIR/STTR",
                solicitation_number=None,
                agency="DOD",
                branch="DARPA",
                open_date=topic.get("open_date"),
                close_date=topic.get("close_date"),
                topic_title=topic.get("title"),
                topic_number=topic.get("topic_number"),
                topic_description=topic.get("objective"),
                subtopic_title=None,
                subtopic_description=None,
                url=_normalize_url(config.dod.darpa_topics_url, topic.get("url")),
                raw=topic,
            )
        )

    return opportunities


def _parse_lines(html: str) -> list[ParsedLine]:
    parser = _LineParser()
    parser.feed(html)
    parser.close()
    return parser.lines


def _slice_active_section(lines: list[ParsedLine]) -> list[ParsedLine]:
    start = None
    end = None
    for idx, line in enumerate(lines):
        text = line.text.strip().lower()
        if start is None and text == "active announcement topics":
            start = idx + 1
            continue
        if start is not None and text.startswith("closed announcement topics"):
            end = idx
            break
    if start is None:
        return lines
    return lines[start:end] if end is not None else lines[start:]


def _parse_topics(lines: list[ParsedLine]) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_program: str | None = None

    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        lower = text.lower()

        if lower.startswith("sbir |") or lower.startswith("sttr |") or lower.startswith("baa"):
            current_program = text
            continue
        if lower.startswith("each year") or lower.startswith("all sbir/sttr topics"):
            continue
        if lower in {"important", "active announcement topics"}:
            continue
        if lower in {"solicitation", "faqs", "faq"}:
            continue

        if lower.startswith("objective:") or lower.startswith("description:"):
            if current is not None:
                current["objective"] = text.split(":", 1)[1].strip()
            continue
        if lower.startswith("tech office:"):
            if current is not None:
                current["tech_office"] = text.split(":", 1)[1].strip()
            continue
        if lower.startswith("topic #:") or lower.startswith("topic #"):
            if current is not None:
                current["topic_number"] = text.split(":", 1)[1].strip()
            continue
        if lower.startswith("pre-release:"):
            if current is not None:
                current["pre_release"] = text.split(":", 1)[1].strip()
            continue
        if lower.startswith("open:"):
            if current is not None:
                current["open_date"] = text.split(":", 1)[1].strip()
            continue
        if (
            lower.startswith("closes:")
            or lower.startswith("closed:")
            or lower.startswith("deadline:")
        ):
            if current is not None:
                current["close_date"] = text.split(":", 1)[1].strip()
            continue

        if current is not None:
            topics.append(current)

        current = {
            "title": text,
            "program": current_program,
            "url": _pick_url(line.hrefs),
        }

    if current is not None:
        topics.append(current)

    return topics


def _pick_url(hrefs: list[str]) -> str | None:
    for href in hrefs:
        if href.startswith("http"):
            return href
    return hrefs[0] if hrefs else None


def _normalize_url(base: str, href: str | None) -> str:
    if not href:
        return base
    if href.startswith("http"):
        return href
    return urljoin(base, href)
