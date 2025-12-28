from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from .config import AppConfig
from .models import Opportunity


@dataclass(slots=True)
class ApiResponse:
    records: list[dict]
    source_url: str


def fetch_solicitations(config: AppConfig) -> list[dict]:
    base_url = _select_base_url(config)
    rows = max(1, min(config.match.rows, 50))
    start = 0
    pages = 0
    records: list[dict] = []

    while pages < config.match.max_pages:
        params: dict[str, Any] = {"rows": rows, "start": start}
        if config.match.open_only:
            params["open"] = 1

        response = _fetch_page(base_url, params, config)
        if not response.records:
            break

        records.extend(response.records)
        if len(response.records) < rows:
            break

        start += rows
        pages += 1

    return records


def _select_base_url(config: AppConfig) -> str:
    errors: list[str] = []
    for base_url in config.match.api_base_urls:
        try:
            _fetch_page(base_url, {"rows": 1, "start": 0, "open": 1}, config)
            return base_url
        except Exception as exc:  # pragma: no cover - best effort
            errors.append(f"{base_url}: {exc}")
    if errors:
        raise RuntimeError(
            "SBIR API base URLs failed. "
            "Check api_base_urls in config.toml or SBIR.gov API status. "
            f"Errors: {errors}"
        )
    raise RuntimeError("No SBIR API base URL configured")


def _fetch_page(base_url: str, params: dict[str, Any], config: AppConfig) -> ApiResponse:
    headers = {"User-Agent": config.user_agent}
    retries = max(0, config.match.retry_max)
    backoff = max(0.1, config.match.retry_backoff_seconds)
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=30.0, headers=headers) as client:
                resp = client.get(base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            records = _extract_records(data)
            return ApiResponse(records=records, source_url=str(resp.url))
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status = exc.response.status_code
            if status in {429, 500, 502, 503, 504} and attempt < retries:
                # Use longer delay for rate limits
                delay = backoff * (2**attempt)
                if status == 429:
                    delay = max(delay, 10.0)  # At least 10s for rate limits
                time.sleep(delay)
                continue
            raise
        except httpx.RequestError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff * (2**attempt))
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("SBIR API request failed")


def _extract_records(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("solicitations", "results", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def iter_opportunities(solicitation: dict[str, Any]) -> Iterable[Opportunity]:
    topics = solicitation.get("solicitation_topics") or []
    if not isinstance(topics, list):
        topics = []

    base_kwargs = _base_fields(solicitation)
    if not topics:
        yield Opportunity(
            **base_kwargs,
            source="sbir",
            topic_title=None,
            topic_number=None,
            topic_description=None,
            subtopic_title=None,
            subtopic_description=None,
            url=_best_url(solicitation, None, None),
            raw=solicitation,
            id=_build_id(base_kwargs.get("solicitation_number"), None, None),
        )
        return

    for topic in topics:
        if not isinstance(topic, dict):
            continue
        subtopics = topic.get("subtopics") or []
        if not isinstance(subtopics, list):
            subtopics = []

        if not subtopics:
            yield _opportunity_from_topic(base_kwargs, solicitation, topic, None)
            continue

        for subtopic in subtopics:
            if not isinstance(subtopic, dict):
                continue
            yield _opportunity_from_topic(base_kwargs, solicitation, topic, subtopic)


def _opportunity_from_topic(
    base_kwargs: dict[str, Any],
    solicitation: dict[str, Any],
    topic: dict[str, Any],
    subtopic: dict[str, Any] | None,
) -> Opportunity:
    topic_title = _to_str(topic.get("topic_title"))
    topic_number = _to_str(topic.get("topic_number"))
    topic_description = _to_str(topic.get("topic_description"))
    subtopic_title = _to_str(subtopic.get("subtopic_title")) if subtopic else None
    subtopic_description = _to_str(subtopic.get("subtopic_description")) if subtopic else None
    url = _best_url(solicitation, topic, subtopic)
    identifier = _build_id(base_kwargs.get("solicitation_number"), topic_number, subtopic_title)

    return Opportunity(
        **base_kwargs,
        source="sbir",
        topic_title=topic_title,
        topic_number=topic_number,
        topic_description=topic_description,
        subtopic_title=subtopic_title,
        subtopic_description=subtopic_description,
        url=url,
        raw={"solicitation": solicitation, "topic": topic, "subtopic": subtopic},
        id=identifier,
    )


def _base_fields(solicitation: dict[str, Any]) -> dict[str, Any]:
    return {
        "solicitation_title": _to_str(solicitation.get("solicitation_title")) or "",
        "solicitation_number": _to_str(solicitation.get("solicitation_number")),
        "agency": _to_str(solicitation.get("agency")),
        "branch": _to_str(solicitation.get("branch")),
        "open_date": _to_str(solicitation.get("open_date")),
        "close_date": _to_str(solicitation.get("close_date")),
    }


def _best_url(
    solicitation: dict[str, Any],
    topic: dict[str, Any] | None,
    subtopic: dict[str, Any] | None,
) -> str | None:
    for source in (subtopic, topic, solicitation):
        if not source:
            continue
        for key in (
            "sbir_subtopic_link",
            "sbir_topic_link",
            "sbir_solicitation_link",
            "solicitation_agency_url",
        ):
            value = _to_str(source.get(key))
            if value:
                return value
    return None


def _build_id(
    solicitation_number: str | None,
    topic_number: str | None,
    subtopic_title: str | None,
) -> str:
    parts = [part for part in (solicitation_number, topic_number, subtopic_title) if part]
    return "::".join(parts) if parts else "unknown"


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None
