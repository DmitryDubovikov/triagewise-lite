"""Promotion-turn log — the gate's persistent trail (iter 7).

Append-only JSONL next to the SLO log (app/llm/slo.py), same posture: one record per gate
turn from either transport (`make promote` / a Prefect tick), jq-friendly (rule 9). A log,
not a registry: the alias truth stays in MLflow (rule 8) — this file only remembers what the
gate decided and when, so the read-only dashboard can show the last verdict without
re-running anything.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from app.config import Settings
from app.persistence.jsonl import iter_records


class PromotionRecord(BaseModel):
    ts: str
    champion_version: int
    champion_score: float
    challenger_version: int
    challenger_score: float
    promoted: bool
    champion_version_after: int  # fresh store read after the (possible) swap, rule 8
    golden_count: int
    mode: str  # replay | record | live


def log_promotion(record: PromotionRecord, settings: Settings) -> None:
    """Append one gate-turn record to the promotion log."""
    settings.promotion_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.promotion_log_path.open("a") as f:
        f.write(record.model_dump_json() + "\n")


def last_promotion(path: Path) -> PromotionRecord | None:
    """The most recent valid record, or None (no log yet / nothing parseable).

    Tolerant read (iter_records): a torn or foreign line is skipped, not fatal — the
    dashboard degrades to the newest record it can still parse."""
    latest: PromotionRecord | None = None
    for record in iter_records(path, PromotionRecord):
        latest = record
    return latest
