from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig, config_path, load_config
from .matcher import match_opportunities
from .notify import notify, notify_test
from .sources import collect_opportunities
from .state import State, load_state, save_state


@dataclass(slots=True)
class RunSummary:
    total_opportunities: int
    matched: int
    new_matches: int
    skipped: int
    sources: list[str]
    errors: list[str]
    evaluations: list[tuple[str, dict]]


def main() -> None:
    parser = argparse.ArgumentParser(prog="sbir-search", description="SBIR opportunity crawler")
    parser.add_argument("--config", help="Path to config.toml")
    parser.add_argument("--dry-run", action="store_true", help="Print matches to stdout")
    parser.add_argument("--explain", action="store_true", help="Explain match decisions")
    parser.add_argument(
        "--test-discord",
        nargs="?",
        const="sbir-search test message",
        help="Send a test Discord message (optionally provide custom text)",
    )
    args = parser.parse_args()

    cfg_path = config_path(args.config)
    config = load_config(cfg_path)
    if args.dry_run:
        config.notify.dry_run = True

    if args.test_discord is not None:
        notify_test(config, args.test_discord)
        print("Discord test message sent.")
        return

    summary = run(config, explain=args.explain)
    if summary.errors and config.show_warnings:
        print("Warnings:", file=sys.stderr)
        for error in summary.errors:
            print(f"- {error}", file=sys.stderr)

    if summary.evaluations:
        for _, payload in summary.evaluations:
            print(json.dumps(payload, indent=2))

    print(
        "SBIR crawl complete: "
        f"opportunities={summary.total_opportunities} "
        f"matches={summary.matched} "
        f"new={summary.new_matches} "
        f"skipped={summary.skipped} "
        f"sources={','.join(summary.sources)}"
    )


def run(config: AppConfig, explain: bool = False) -> RunSummary:
    opportunities, reports, errors = collect_opportunities(config)

    state_path = Path(config.match.state_path)
    state = load_state(state_path)

    match_result = match_opportunities(opportunities, config)
    new_matches = _filter_new(match_result.matches, state)

    if new_matches:
        notify(new_matches, config)
        _remember(state, new_matches)
        save_state(state_path, state)

    evaluations = []
    if explain:
        evaluations = _explain(match_result.evaluations)

    return RunSummary(
        total_opportunities=len(opportunities),
        matched=len(match_result.matches),
        new_matches=len(new_matches),
        skipped=match_result.skipped,
        sources=[f"{report.name}:{report.count}" for report in reports],
        errors=errors,
        evaluations=evaluations,
    )


def _filter_new(matches, state: State):
    return [match for match in matches if match.opportunity.id not in state.seen_ids]


def _remember(state: State, matches) -> None:
    for match in matches:
        state.seen_ids.add(match.opportunity.id)


def _explain(evaluations):
    results = []
    for evaluation in evaluations:
        opp = evaluation.opportunity
        payload = {
            "id": opp.id,
            "source": opp.source,
            "title": opp.topic_title or opp.solicitation_title,
            "agency": opp.agency,
            "open_date": opp.open_date,
            "close_date": opp.close_date,
            "score": evaluation.score,
            "matched_keywords": evaluation.matched_keywords,
            "reason": evaluation.reason or "matched",
            "url": opp.url,
        }
        results.append((opp.id, payload))
    return results


if __name__ == "__main__":
    main()
