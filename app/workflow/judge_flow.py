"""Online-eval workflow: pull traced triage spans -> sample -> judge -> annotate (iter 5b).

Pure glue over the seams: the Phoenix client is opened at the transport boundary and passed
in, like the registry handle (rule 6); the span-store dialect lives in the observability
helpers; sampling/selection is a domain decision. The judge runner is an injected callable,
so tests exercise this glue with a fake — the real phoenix.evals runner
(app/observability/judge.py) only ever runs on an explicit live go (rule 4). Incremental by
design: spans already carrying the judge annotation are filtered out, so re-running without
new traffic judges nothing and costs nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.config import Settings
from app.domain.judge import JudgeCandidate, JudgeVerdict, select_for_judgement
from app.observability.phoenix import (
    extract_candidates,
    fetch_judge_annotations,
    fetch_triage_spans,
    log_verdicts,
)

if TYPE_CHECKING:
    from phoenix.client import Client

JudgeRunner = Callable[[list[JudgeCandidate]], list[JudgeVerdict]]


class JudgeRunReport(BaseModel):
    spans_seen: int
    already_judged: int
    truncated: bool  # the span fetch hit its page limit — older traffic wasn't considered
    verdicts: list[JudgeVerdict]


def judge_traffic(client: Client, settings: Settings, runner: JudgeRunner) -> JudgeRunReport:
    """Sample untried traffic, run the judge over it, write verdicts back as span annotations."""
    spans, truncated = fetch_triage_spans(client, settings)
    judged_ids = {a["span_id"] for a in fetch_judge_annotations(client, settings, spans)}
    candidates = select_for_judgement(
        extract_candidates(spans), judged_span_ids=judged_ids, rate=settings.judge_sample_rate
    )
    verdicts = runner(candidates) if candidates else []
    if verdicts:
        log_verdicts(client, verdicts)
    return JudgeRunReport(
        spans_seen=len(spans),
        already_judged=len(judged_ids),
        truncated=truncated,
        verdicts=verdicts,
    )
