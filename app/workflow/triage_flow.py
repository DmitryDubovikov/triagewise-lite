"""Triage orchestration: load prompt by alias -> route() -> parsed TriageResult.

The prompt is no longer inline — it's a versioned MLflow Prompt Registry artifact loaded by
alias (iter 1). The registry handle is opened at the transport boundary and passed in (seam
option A, CLAUDE.md rule 6): the workflow loads + formats the prompt, then calls route(), which
stays a pure tier->model->cassette chokepoint and never imports the registry. Domain stays pure.

Online observability (iter 5a): each triage is wrapped in a Phoenix span carrying the parsed
labels. Tracing is initialized (or not) at the transport boundary; here triage_span() is a
no-op unless the transport turned it on. `batch` is a plain traffic tag for the drift monitor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import Settings
from app.domain.triage import Ticket, TriageResult, parse_triage
from app.llm.router import route
from app.observability.phoenix import triage_span
from app.persistence.prompts import CHAMPION, format_for_ticket, load_triage_prompt

if TYPE_CHECKING:
    from mlflow import MlflowClient


async def triage_ticket(
    ticket: Ticket,
    *,
    tier: str,
    client: MlflowClient,
    alias: str = CHAMPION,
    settings: Settings | None = None,
    batch: str | None = None,
) -> TriageResult:
    prompt = load_triage_prompt(client, alias)
    messages = format_for_ticket(prompt, ticket)
    with triage_span(ticket, tier=tier, batch=batch) as recorder:
        content = await route(tier, messages, settings=settings)
        result = parse_triage(content)
        recorder.set_result(result)
    return result
