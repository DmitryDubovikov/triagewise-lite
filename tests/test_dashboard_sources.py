"""Iter-7 existence gates, offline: the promotion log persists gate turns and the dashboard
sources distill each store's dialect — all in plain pytest, no streamlit, no store, no
network, no LLM anywhere (the render layer lives only in the dashboard image and is
exercised by the compose smoke at close)."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.llm.slo import CallRecord
from app.observability.phoenix import batch_category_rows
from app.persistence.promotion_log import PromotionRecord, last_promotion, log_promotion
from app.ui.sources import parse_loop_status, slo_summary, summarize_judge


def make_promotion(**overrides) -> PromotionRecord:
    base = dict(
        ts="2026-07-09T00:00:00.000+00:00",
        champion_version=1,
        champion_score=0.75,
        challenger_version=2,
        challenger_score=1.0,
        promoted=True,
        champion_version_after=2,
        golden_count=3,
        mode="replay",
    )
    return PromotionRecord(**{**base, **overrides})


def test_promotion_log_appends_and_last_wins(tmp_path: Path):
    settings = Settings(promotion_log_path=tmp_path / "promotions.jsonl")
    log_promotion(make_promotion(), settings)
    log_promotion(make_promotion(promoted=False, champion_version=2), settings)
    got = last_promotion(settings.promotion_log_path)
    assert got is not None and not got.promoted and got.champion_version == 2


def test_last_promotion_tolerates_absence_and_garbage(tmp_path: Path):
    assert last_promotion(tmp_path / "absent.jsonl") is None
    path = tmp_path / "promotions.jsonl"
    path.write_text(make_promotion().model_dump_json() + "\n" + '{"torn": tr')
    got = last_promotion(path)  # the torn tail is skipped, the newest parseable record wins
    assert got is not None and got.promoted


def make_call(**overrides) -> CallRecord:
    base = dict(
        ts="2026-07-09T00:00:00.000+00:00",
        tier="cheap",
        model="gpt-test",
        mode="replay",
        latency_ms=12.0,
        cost_usd=0.001,
        cost_source="cassette",
        cache="off",
        slo_breaches=[],
    )
    return CallRecord(**{**base, **overrides})


def test_slo_summary_aggregates_and_skips_garbage(tmp_path: Path):
    path = tmp_path / "llm_calls.jsonl"
    lines = [
        make_call(cache="hit").model_dump_json(),
        "not json at all",
        make_call(
            cache="miss", cost_usd=0.002, slo_breaches=["latency 9ms > 1ms"]
        ).model_dump_json(),
        # a real network call — the only one that should count toward the live cost/latency averages
        make_call(mode="live", latency_ms=400.0, cost_usd=0.0001).model_dump_json(),
    ]
    path.write_text("\n".join(lines) + "\n")
    summary = slo_summary(path)
    assert summary.calls == 3 and summary.total_cost_usd == 0.0031
    assert summary.breached_calls == 1
    assert summary.cache_hits == 1 and summary.cache_misses == 1
    assert summary.live_calls == 1
    assert summary.avg_live_latency_ms == 400.0 and summary.avg_live_cost_usd == 0.0001
    assert summary.last_call is not None and summary.last_call.mode == "live"


def test_slo_summary_empty_without_log(tmp_path: Path):
    summary = slo_summary(tmp_path / "absent.jsonl")
    assert summary.calls == 0 and summary.last_call is None


def test_summarize_judge_means_scores_and_tallies_labels():
    spans = [{"a": 1}, {"a": 2}, {"a": 3}]  # 3 traced, only 2 judged
    annotations = [
        {"span_id": "s1", "result": {"label": "correct", "score": 1.0}},
        {"span_id": "s2", "result": {"label": "incorrect", "score": 0.0}},
    ]
    summary = summarize_judge(spans, annotations)
    assert summary.traced == 3 and summary.judged == 2
    assert summary.mean_score == 0.5
    assert summary.labels == {"correct": 1, "incorrect": 1}


def test_summarize_judge_handles_no_verdicts():
    summary = summarize_judge([{"a": 1}], [])
    assert summary.traced == 1 and summary.judged == 0
    assert summary.mean_score is None and summary.labels == {}


def test_batch_category_rows_keeps_only_complete_spans():
    spans = [
        {"attributes": {"triage.batch": "base", "triage.category": "bug"}},
        {"attributes": {"triage.category": "bug"}},  # no batch
        {"attributes": {"triage.batch": "postrelease"}},  # no category
        {},  # no attributes at all
        {"attributes": {"triage.batch": "postrelease", "triage.category": "automation"}},
    ]
    assert batch_category_rows(spans) == [("base", "bug"), ("postrelease", "automation")]


def test_parse_loop_status_reads_both_api_answers():
    deployment = {"schedules": [{"active": True, "schedule": {"interval": 60.0}}]}
    runs = [{"state": {"type": "COMPLETED"}, "start_time": "2026-07-09T00:01:00+00:00"}]
    status = parse_loop_status(deployment, runs)
    assert status.interval_seconds == 60.0 and status.schedule_active is True
    assert status.last_run_state == "COMPLETED"
    assert status.last_run_time == "2026-07-09T00:01:00+00:00"


def test_parse_loop_status_handles_nothing_registered():
    status = parse_loop_status(None, [])
    assert status == (None, None, None, None)


def test_parse_loop_status_scheduled_run_uses_expected_time():
    runs = [{"state": {"type": "SCHEDULED"}, "start_time": None, "expected_start_time": "soon"}]
    status = parse_loop_status({"schedules": []}, runs)
    assert status.last_run_state == "SCHEDULED" and status.last_run_time == "soon"


def test_sources_import_without_streamlit():
    """The sources module must stay render-free: importing it (as this whole suite does)
    pulls no streamlit — the uv env doesn't even have it."""
    import sys

    import app.ui.sources  # noqa: F401

    assert "streamlit" not in sys.modules


def test_loop_names_match_the_flow():
    """The dashboard reads the loop by name over REST (its image has no prefect lib) — the
    shared constants in app/config.py must be the names the flow actually registers."""
    from app.cli.loop import continuous_evaluation
    from app.config import LOOP_FLOW

    assert continuous_evaluation.name == LOOP_FLOW


def test_dashboard_image_pins_match_uv_lock():
    """requirements.txt claims 'same numbers as uv.lock' — check it mechanically (the iter-0
    pin-gate posture: pins are verified, not prose). Image-only deps (streamlit) are skipped;
    mlflow-skinny rides the same release train as the host's mlflow."""
    import tomllib

    root = Path(__file__).resolve().parent.parent
    lock = {
        p["name"]: p["version"] for p in tomllib.loads((root / "uv.lock").read_text())["package"]
    }
    aliases = {"mlflow-skinny": "mlflow"}
    checked = 0
    for line in (root / "dashboard" / "requirements.txt").read_text().splitlines():
        spec = line.split("#")[0].strip()
        if "==" not in spec:
            continue
        name, _, version = spec.partition("==")
        host = lock.get(aliases.get(name, name))
        if host is not None:
            assert host == version, f"{name}: image pins {version}, uv.lock has {host}"
            checked += 1
    assert checked >= 4  # the shared pins are actually being compared, not silently skipped
