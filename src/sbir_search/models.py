from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Opportunity:
    id: str
    source: str | None
    solicitation_title: str
    solicitation_number: str | None
    agency: str | None
    branch: str | None
    open_date: str | None
    close_date: str | None
    topic_title: str | None
    topic_number: str | None
    topic_description: str | None
    subtopic_title: str | None
    subtopic_description: str | None
    url: str | None
    raw: dict


@dataclass(slots=True)
class Match:
    opportunity: Opportunity
    score: int
    matched_keywords: list[str]
    matched_text: str
