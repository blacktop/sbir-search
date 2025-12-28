from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MatchConfig:
    keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    min_score: int = 1
    agencies: list[str] = field(default_factory=list)
    open_only: bool = True
    always_include_sources: list[str] = field(default_factory=list)
    match_fields: list[str] = field(
        default_factory=lambda: [
            "solicitation_title",
            "topic_title",
            "topic_description",
            "subtopic_title",
            "subtopic_description",
        ]
    )
    state_path: str = ".sbir-search/state.json"
    rows: int = 50
    max_pages: int = 40
    retry_max: int = 3
    retry_backoff_seconds: float = 2.0
    api_base_urls: list[str] = field(
        default_factory=lambda: [
            "https://api.www.sbir.gov/public/api/solicitations",
        ]
    )


@dataclass(slots=True)
class NotifyConfig:
    discord_webhook_url: str | None = None
    discord_bot_token: str | None = None
    discord_channel_id: str | None = None
    discord_client_enabled: bool = True
    dry_run: bool = False


@dataclass(slots=True)
class SamConfig:
    enabled: bool = False
    fallback_only: bool = True
    api_key: str | None = None
    title_query: str = "SBIR"
    posted_days: int = 365
    limit: int = 100
    max_pages: int = 5
    ptype: str | None = "o"
    base_url: str = "https://api.sam.gov/opportunities/v2/search"


@dataclass(slots=True)
class RssConfig:
    enabled: bool = True
    fallback_only: bool = True
    feed_urls: list[str] = field(
        default_factory=lambda: [
            "https://www.grants.gov/rss/GG_OppNewByAgency.xml",
            "https://www.grants.gov/rss/GG_OppNewByCategory.xml",
            "https://www.grants.gov/rss/GG_OppModByAgency.xml",
            "https://www.grants.gov/rss/GG_OppModByCategory.xml",
        ]
    )


@dataclass(slots=True)
class DodConfig:
    enabled: bool = True
    fallback_only: bool = True
    darpa_topics_url: str = (
        "https://www.darpa.mil/work-with-us/communities/small-business/sbir-sttr-topics"
    )


@dataclass(slots=True)
class NsfConfig:
    enabled: bool = True
    fallback_only: bool = True
    solicitations_url: str = "https://seedfund.nsf.gov/solicitations/"


@dataclass(slots=True)
class NihConfig:
    enabled: bool = True
    fallback_only: bool = True
    feed_url: str = "https://grants.nih.gov/grants/guide/newsfeed/fundingopps.xml"
    required_terms: list[str] = field(default_factory=lambda: ["sbir", "sttr", "small business"])


@dataclass(slots=True)
class AppConfig:
    match: MatchConfig = field(default_factory=MatchConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    sam: SamConfig = field(default_factory=SamConfig)
    rss: RssConfig = field(default_factory=RssConfig)
    dod: DodConfig = field(default_factory=DodConfig)
    nsf: NsfConfig = field(default_factory=NsfConfig)
    nih: NihConfig = field(default_factory=NihConfig)
    user_agent: str = "sbir-search/0.1"
    fail_on_no_results: bool = False
    show_warnings: bool = False


def _merge(default: Any, override: Any) -> Any:
    if isinstance(default, dict) and isinstance(override, dict):
        merged: dict[str, Any] = {**default}
        for key, value in override.items():
            merged[key] = _merge(default.get(key), value)
        return merged
    return override if override is not None else default


def _normalize_agencies(agencies: list[str]) -> list[str]:
    return [agency.upper() for agency in agencies]


def _normalize_sources(sources: list[str]) -> list[str]:
    return [source.lower() for source in sources]


def load_config(path: Path) -> AppConfig:
    data: dict[str, Any] = {}
    if path.exists():
        data = _read_toml(path)

    defaults = AppConfig()
    merged = _merge(_as_dict(defaults), data)

    match = MatchConfig(**merged.get("match", {}))
    notify = NotifyConfig(**merged.get("notify", {}))
    sam = SamConfig(**merged.get("sam", {}))
    rss = RssConfig(**merged.get("rss", {}))
    dod = DodConfig(**merged.get("dod", {}))
    nsf = NsfConfig(**merged.get("nsf", {}))
    nih = NihConfig(**merged.get("nih", {}))
    config = AppConfig(
        match=match,
        notify=notify,
        sam=sam,
        rss=rss,
        dod=dod,
        nsf=nsf,
        nih=nih,
        user_agent=merged.get("user_agent", "sbir-search/0.1"),
        fail_on_no_results=merged.get("fail_on_no_results", False),
        show_warnings=merged.get("show_warnings", False),
    )

    if env_webhook := os.getenv("DISCORD_WEBHOOK_URL"):
        config.notify.discord_webhook_url = env_webhook
    if env_bot_token := os.getenv("DISCORD_TOKEN"):
        token = env_bot_token.strip()
        if token.lower().startswith("bot "):
            token = token[4:].strip()
        config.notify.discord_bot_token = token
    if env_channel_id := os.getenv("DISCORD_CHANNEL_ID"):
        config.notify.discord_channel_id = env_channel_id
    if not config.notify.discord_channel_id:
        if env_channel := os.getenv("DISCORD_CHANNEL"):
            config.notify.discord_channel_id = env_channel
        if env_channel := os.getenv("DISCORD_ID"):
            config.notify.discord_channel_id = env_channel
    if env_sam := os.getenv("SAM_API_KEY"):
        config.sam.api_key = env_sam

    config.match.agencies = _normalize_agencies(config.match.agencies)
    config.match.always_include_sources = _normalize_sources(config.match.always_include_sources)
    return config


def config_path(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path).expanduser()
    if env_path := os.getenv("SBIR_SEARCH_CONFIG"):
        return Path(env_path).expanduser()
    return Path("config.toml")


def _read_toml(path: Path) -> dict[str, Any]:
    import tomllib

    with path.open("rb") as handle:
        return tomllib.load(handle)


def _as_dict(config: AppConfig) -> dict[str, Any]:
    return {
        "user_agent": config.user_agent,
        "match": {
            "keywords": config.match.keywords,
            "exclude_keywords": config.match.exclude_keywords,
            "min_score": config.match.min_score,
            "agencies": config.match.agencies,
            "open_only": config.match.open_only,
            "always_include_sources": config.match.always_include_sources,
            "match_fields": config.match.match_fields,
            "state_path": config.match.state_path,
            "rows": config.match.rows,
            "max_pages": config.match.max_pages,
            "retry_max": config.match.retry_max,
            "retry_backoff_seconds": config.match.retry_backoff_seconds,
            "api_base_urls": config.match.api_base_urls,
        },
        "notify": {
            "discord_webhook_url": config.notify.discord_webhook_url,
            "discord_bot_token": config.notify.discord_bot_token,
            "discord_channel_id": config.notify.discord_channel_id,
            "discord_client_enabled": config.notify.discord_client_enabled,
            "dry_run": config.notify.dry_run,
        },
        "sam": {
            "enabled": config.sam.enabled,
            "fallback_only": config.sam.fallback_only,
            "api_key": config.sam.api_key,
            "title_query": config.sam.title_query,
            "posted_days": config.sam.posted_days,
            "limit": config.sam.limit,
            "max_pages": config.sam.max_pages,
            "ptype": config.sam.ptype,
            "base_url": config.sam.base_url,
        },
        "rss": {
            "enabled": config.rss.enabled,
            "fallback_only": config.rss.fallback_only,
            "feed_urls": config.rss.feed_urls,
        },
        "dod": {
            "enabled": config.dod.enabled,
            "fallback_only": config.dod.fallback_only,
            "darpa_topics_url": config.dod.darpa_topics_url,
        },
        "nsf": {
            "enabled": config.nsf.enabled,
            "fallback_only": config.nsf.fallback_only,
            "solicitations_url": config.nsf.solicitations_url,
        },
        "nih": {
            "enabled": config.nih.enabled,
            "fallback_only": config.nih.fallback_only,
            "feed_url": config.nih.feed_url,
            "required_terms": config.nih.required_terms,
        },
        "fail_on_no_results": config.fail_on_no_results,
        "show_warnings": config.show_warnings,
    }
