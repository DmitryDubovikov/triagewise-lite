"""Per-call SLO accounting for the access layer (LLM FinOps, iter 3).

Every route() call yields one CallRecord: tier, model, mode, latency, cost. check_slo() is a
pure threshold decision; log_call() appends the record to a JSONL file (the demonstrable
artifact, jq-friendly) and mirrors a human-readable line to the logger. A breach WARNs — it
never fails the call (existence-gate, not an enforcement gate).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.config import Settings

logger = logging.getLogger(__name__)

# Where cost_usd came from: a live completion_cost, a cassette recorded earlier, or unknown
# (hand-authored cassette without cost / pricing lookup failed) — then it's 0.0.
CostSource = Literal["live", "cassette", "none"]

# Semantic-cache outcome (iter 4): hit = served from cache (no cassette, no network),
# miss = went the normal route path and was stored, off = cache disabled or bypassed.
CacheState = Literal["hit", "miss", "off"]


class CallRecord(BaseModel):
    ts: str
    tier: str
    model: str
    mode: str  # replay | record | live
    latency_ms: float
    cost_usd: float
    cost_source: CostSource
    cache: CacheState
    slo_breaches: list[str] = Field(default_factory=list)


def check_slo(cost_usd: float, latency_ms: float, settings: Settings) -> list[str]:
    """Pure decision: which per-call SLO thresholds does this call breach?"""
    breaches = []
    if cost_usd > settings.slo_max_cost_usd:
        breaches.append(f"cost ${cost_usd:.6f} > ${settings.slo_max_cost_usd:.6f}")
    if latency_ms > settings.slo_max_latency_ms:
        breaches.append(f"latency {latency_ms:.0f}ms > {settings.slo_max_latency_ms:.0f}ms")
    return breaches


def log_call(
    *,
    tier: str,
    model: str,
    settings: Settings,
    latency_ms: float,
    cost_usd: float,
    cost_source: CostSource,
    cache: CacheState,
) -> None:
    """Build the per-call record, append it to the JSONL SLO log, mirror a line to the logger."""
    record = CallRecord(
        ts=datetime.now(UTC).isoformat(timespec="milliseconds"),
        tier=tier,
        model=model,
        mode=settings.llm_mode,
        latency_ms=round(latency_ms, 1),
        cost_usd=cost_usd,
        cost_source=cost_source,
        cache=cache,
        slo_breaches=check_slo(cost_usd, latency_ms, settings),
    )
    settings.llm_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.llm_log_path.open("a") as f:
        f.write(record.model_dump_json() + "\n")

    line = (
        f"[slo] {record.tier}->{record.model} ({record.mode}) "
        f"{record.latency_ms:.0f}ms ${record.cost_usd:.6f} ({record.cost_source})"
    )
    if record.cache != "off":
        line += f" cache={record.cache}"
    if record.slo_breaches:
        logger.warning("%s BREACH: %s", line, "; ".join(record.slo_breaches))
    else:
        logger.info("%s ok", line)
