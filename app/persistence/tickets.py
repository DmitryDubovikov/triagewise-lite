"""Ticket fixture I/O — reads the synthetic Driftwood ticket stream."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.triage import GoldenTicket, Ticket, TriageResult


def load_tickets(path: Path) -> list[Ticket]:
    lines = path.read_text().splitlines()
    return [Ticket.model_validate(json.loads(line)) for line in lines if line.strip()]


def load_replies(path: Path) -> dict[str, TriageResult]:
    """Read the fabricated-reply fixture (iter 5a): ticket id -> format-valid TriageResult.

    These back the offline cassettes for both traffic batches (scripts.author_cassette).
    Validation is the point: a malformed reply fails here, not inside a replayed triage.
    """
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {row["id"]: TriageResult.model_validate(row["reply"]) for row in rows}


def load_golden(path: Path) -> list[GoldenTicket]:
    """Read the DVC-versioned golden set. Validation is the point: a mislabeled row
    (bad enum, missing field) fails here, not silently downstream in the eval gate."""
    lines = path.read_text().splitlines()
    return [GoldenTicket.model_validate(json.loads(line)) for line in lines if line.strip()]


def get_ticket(tickets: list[Ticket], ticket_id: str) -> Ticket | None:
    return next((t for t in tickets if t.id == ticket_id), None)
