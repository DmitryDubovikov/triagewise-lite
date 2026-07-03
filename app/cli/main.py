"""Thin CLI adapter (CLAUDE.md rule 6): parse args, open the boundary, call the workflow.

    python -m app.cli.main [TICKET_ID]

Triages one ticket (the first, or the given id) at the configured TRIAGE_TIER, using the
champion prompt from the registry. The LLM call is offline/$0 in the default replay mode, but
the prompt now lives in MLflow (iter 1), so this needs the registry reachable (`make up` +
`python -m scripts.register_prompt`).
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.config import get_settings
from app.persistence.prompts import open_registry
from app.persistence.tickets import get_ticket, load_tickets
from app.workflow.triage_flow import triage_ticket


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    # Transport configures logging; the access layer just logs (SLO line lands on stderr).
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
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

    client = open_registry(settings)
    result = asyncio.run(
        triage_ticket(ticket, tier=settings.triage_tier, client=client, settings=settings)
    )
    print(f"[{ticket.id}] {settings.triage_tier} ({settings.llm_mode})")
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
