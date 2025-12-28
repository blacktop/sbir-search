from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import feedparser
import httpx

from .config import AppConfig
from .models import Opportunity


@dataclass(slots=True)
class NihEntry:
    title: str
    link: str
    summary: str | None
    published: str | None
    entry_id: str | None


def fetch_nih_guide_opportunities(config: AppConfig) -> list[Opportunity]:
    feed = _fetch_feed(config.nih.feed_url, config)
    opportunities: list[Opportunity] = []

    for entry in feed.entries:
        item = _to_entry(entry)
        if not item:
            continue
        if not _matches_required_terms(item, config.nih.required_terms):
            continue
        identifier = item.entry_id or item.link or f"{item.title}:{item.published or ''}"
        opportunities.append(
            Opportunity(
                id=f"nih_guide::{identifier}",
                source="nih_guide",
                solicitation_title=item.title,
                solicitation_number=None,
                agency="HHS",
                branch="NIH/CDC",
                open_date=item.published,
                close_date=None,
                topic_title=None,
                topic_number=None,
                topic_description=item.summary,
                subtopic_title=None,
                subtopic_description=None,
                url=item.link,
                raw=dict(entry),
            )
        )

    return opportunities


def _fetch_feed(feed_url: str, config: AppConfig) -> feedparser.FeedParserDict:
    headers = {"User-Agent": config.user_agent}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        resp = client.get(feed_url)
        resp.raise_for_status()
        content = resp.text

    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Feed parse error: {feed.bozo_exception}")
    return feed


def _to_entry(entry: feedparser.FeedParserDict) -> NihEntry | None:
    title = _to_str(entry.get("title"))
    link = _to_str(entry.get("link"))
    if not title or not link:
        return None
    summary = _to_str(entry.get("summary") or entry.get("description"))
    published = _to_str(entry.get("published") or entry.get("updated"))
    entry_id = _to_str(entry.get("id") or entry.get("guid"))
    return NihEntry(title=title, link=link, summary=summary, published=published, entry_id=entry_id)


def _matches_required_terms(entry: NihEntry, terms: list[str]) -> bool:
    if not terms:
        return True
    text = " ".join(filter(None, [entry.title, entry.summary])).lower()
    return any(term.lower() in text for term in terms)


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None
