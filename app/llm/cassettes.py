"""Record/replay cassettes — deterministic, $0, offline (CLAUDE.md rule 4).

A cassette stores one LLM exchange keyed by sha256({model, messages}). The same key()
is the single source of truth for both the router and any offline author script.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

Messages = list[dict[str, Any]]


def cassette_key(model: str, messages: Messages) -> str:
    canonical = json.dumps(
        {"model": model, "messages": messages}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _path(cassettes_dir: Path, key: str) -> Path:
    return cassettes_dir / f"{key}.json"


def load(cassettes_dir: Path, key: str) -> dict[str, Any] | None:
    """Return the stored response payload for key, or None if no cassette exists."""
    path = _path(cassettes_dir, key)
    if not path.exists():
        return None
    return json.loads(path.read_text())["response"]


def save(
    cassettes_dir: Path, key: str, model: str, messages: Messages, response: dict[str, Any]
) -> None:
    cassettes_dir.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "messages": messages, "response": response}
    _path(cassettes_dir, key).write_text(json.dumps(payload, indent=2, sort_keys=True))
