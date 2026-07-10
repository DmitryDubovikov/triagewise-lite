"""Phoenix tracing — the online-observability seam (iter 5a).

Off by default (PHOENIX_ENABLED=0): triage_span() yields a no-op recorder and nothing under
`phoenix`/OTel is ever imported, so tests, CI and plain replay runs stay byte-identical to
iter 4. init_tracing() is called once at the transport boundary (like the registry handle);
the workflow only wraps its work in triage_span(). No litellm callbacks are involved (rule 5)
— the span is ours, around the workflow, and the export target is localhost Phoenix.

Span vocabulary: one span per triaged ticket, named "triage_ticket", carrying flat
`triage.*` attributes (ticket_id, batch, tier, category, priority, sentiment, needs_human)
plus OpenInference input/output values so the Phoenix UI renders the exchange. Deliberately
NO model/mode attributes: the span would only be re-predicting them, and the SLO log
(app/llm/slo.py) is already the ground truth for model/mode/cache/cost per call.
The drift report (scripts/drift_report.py) aggregates `triage.batch` x `triage.category`.

This module is also the span-STORE seam (iter 5b): the vocabulary constants plus the
read/write helpers every store client shares (judge flow, drift and judge reports). The
helpers take the Phoenix client as an argument — it is opened at the transport boundary,
and this module still imports nothing Phoenix at module level.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from app.config import Settings
from app.domain.judge import JudgeCandidate, JudgeVerdict

if TYPE_CHECKING:
    from phoenix.client import Client

    from app.domain.triage import Ticket, TriageResult

SPAN_NAME = "triage_ticket"

# Batch labels `make traffic` stamps on spans — the two sides of the drift comparison (5a).
# Shared by the drift report and the dashboard's drift card (iter 7).
BASELINE_BATCH = "base"
CANDIDATE_BATCH = "postrelease"

# One page of spans — the shared ceiling for every span-store reader (judge flow, drift and
# judge reports). At ~21 spans per `make traffic` it truncates only after ~47 runs; readers
# warn loudly when they hit it. Pagination — if the store ever really grows.
FETCH_LIMIT = 1000

# The judge's annotation on a span (iter 5b) — what reports and the Phoenix UI group by.
JUDGE_ANNOTATION = "triage_quality"


def fetch_triage_spans(client: Client, settings: Settings) -> tuple[list[Any], bool]:
    """One page of traced triage spans, plus whether the page limit truncated the read."""
    spans = client.spans.get_spans(
        project_identifier=settings.phoenix_project, name=SPAN_NAME, limit=FETCH_LIMIT
    )
    return list(spans), len(spans) >= FETCH_LIMIT


def batch_category_rows(spans: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """(batch, category) observations for the drift decision (app/domain/drift.py), dropping
    spans that don't carry both. The store dialect (flat dotted attribute keys) stays at this
    seam — shared by the drift report script and the dashboard's drift card."""
    rows: list[tuple[str, str]] = []
    for span in spans:
        attrs = span.get("attributes") or {}
        batch, category = attrs.get("triage.batch"), attrs.get("triage.category")
        if batch is not None and category is not None:
            rows.append((str(batch), str(category)))
    return rows


def fetch_judge_annotations(client: Client, settings: Settings, spans: list[Any]) -> list[Any]:
    """The judge annotations already sitting on these spans — the incremental evaluator's
    skip set, and the judge report's subject."""
    if not spans:
        return []
    return list(
        client.spans.get_span_annotations(
            spans=spans,
            project_identifier=settings.phoenix_project,
            include_annotation_names=[JUDGE_ANNOTATION],
            limit=FETCH_LIMIT,
        )
    )


def extract_candidates(spans: Iterable[Mapping[str, Any]]) -> list[JudgeCandidate]:
    """Parse raw span dicts (flat dotted attribute keys) into typed judge candidates,
    dropping spans that don't carry a full triage exchange. The store dialect stays at
    this seam; domain only ever sees JudgeCandidate."""
    candidates: list[JudgeCandidate] = []
    for span in spans:
        span_id = (span.get("context") or {}).get("span_id")
        attrs = span.get("attributes") or {}
        ticket_id = attrs.get("triage.ticket_id")
        ticket_text = attrs.get("input.value")
        triage_json = attrs.get("output.value")
        if not span_id or not ticket_id or ticket_text is None or triage_json is None:
            continue
        candidates.append(
            JudgeCandidate(
                span_id=str(span_id),
                ticket_id=str(ticket_id),
                ticket_text=str(ticket_text),
                triage_json=str(triage_json),
            )
        )
    return candidates


def log_verdicts(client: Client, verdicts: Iterable[JudgeVerdict]) -> None:
    """Write judge verdicts back as span annotations, next to the traces they judge."""
    payload: list[Any] = []
    for v in verdicts:
        # Phoenix's AnnotationResult wants keys absent, not null, when there's no value.
        result: dict[str, str | float] = {"label": v.label}
        if v.score is not None:
            result["score"] = v.score
        if v.explanation is not None:
            result["explanation"] = v.explanation
        payload.append(
            {
                "span_id": v.span_id,
                "name": JUDGE_ANNOTATION,
                "annotator_kind": "LLM",
                "result": result,
            }
        )
    client.spans.log_span_annotations(span_annotations=payload, sync=True)


# Set once by init_tracing(); None = tracing off, triage_span() is a no-op.
_tracer: Any = None


def init_tracing(settings: Settings) -> bool:
    """Wire the OTel tracer to Phoenix at the boundary. Returns whether tracing is on.

    Idempotent: a second call reuses the tracer instead of stacking exporters.
    """
    global _tracer
    if not settings.phoenix_enabled:
        return False
    if _tracer is None:
        from phoenix.otel import register  # lazy: the off-path never imports OTel

        provider = register(
            project_name=settings.phoenix_project,
            endpoint=f"{settings.phoenix_endpoint}/v1/traces",
            set_global_tracer_provider=False,  # keep OTel state ours, not process-global
            verbose=False,
        )
        _tracer = provider.get_tracer("triagewise")
    return True


class SpanRecorder:
    """Hands the workflow a place to attach the parsed result; no-op when tracing is off."""

    def __init__(self, span: Any = None) -> None:
        self._span = span

    def set_result(self, result: TriageResult) -> None:
        if self._span is None:
            return
        self._span.set_attribute("output.value", result.model_dump_json())
        self._span.set_attribute("triage.category", result.category)
        self._span.set_attribute("triage.priority", result.priority)
        self._span.set_attribute("triage.sentiment", result.sentiment)
        self._span.set_attribute("triage.needs_human", result.needs_human)


@contextmanager
def triage_span(ticket: Ticket, *, tier: str, batch: str | None = None) -> Iterator[SpanRecorder]:
    if _tracer is None:
        yield SpanRecorder()
        return
    with _tracer.start_as_current_span(SPAN_NAME) as span:
        span.set_attribute("openinference.span.kind", "CHAIN")
        span.set_attribute("input.value", f"{ticket.subject}\n\n{ticket.body}")
        span.set_attribute("triage.ticket_id", ticket.id)
        span.set_attribute("triage.tier", tier)
        if batch is not None:
            span.set_attribute("triage.batch", batch)
        yield SpanRecorder(span)
