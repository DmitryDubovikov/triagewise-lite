"""Ticket fixture I/O — reads the synthetic Driftwood ticket stream."""

from __future__ import annotations

import json
from pathlib import Path

from app.domain.triage import Ticket


def load_tickets(path: Path) -> list[Ticket]:
    lines = path.read_text().splitlines()
    return [Ticket.model_validate(json.loads(line)) for line in lines if line.strip()]


def get_ticket(tickets: list[Ticket], ticket_id: str) -> Ticket | None:
    return next((t for t in tickets if t.id == ticket_id), None)
