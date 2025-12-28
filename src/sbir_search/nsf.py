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


def fetch_nsf_seedfund_opportunities(config: AppConfig) -> list[Opportunity]:
    headers = {"User-Agent": config.user_agent}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        resp = client.get(config.nsf.solicitations_url)
        resp.raise_for_status()
        html = resp.text

    lines = _parse_lines(html)
    section = _slice_solicitations(lines)

    opportunities: list[Opportunity] = []
    for line in section:
        title = line.text.strip()
        if not title or not line.hrefs:
            continue
        if not _is_relevant_title(title):
            continue
        href = _pick_url(line.hrefs)
        if not _is_solicitation_link(href):
            continue
        url = _normalize_url(config.nsf.solicitations_url, href)
        identifier = f"nsf_seedfund::{href or title}"

        opportunities.append(
            Opportunity(
                id=identifier,
                source="nsf_seedfund",
                solicitation_title=title,
                solicitation_number=None,
                agency="NSF",
                branch=None,
                open_date=None,
                close_date=None,
                topic_title=None,
                topic_number=None,
                topic_description=None,
                subtopic_title=None,
                subtopic_description=None,
                url=url,
                raw={"title": title, "href": href},
            )
        )

    return opportunities


def _parse_lines(html: str) -> list[ParsedLine]:
    parser = _LineParser()
    parser.feed(html)
    parser.close()
    return parser.lines


def _slice_solicitations(lines: list[ParsedLine]) -> list[ParsedLine]:
    start = None
    end = None
    for idx, line in enumerate(lines):
        text = line.text.strip().lower()
        if start is None and text == "solicitations":
            start = idx + 1
            continue
        if start is not None and text in {"return to top", "america's seed fund"}:
            end = idx
            break
    if start is None:
        return lines
    return lines[start:end] if end is not None else lines[start:]


def _is_relevant_title(title: str) -> bool:
    lower = title.lower()
    return any(token in lower for token in ("sbir", "sttr", "solicitation"))


def _is_solicitation_link(href: str | None) -> bool:
    if not href:
        return False
    return "solicitation" in href.lower()


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
