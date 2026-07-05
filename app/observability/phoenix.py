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
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from app.config import Settings

if TYPE_CHECKING:
    from app.domain.triage import Ticket, TriageResult

SPAN_NAME = "triage_ticket"

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
