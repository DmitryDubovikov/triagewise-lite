"""Read-only data sources for the control-plane dashboard (iter 7).

One function per card, each reading ONE store an earlier iteration writes: the MLflow prompt
registry (iter 1/6a), Phoenix spans (5a), the SLO log (3/4) and the Prefect API (6b); the
promotion-log card reads app/persistence/promotion_log directly. Handles and Settings come in
as arguments — opened at the dashboard boundary (rule 6). No source writes anything and none
calls an LLM: the panel renders the control plane, it is not part of it. Streamlit is
deliberately absent here (rendering lives in dashboard.py), so every source stays
plain-pytest testable; the Prefect read keeps its pure parse (parse_loop_status) split from
the httpx I/O for the same reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from app.config import LOOP_DEPLOYMENT, LOOP_FLOW, Settings
from app.domain.drift import CategoryDrift, category_drift
from app.llm.slo import CallRecord
from app.observability.phoenix import (
    BASELINE_BATCH,
    CANDIDATE_BATCH,
    batch_category_rows,
    fetch_triage_spans,
)
from app.persistence.jsonl import iter_records
from app.persistence.prompts import CHALLENGER, CHAMPION, load_triage_prompt

if TYPE_CHECKING:
    from mlflow import MlflowClient
    from phoenix.client import Client


class PromptAliasStatus(NamedTuple):
    alias: str
    version: int


def prompt_statuses(client: MlflowClient) -> list[PromptAliasStatus]:
    """Which version each lifecycle alias points at — fresh from the registry (rule 8)."""
    return [
        PromptAliasStatus(alias, load_triage_prompt(client, alias).version)
        for alias in (CHAMPION, CHALLENGER)
    ]


class DriftStatus(NamedTuple):
    report: CategoryDrift
    observations: int
    truncated: bool


def drift_status(client: Client, settings: Settings) -> DriftStatus | None:
    """The drift verdict over traced spans — None when no traffic carries batch+category yet."""
    spans, truncated = fetch_triage_spans(client, settings)
    rows = batch_category_rows(spans)
    if not rows:
        return None
    report = category_drift(rows, baseline=BASELINE_BATCH, candidate=CANDIDATE_BATCH)
    return DriftStatus(report=report, observations=len(rows), truncated=truncated)


class SloSummary(NamedTuple):
    calls: int
    total_cost_usd: float
    breached_calls: int  # calls that violated at least one SLO threshold
    cache_hits: int
    cache_misses: int
    last_call: CallRecord | None


def slo_summary(path: Path) -> SloSummary:
    """Aggregate the per-call SLO log (iter 3/4); unparseable lines are skipped (iter_records)."""
    calls = breaches = hits = misses = 0
    cost = 0.0
    last: CallRecord | None = None
    for record in iter_records(path, CallRecord):
        calls += 1
        cost += record.cost_usd
        breaches += bool(record.slo_breaches)
        hits += record.cache == "hit"
        misses += record.cache == "miss"
        last = record
    return SloSummary(calls, round(cost, 6), breaches, hits, misses, last)


class LoopStatus(NamedTuple):
    interval_seconds: float | None  # None = loop never registered on the server
    schedule_active: bool | None
    last_run_state: str | None  # COMPLETED / SCHEDULED / LATE / ...
    last_run_time: str | None


def parse_loop_status(deployment: dict[str, Any] | None, runs: list[dict[str, Any]]) -> LoopStatus:
    """Pure distillation of the two Prefect API answers into one card."""
    interval = active = None
    schedules = (deployment or {}).get("schedules") or []
    if schedules:
        interval = (schedules[0].get("schedule") or {}).get("interval")
        active = schedules[0].get("active")
    state = time = None
    if runs:
        state = (runs[0].get("state") or {}).get("type")
        time = runs[0].get("start_time") or runs[0].get("expected_start_time")
    return LoopStatus(interval, active, state, time)


def fetch_loop_status(settings: Settings) -> LoopStatus:
    """Deployment schedule + newest flow run over the plain Prefect REST API."""
    import httpx  # lazy at the seam, like every store client in this app

    deployment = None
    with httpx.Client(base_url=settings.prefect_api_url.rstrip("/"), timeout=5) as client:
        resp = client.get(f"/deployments/name/{LOOP_FLOW}/{LOOP_DEPLOYMENT}")
        if resp.status_code == 200:
            deployment = resp.json()
        elif resp.status_code != 404:  # 404 = loop never registered — a state, not an error
            resp.raise_for_status()
        runs = client.post(
            "/flow_runs/filter",
            json={"flows": {"name": {"any_": [LOOP_FLOW]}}, "sort": "START_TIME_DESC", "limit": 1},
        )
        runs.raise_for_status()
    return parse_loop_status(deployment, runs.json())
