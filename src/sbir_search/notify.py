from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx

from .config import AppConfig
from .models import Match


@dataclass(slots=True)
class NotifyResult:
    sent: int
    skipped: int


def notify(matches: list[Match], config: AppConfig) -> NotifyResult:
    if not matches:
        return NotifyResult(sent=0, skipped=0)
    if config.notify.dry_run:
        _print_matches(matches)
        return NotifyResult(sent=0, skipped=len(matches))

    payloads = _build_payloads(matches)
    sent = _send_payloads(payloads, config)
    return NotifyResult(sent=sent, skipped=0)


def notify_test(config: AppConfig, message: str) -> None:
    _send_payloads([{"content": message}], config)


def _build_payloads(matches: list[Match]) -> list[dict]:
    lines = ["**SBIR matches:**"]
    payloads: list[dict] = []
    length = len(lines[0])

    for match in matches:
        line = _format_match(match)
        if length + len(line) + 1 > 1800:
            payloads.append({"content": "\n".join(lines)})
            lines = ["**SBIR matches (cont.):**"]
            length = len(lines[0])
        lines.append(line)
        length += len(line) + 1

    if lines:
        payloads.append({"content": "\n".join(lines)})

    return payloads


def _format_match(match: Match) -> str:
    opp = match.opportunity
    source = opp.source or "sbir"
    title = opp.topic_title or opp.solicitation_title
    agency = opp.agency or ""
    close_date = opp.close_date or ""
    url = opp.url or ""
    keyword_list = ", ".join(match.matched_keywords)
    return (
        f"- [{source}] **{title}** ({agency}) close {close_date} "
        f"score {match.score} [{keyword_list}] {url}"
    ).strip()


def _post_discord_webhook(webhook_url: str, payload: dict) -> None:
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(webhook_url, json=payload)
        resp.raise_for_status()


def _post_discord_bot(token: str, channel_id: str, payload: dict) -> None:
    if payload.get("content") is None:
        return
    try:
        import discord  # type: ignore
    except Exception:
        _post_discord_bot_http(token, channel_id, payload)
        return

    if not _run_discord_send(discord, token, channel_id, payload["content"]):
        _post_discord_bot_http(token, channel_id, payload)


def _post_discord_bot_http(token: str, channel_id: str, payload: dict) -> None:
    headers = {"Authorization": f"Bot {token}"}
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    with httpx.Client(timeout=20.0, headers=headers) as client:
        resp = client.post(url, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"Discord API error {resp.status_code}: {resp.text}")


def _run_discord_send(discord_module, token: str, channel_id: str, content: str) -> bool:
    async def _send() -> None:
        intents = discord_module.Intents.none()
        client = discord_module.Client(intents=intents)

        @client.event
        async def on_ready():
            try:
                channel = client.get_channel(int(channel_id))
                if channel is None:
                    channel = await client.fetch_channel(int(channel_id))
                await channel.send(content)
            finally:
                await client.close()

        try:
            await client.start(token)
        except Exception:
            try:
                await client.close()
            except Exception:
                pass
            raise

    try:
        asyncio.run(_send())
        return True
    except Exception:
        return False


def _send_payloads(payloads: list[dict], config: AppConfig) -> int:
    if config.notify.discord_webhook_url:
        for payload in payloads:
            _post_discord_webhook(config.notify.discord_webhook_url, payload)
        return len(payloads)

    if config.notify.discord_bot_token and config.notify.discord_channel_id:
        if config.notify.discord_client_enabled:
            try:
                import discord  # type: ignore
            except Exception:
                pass
        for payload in payloads:
            _post_discord_bot(
                config.notify.discord_bot_token,
                config.notify.discord_channel_id,
                payload,
            )
        return len(payloads)

    raise RuntimeError(
        "Discord credentials not configured. Set DISCORD_WEBHOOK_URL or "
        "DISCORD_TOKEN + DISCORD_CHANNEL_ID."
    )


def _print_matches(matches: list[Match]) -> None:
    for match in matches:
        payload = {
            "title": match.opportunity.topic_title or match.opportunity.solicitation_title,
            "source": match.opportunity.source,
            "agency": match.opportunity.agency,
            "close_date": match.opportunity.close_date,
            "url": match.opportunity.url,
            "score": match.score,
            "keywords": match.matched_keywords,
        }
        print(json.dumps(payload, indent=2))
