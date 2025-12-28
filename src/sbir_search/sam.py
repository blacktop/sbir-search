from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .config import AppConfig
from .models import Opportunity


@dataclass(slots=True)
class SamResponse:
    records: list[dict]


def fetch_sam_opportunities(config: AppConfig) -> list[Opportunity]:
    if not config.sam.api_key:
        raise RuntimeError("SAM.gov API key not configured (set SAM_API_KEY)")

    records = _fetch_sam_records(config)
    opportunities: list[Opportunity] = []
    for record in records:
        opportunity = _to_opportunity(record)
        if opportunity:
            opportunities.append(opportunity)
    return opportunities


def _fetch_sam_records(config: AppConfig) -> list[dict]:
    params = _build_params(config)
    offset = 0
    pages = 0
    records: list[dict] = []

    while pages < config.sam.max_pages:
        params["offset"] = offset
        response = _fetch_page(config.sam.base_url, params, config)
        if not response.records:
            break

        records.extend(response.records)
        if len(response.records) < config.sam.limit:
            break

        offset += config.sam.limit
        pages += 1

    return records


def _build_params(config: AppConfig) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    posted_to = now.strftime("%m/%d/%Y")
    # SAM.gov API requires date range <= 1 year
    days = min(config.sam.posted_days, 364)
    posted_from = (now - timedelta(days=days)).strftime("%m/%d/%Y")

    params: dict[str, Any] = {
        "api_key": config.sam.api_key,
        "postedFrom": posted_from,
        "postedTo": posted_to,
        "limit": config.sam.limit,
    }
    if config.sam.title_query:
        params["title"] = config.sam.title_query
    if config.sam.ptype:
        params["ptype"] = config.sam.ptype
    return params


def _fetch_page(base_url: str, params: dict[str, Any], config: AppConfig) -> SamResponse:
    headers = {"User-Agent": config.user_agent}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        resp = client.get(base_url, params=params)
        resp.raise_for_status()
        data = resp.json()
    records = _extract_records(data)
    return SamResponse(records=records)


def _extract_records(data: Any) -> list[dict]:
    if isinstance(data, dict):
        for key in ("opportunitiesData", "opportunities", "data", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _to_opportunity(record: dict[str, Any]) -> Opportunity | None:
    title = _to_str(record.get("title"))
    if not title:
        return None

    notice_id = _to_str(record.get("noticeId") or record.get("noticeID"))
    solicitation_number = _to_str(record.get("solicitationNumber"))
    agency = _to_str(record.get("fullParentPathName") or record.get("department"))
    branch = _to_str(record.get("office") or record.get("subTier"))
    open_date = _to_str(record.get("postedDate"))
    close_date = _to_str(
        record.get("responseDeadLine")
        or record.get("reponseDeadLine")
        or record.get("responseDeadline")
    )

    url = _to_str(
        record.get("uiLink") or record.get("additionalInfoLink") or record.get("description")
    )

    topic_description = _build_description(record)

    identifier = notice_id or solicitation_number or f"{title}:{open_date or ''}"
    identifier = f"sam::{identifier}"

    return Opportunity(
        id=identifier,
        source="sam",
        solicitation_title=title,
        solicitation_number=solicitation_number,
        agency=agency,
        branch=branch,
        open_date=open_date,
        close_date=close_date,
        topic_title=None,
        topic_number=None,
        topic_description=topic_description,
        subtopic_title=None,
        subtopic_description=None,
        url=url,
        raw=record,
    )


def _build_description(record: dict[str, Any]) -> str | None:
    parts = []
    for key in ("type", "setAside", "naicsCode", "classificationCode"):
        value = _to_str(record.get(key))
        if value:
            parts.append(f"{key}:{value}")
    return " ".join(parts) or None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value).strip() or None
