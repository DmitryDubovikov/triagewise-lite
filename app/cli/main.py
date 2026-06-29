"""Thin CLI adapter (CLAUDE.md rule 6): parse args, open the boundary, call the workflow.

    python -m app.cli.main [TICKET_ID]

Triages one ticket (the first, or the given id) at the configured TRIAGE_TIER. In the default
replay mode this is offline and $0.
"""

from __future__ import annotations

import asyncio
import sys

from app.config import get_settings
from app.persistence.tickets import get_ticket, load_tickets
from app.workflow.triage_flow import triage_ticket


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    settings = get_settings()
    tickets = load_tickets(settings.tickets_path)

    wanted = argv[0] if argv else None
    if wanted:
        ticket = get_ticket(tickets, wanted)
    else:
        ticket = tickets[0] if tickets else None
    if ticket is None:
        msg = f"No ticket with id '{wanted}'" if wanted else "No tickets in fixture"
        print(msg, file=sys.stderr)
        return 1

    result = asyncio.run(triage_ticket(ticket, tier=settings.triage_tier, settings=settings))
    print(f"[{ticket.id}] {settings.triage_tier} ({settings.llm_mode})")
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
