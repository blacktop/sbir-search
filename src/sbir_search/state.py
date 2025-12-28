from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class State:
    seen_ids: set[str] = field(default_factory=set)


def load_state(path: Path) -> State:
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return State()
    seen = set(data.get("seen_ids", [])) if isinstance(data, dict) else set()
    return State(seen_ids=seen)


def save_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen_ids": sorted(state.seen_ids)}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
