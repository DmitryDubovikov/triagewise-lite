"""Control-plane dashboard (iter 7) — one read-only Streamlit page, five lifecycle proofs.

A thin transport (rule 6): open handles at the boundary, call app/ui/sources, render. Every
card is a fresh read of its store on each rerun; the panel never writes and never calls an
LLM — the stores stay the source of truth (rule 8: this page is a rendering of the stores,
verification still happens against them). A card whose backend is down degrades to a warning
with the operator hint instead of taking the page down. Streamlit itself is the render
vehicle, not a resume line: it exists only in the dashboard image (dashboard/requirements.txt),
never in the uv env — hence no test imports this module.
"""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from app.config import LOOP_DEPLOYMENT, LOOP_FLOW, get_settings
from app.observability.phoenix import CANDIDATE_BATCH
from app.persistence.promotion_log import last_promotion
from app.persistence.prompts import TRIAGE_PROMPT_NAME, open_registry
from app.ui.sources import drift_status, fetch_loop_status, prompt_statuses, slo_summary

settings = get_settings()

st.set_page_config(page_title="triagewise control plane", page_icon="🗼", layout="wide")
st.title("triagewise — LLMOps control plane")
st.caption(
    "Read-only: every card is a fresh read of its store — MLflow registry, Phoenix spans, "
    "Prefect API, JSONL logs. The panel renders the lifecycle; the stores stay the truth."
)
st.button("↻ re-read stores")  # any click reruns the script = every card reads fresh


def card(title: str, render: Callable[[], None], hint: str) -> None:
    """One proof, one container; a dead backend degrades the card, not the page."""
    with st.container(border=True):
        st.subheader(title)
        try:
            render()
        except Exception as exc:  # any store failure = the same degraded card
            st.warning(f"unavailable: {exc}")
            st.caption(hint)


def render_prompts() -> None:
    statuses = prompt_statuses(open_registry(settings))
    for col, status in zip(st.columns(len(statuses)), statuses, strict=True):
        col.metric(f"prompts:/{TRIAGE_PROMPT_NAME}@{status.alias}", f"v{status.version}")
    st.caption(
        f"prompt-as-artifact: aliases live in the MLflow registry ({settings.mlflow_tracking_uri})"
    )


def render_gate() -> None:
    record = last_promotion(settings.promotion_log_path)
    if record is None:
        st.info("no gate turn logged yet — run `make promote` (or `make loop`)")
        return
    verdict = f"swapped → v{record.champion_version_after}" if record.promoted else "no swap"
    left, right = st.columns(2)
    left.metric(f"champion v{record.champion_version}", f"{record.champion_score:.3f}")
    right.metric(f"challenger v{record.challenger_version}", f"{record.challenger_score:.3f}")
    (st.success if record.promoted else st.info)(f"gate: {verdict}")
    st.caption(
        f"{record.ts} · {record.golden_count} golden tickets · mode={record.mode} · "
        f"champion after turn: v{record.champion_version_after}"
    )


def render_drift() -> None:
    from phoenix.client import Client  # lazy: the store client opens at THIS boundary

    status = drift_status(Client(base_url=settings.phoenix_endpoint), settings)
    if status is None:
        st.info("no traced triage spans yet — run `make traffic` (it sets PHOENIX_ENABLED=1)")
        return
    report = status.report
    if report.drifted:
        st.error(f"DRIFT: new in '{CANDIDATE_BATCH}': {', '.join(report.new_categories)}")
    else:
        st.success("no categorical drift between batches")
    st.dataframe(
        [
            {"batch": batch, "category": category, "count": count}
            for batch, counts in report.distributions.items()
            for category, count in counts.items()
        ],
        hide_index=True,
    )
    st.caption(
        f"{status.observations} observations from Phoenix ({settings.phoenix_endpoint})"
        + (" · WARNING: page limit hit, sample truncated" if status.truncated else "")
    )


def render_slo() -> None:
    summary = slo_summary(settings.llm_log_path)
    if summary.calls == 0:
        st.info("no LLM calls logged yet — run `make promote` or `make traffic`")
        return
    calls, cost, breaches, rate = st.columns(4)
    calls.metric("calls", summary.calls)
    cost.metric("total cost", f"${summary.total_cost_usd:.4f}")
    breaches.metric("breached calls", summary.breached_calls)
    cached = summary.cache_hits + summary.cache_misses
    rate.metric("cache hit-rate", f"{summary.cache_hits / cached:.0%}" if cached else "—")
    last = summary.last_call
    if last is not None:
        st.caption(
            f"last: {last.ts} · {last.tier}->{last.model} ({last.mode}) · "
            f"{last.latency_ms:.0f}ms · ${last.cost_usd:.6f}"
        )


def render_loop() -> None:
    status = fetch_loop_status(settings)
    if status.interval_seconds is None and status.last_run_state is None:
        st.info("loop not registered on the Prefect server yet — run `make loop`")
        return
    interval, schedule, tick = st.columns(3)
    interval.metric(
        "interval",
        f"{status.interval_seconds:.0f}s" if status.interval_seconds is not None else "—",
    )
    schedule.metric("schedule", "active" if status.schedule_active else "paused")
    tick.metric("last tick", status.last_run_state or "—")
    st.caption(
        f"deployment {LOOP_FLOW}/{LOOP_DEPLOYMENT} on {settings.prefect_api_url}"
        + (f" · last tick at {status.last_run_time}" if status.last_run_time else "")
    )


left, right = st.columns(2)
with left:
    card(
        "Prompt registry — champion/challenger (iter 1/6a)",
        render_prompts,
        "Is MLflow up (`make up`)? Seeded (`uv run python -m scripts.register_prompt`)?",
    )
    card(
        "Drift monitor (iter 5a)",
        render_drift,
        "Is Phoenix up (`make up`)? Traffic traced (`make traffic`)?",
    )
    card(
        "Cost/latency SLO (iter 3/4)",
        render_slo,
        "The SLO log appears after any routed call — `make promote` or `make traffic`.",
    )
with right:
    card(
        "Promotion gate (iter 6a)",
        render_gate,
        "The promotion log appears after a gate turn — `make promote` or `make loop`.",
    )
    card(
        "Continuous-evaluation loop (iter 6b)",
        render_loop,
        "Is Prefect up (`make up`)? Runner started (`make loop`)?",
    )
