"""Tier -> model resolution from llm-tiers.yaml, with the pin-gate enforced at load."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings

# Pin-gate: a model name must end in a dated snapshot (-YYYY-MM-DD), never a floating alias.
_SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")


@lru_cache
def load_tiers(path: Path | None = None) -> dict[str, str]:
    path = path or get_settings().tiers_path
    data = yaml.safe_load(path.read_text())
    tiers = (data or {}).get("tiers") or {}
    if not tiers:
        raise ValueError(f"No tiers defined in {path}")
    for tier, model in tiers.items():
        if not _SNAPSHOT_RE.search(model):
            raise ValueError(
                f"Tier '{tier}' -> '{model}' is not a dated snapshot (-YYYY-MM-DD); "
                "floating aliases drift silently and are forbidden (pin-gate)."
            )
    return dict(tiers)


def resolve_model(tier: str, path: Path | None = None) -> str:
    tiers = load_tiers(path)
    try:
        return tiers[tier]
    except KeyError:
        raise ValueError(f"Unknown tier '{tier}'; known: {sorted(tiers)}") from None
