"""Online-judge decisions — pure sampling + candidate selection, no I/O (CLAUDE.md rule 6).

The online evaluator (iter 5b) doesn't judge every traced span: production traffic gets
sampled. Sampling is deterministic per ticket (a hash bucket, not random), so re-running the
judge over the same traffic picks the same spans — which keeps the incremental no-op property
verifiable. Pulling spans from Phoenix and parsing their store dialect is the observability
seam's job (app/observability/phoenix.py, same split as the drift sibling); deciding is ours.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Set

from pydantic import BaseModel


class JudgeCandidate(BaseModel):
    """One traced triage exchange, carrying exactly what the judge prompt needs."""

    span_id: str
    ticket_id: str
    ticket_text: str  # the span's input.value (subject + body)
    triage_json: str  # the span's output.value (parsed TriageResult as JSON)


class JudgeVerdict(BaseModel):
    span_id: str
    label: str  # correct | incorrect
    score: float | None = None
    explanation: str | None = None


def sampled(ticket_id: str, rate: float) -> bool:
    """Deterministic traffic sampling: same ticket -> same decision on every run."""
    bucket = int.from_bytes(hashlib.sha256(ticket_id.encode()).digest()[:8], "big") / 2**64
    return bucket < rate


def select_for_judgement(
    candidates: Iterable[JudgeCandidate], *, judged_span_ids: Set[str], rate: float
) -> list[JudgeCandidate]:
    """Pick what the judge should look at: exchanges that aren't annotated yet (incremental —
    re-runs cost nothing) and fall into the sample."""
    return [
        c for c in candidates if c.span_id not in judged_span_ids and sampled(c.ticket_id, rate)
    ]
