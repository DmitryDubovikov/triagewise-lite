"""Iter-5b existence gates, offline: sampling is deterministic and pure, span parsing stays
at the observability seam, and the judge flow glue (fetch -> filter -> judge -> annotate)
works against a fake Phoenix client and a fake runner — the real phoenix.evals harness is
live-gated and never runs here (rule 4)."""

from __future__ import annotations

import sys

from app.config import Settings
from app.domain.judge import JudgeVerdict, sampled, select_for_judgement
from app.observability.phoenix import JUDGE_ANNOTATION, extract_candidates
from app.workflow.judge_flow import judge_traffic


def _span(span_id: str, ticket_id: str) -> dict:
    return {
        "context": {"trace_id": "t", "span_id": span_id},
        "attributes": {
            "triage.ticket_id": ticket_id,
            "input.value": f"Subject of {ticket_id}",
            "output.value": '{"category": "bug"}',
        },
    }


class FakeSpans:
    """Duck-typed client.spans: canned reads, captured writes."""

    def __init__(self, spans: list[dict], annotations: list[dict]) -> None:
        self._spans, self._annotations = spans, annotations
        self.logged: list[dict] = []

    def get_spans(self, **_: object) -> list[dict]:
        return self._spans

    def get_span_annotations(self, **_: object) -> list[dict]:
        return self._annotations

    def log_span_annotations(self, *, span_annotations: list[dict], sync: bool) -> None:
        self.logged.extend(span_annotations)


class FakeClient:
    def __init__(self, spans: FakeSpans) -> None:
        self.spans = spans


def test_sampling_is_deterministic_and_respects_rate_edges():
    ids = [f"DW-{i:03d}" for i in range(50)]
    assert [sampled(i, 0.5) for i in ids] == [sampled(i, 0.5) for i in ids]
    assert all(sampled(i, 1.0) for i in ids)
    assert not any(sampled(i, 0.0) for i in ids)


def test_extract_candidates_drops_spans_without_a_full_exchange():
    spans = [
        _span("s1", "DW-001"),
        {"context": {"span_id": "s3"}, "attributes": {}},  # not a triage exchange
    ]
    candidates = extract_candidates(spans)
    assert [c.span_id for c in candidates] == ["s1"]
    assert candidates[0].ticket_id == "DW-001"


def test_select_for_judgement_skips_already_judged():
    candidates = extract_candidates([_span("s1", "DW-001"), _span("s2", "DW-002")])
    picked = select_for_judgement(candidates, judged_span_ids={"s2"}, rate=1.0)
    assert [c.span_id for c in picked] == ["s1"]


def test_judge_traffic_annotates_sampled_spans():
    fake = FakeSpans([_span("s1", "DW-001"), _span("s2", "DW-002")], annotations=[])
    seen: list[list] = []

    def runner(candidates):
        seen.append(candidates)
        return [
            JudgeVerdict(span_id=c.span_id, label="correct", score=1.0, explanation="fine")
            for c in candidates
        ]

    settings = Settings(judge_sample_rate=1.0)
    report = judge_traffic(FakeClient(fake), settings, runner)

    assert report.spans_seen == 2 and report.already_judged == 0 and not report.truncated
    assert [c.ticket_id for c in seen[0]] == ["DW-001", "DW-002"]
    assert [v.span_id for v in report.verdicts] == ["s1", "s2"]
    assert fake.logged and all(a["name"] == JUDGE_ANNOTATION for a in fake.logged)
    assert fake.logged[0]["annotator_kind"] == "LLM"
    assert fake.logged[0]["result"] == {"label": "correct", "score": 1.0, "explanation": "fine"}
    assert not any(m == "phoenix.evals" or m.startswith("phoenix.evals.") for m in sys.modules)


def test_judge_traffic_rerun_is_a_noop():
    """Incremental online eval: everything already judged -> no runner call, no writes."""
    annotations = [
        {"span_id": "s1", "name": JUDGE_ANNOTATION, "result": {"label": "correct"}},
        {"span_id": "s2", "name": JUDGE_ANNOTATION, "result": {"label": "incorrect"}},
    ]
    fake = FakeSpans([_span("s1", "DW-001"), _span("s2", "DW-002")], annotations)

    def runner(candidates):
        raise AssertionError("runner must not be called when everything is judged")

    report = judge_traffic(FakeClient(fake), Settings(judge_sample_rate=1.0), runner)
    assert report.already_judged == 2 and report.verdicts == [] and fake.logged == []
