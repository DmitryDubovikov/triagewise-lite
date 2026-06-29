"""Triage orchestration: ticket -> route() -> parsed TriageResult.

The prompt lives here inline for now; in iter 1 it becomes a versioned MLflow Prompt Registry
artifact loaded at the boundary. Domain stays pure (schema/parse); persistence reads fixtures.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.triage import Ticket, TriageResult, parse_triage
from app.llm.cassettes import Messages
from app.llm.router import route

_SYSTEM = (
    "You triage Driftwood (a SaaS task-tracker) support tickets. "
    "Reply with ONLY a JSON object with keys: "
    "category (string), priority (low|medium|high|urgent), "
    "sentiment (negative|neutral|positive), needs_human (boolean), "
    "draft_reply (string). No prose, no code fences."
)


def build_messages(ticket: Ticket) -> Messages:
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Subject: {ticket.subject}\n\n{ticket.body}"},
    ]


async def triage_ticket(
    ticket: Ticket, *, tier: str, settings: Settings | None = None
) -> TriageResult:
    content = await route(tier, build_messages(ticket), settings=settings)
    return parse_triage(content)
