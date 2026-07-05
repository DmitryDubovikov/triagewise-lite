"""Thin batch transport (CLAUDE.md rule 6): triage a whole ticket batch, traced to Phoenix.

    PHOENIX_ENABLED=1 python -m app.cli.batch fixtures/tickets.jsonl --batch base

Runs every ticket in the file through the champion prompt at TRIAGE_TIER — offline/$0 in the
default replay mode (cassettes for both fixture batches are authored offline). The --batch
label lands on every span as `triage.batch`, which is what the drift report aggregates by.
Re-running appends more spans (traces are append-only); the drift verdict is stable because
the report compares per-batch distributions, not counts.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from app.config import get_settings
from app.observability.phoenix import init_tracing
from app.persistence.prompts import open_registry
from app.persistence.tickets import load_tickets
from app.workflow.triage_flow import triage_ticket


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tickets", type=Path, help="ticket batch (JSONL)")
    parser.add_argument(
        "--batch", required=True, help="batch label on every span, e.g. base | postrelease"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    settings = get_settings()
    traced = init_tracing(settings)
    if not traced:
        print("PHOENIX_ENABLED=0 — running untraced", file=sys.stderr)

    tickets = load_tickets(args.tickets)
    if not tickets:
        print(f"No tickets in {args.tickets}", file=sys.stderr)
        return 1

    client = open_registry(settings)

    async def run() -> None:
        for ticket in tickets:
            result = await triage_ticket(
                ticket,
                tier=settings.triage_tier,
                client=client,
                settings=settings,
                batch=args.batch,
            )
            print(f"[{ticket.id}] {result.category}")

    asyncio.run(run())
    print(
        f"{len(tickets)} tickets triaged (batch={args.batch}, mode={settings.llm_mode}, "
        f"traced={traced})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
