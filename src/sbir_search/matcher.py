from __future__ import annotations

import re
from dataclasses import dataclass

from .config import AppConfig
from .models import Match, Opportunity


@dataclass(slots=True)
class Evaluation:
    opportunity: Opportunity
    score: int
    matched_keywords: list[str]
    reason: str | None


@dataclass(slots=True)
class MatchResult:
    matches: list[Match]
    skipped: int
    evaluations: list[Evaluation]


def match_opportunities(opportunities: list[Opportunity], config: AppConfig) -> MatchResult:
    keywords = [kw.lower() for kw in config.match.keywords]
    excludes = [kw.lower() for kw in config.match.exclude_keywords]
    always_include = {source.lower() for source in config.match.always_include_sources}

    compiled = [_compile_keyword(kw) for kw in keywords]
    compiled_excludes = [_compile_keyword(kw) for kw in excludes]

    matches: list[Match] = []
    evaluations: list[Evaluation] = []
    skipped = 0

    for opportunity in opportunities:
        source = (opportunity.source or "").lower()
        whitelisted = source in always_include
        if (
            config.match.agencies
            and (opportunity.agency or "").upper() not in config.match.agencies
        ):
            skipped += 1
            evaluations.append(
                Evaluation(
                    opportunity=opportunity,
                    score=0,
                    matched_keywords=[],
                    reason="agency_filtered",
                )
            )
            continue

        text = build_text(opportunity, config)
        if not text and not whitelisted:
            skipped += 1
            evaluations.append(
                Evaluation(
                    opportunity=opportunity,
                    score=0,
                    matched_keywords=[],
                    reason="no_text",
                )
            )
            continue

        excluded = _first_excluded(text, compiled_excludes, excludes) if text else None
        if excluded:
            skipped += 1
            evaluations.append(
                Evaluation(
                    opportunity=opportunity,
                    score=0,
                    matched_keywords=[],
                    reason=f"excluded_keyword:{excluded}",
                )
            )
            continue

        matched_keywords = (
            [kw for kw, pattern in zip(keywords, compiled, strict=False) if pattern.search(text)]
            if text
            else []
        )
        score = len(matched_keywords)
        if score < config.match.min_score and not whitelisted:
            skipped += 1
            evaluations.append(
                Evaluation(
                    opportunity=opportunity,
                    score=score,
                    matched_keywords=matched_keywords,
                    reason=f"score<{config.match.min_score}",
                )
            )
            continue

        matches.append(
            Match(
                opportunity=opportunity,
                score=score,
                matched_keywords=matched_keywords,
                matched_text=text or "",
            )
        )
        evaluations.append(
            Evaluation(
                opportunity=opportunity,
                score=score,
                matched_keywords=matched_keywords,
                reason=None if score >= config.match.min_score else "source_whitelist",
            )
        )

    return MatchResult(matches=matches, skipped=skipped, evaluations=evaluations)


def build_text(opportunity: Opportunity, config: AppConfig) -> str:
    fields: list[str] = []
    for field_name in config.match.match_fields:
        value = getattr(opportunity, field_name, None)
        if value:
            fields.append(value)
    return "\n".join(fields).lower()


def _compile_keyword(keyword: str) -> re.Pattern[str]:
    escaped = re.escape(keyword)
    if keyword.isalnum() and len(keyword) <= 3:
        return re.compile(rf"\\b{escaped}\\b", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def _first_excluded(text: str, patterns: list[re.Pattern[str]], keywords: list[str]) -> str | None:
    for kw, pattern in zip(keywords, patterns, strict=False):
        if pattern.search(text):
            return kw
    return None
