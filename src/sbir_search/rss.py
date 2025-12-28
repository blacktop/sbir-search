from __future__ import annotations

import re
from typing import Any

import feedparser
import httpx

from .config import AppConfig
from .models import Opportunity


def fetch_rss_opportunities(config: AppConfig) -> list[Opportunity]:
    opportunities: list[Opportunity] = []

    for feed_url in config.rss.feed_urls:
        feed = _fetch_feed(feed_url, config)
        for entry in feed.entries:
            opportunity = _to_opportunity(entry)
            if opportunity:
                opportunities.append(opportunity)

    return opportunities


def _fetch_feed(feed_url: str, config: AppConfig) -> feedparser.FeedParserDict:
    headers = {"User-Agent": config.user_agent}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        resp = client.get(feed_url)
        resp.raise_for_status()
        content = resp.text

    feed = feedparser.parse(content)
    if feed.bozo and not feed.entries:
        sanitized = _sanitize_xml(content)
        feed = feedparser.parse(sanitized)
        if feed.bozo and not feed.entries:
            raise RuntimeError(f"Feed parse error: {feed.bozo_exception}")
    return feed


def _to_opportunity(entry: feedparser.FeedParserDict) -> Opportunity | None:
    title = _to_str(entry.get("title"))
    if not title:
        return None

    link = _to_str(entry.get("link"))
    description = _clean_html(_to_str(entry.get("description") or entry.get("summary")))
    pub_date = _to_str(entry.get("published") or entry.get("updated"))
    guid = _to_str(entry.get("id") or entry.get("guid"))
    category = _to_str(_extract_category(entry))

    identifier = guid or link or f"{title}:{pub_date or ''}"
    identifier = f"rss::{identifier}"

    return Opportunity(
        id=identifier,
        source="grants_rss",
        solicitation_title=title,
        solicitation_number=None,
        agency=category,
        branch=None,
        open_date=pub_date,
        close_date=None,
        topic_title=None,
        topic_number=None,
        topic_description=description,
        subtopic_title=None,
        subtopic_description=None,
        url=link,
        raw=dict(entry),
    )


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None


def _clean_html(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"<[^>]+>", " ", value).strip() or None


def _extract_category(entry: feedparser.FeedParserDict) -> str | None:
    tags = entry.get("tags") or []
    if isinstance(tags, list) and tags:
        tag = tags[0]
        if isinstance(tag, dict):
            return _to_str(tag.get("term"))
        return _to_str(tag)
    return None


def _sanitize_xml(content: str) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", content)
    return re.sub(
        r"&(?![a-zA-Z]{2,6};|#\d{2,5};|#x[0-9a-fA-F]{2,5};)",
        "&amp;",
        cleaned,
    )
