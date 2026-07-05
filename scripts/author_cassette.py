"""Author replay cassettes OFFLINE — no network, no LLM, $0.

The replay flows need committed cassettes but we don't spend money to get them. This fabricates
*format-valid* triage responses (existence-gate, not accuracy) from fixtures/replies.jsonl and
writes them through the same cassette_key() the router uses. Messages come from the champion
prompt via the registry + pv.format() — the exact path triage_ticket takes — so the key can't
drift from the real flow. The registry here is a throwaway sqlite db (offline), synced from the
same sync_prompts().

    python -m scripts.author_cassette DW-001            # one ticket
    python -m scripts.author_cassette --all             # every ticket in both batches
    python -m scripts.author_cassette DW-101 smart      # non-default tier

Idempotent: the same reply lands at the same key, so re-running overwrites in place — except
live-recorded cassettes (the ones carrying usage/cost_usd), which are paid artifacts and are
never clobbered by a fabrication.

# dl-lite: fabricated format-valid replies -> upgrade: LLM_MODE=record (real outputs, costs money)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.config import get_settings
from app.llm.cassettes import cassette_key, load, save
from app.llm.tiers import resolve_model
from app.persistence.prompts import (
    CHAMPION,
    format_for_ticket,
    load_triage_prompt,
    open_registry,
    sync_prompts,
)
from app.persistence.tickets import load_replies, load_tickets


def main(argv: list[str]) -> int:
    target = argv[0] if argv else "DW-001"
    tier = argv[1] if len(argv) > 1 else "cheap"
    settings = get_settings()

    tickets = load_tickets(settings.tickets_path) + load_tickets(settings.tickets_postrelease_path)
    replies = load_replies(settings.replies_path)

    if target == "--all":
        wanted = tickets
    else:
        wanted = [t for t in tickets if t.id == target]
        if not wanted:
            print(f"No ticket with id '{target}' in either batch fixture", file=sys.stderr)
            return 1

    missing = [t.id for t in wanted if t.id not in replies]
    if missing:
        print(
            f"No fabricated reply for {missing} in {settings.replies_path}. Add them, or "
            "record live (LLM_MODE=record, costs money, rule 4).",
            file=sys.stderr,
        )
        return 1

    # Throwaway offline registry: same sync, same prompt, same messages as the live flow.
    with tempfile.TemporaryDirectory() as tmp:
        offline = settings.model_copy(
            update={"mlflow_tracking_uri": f"sqlite:///{Path(tmp) / 'reg.db'}"}
        )
        client = open_registry(offline)
        sync_prompts(client)
        prompt = load_triage_prompt(client, CHAMPION)
        model = resolve_model(tier, settings.tiers_path)
        for ticket in wanted:
            messages = format_for_ticket(prompt, ticket)
            key = cassette_key(model, messages)
            existing = load(settings.cassettes_dir, key)
            if existing is not None and ("usage" in existing or "cost_usd" in existing):
                print(
                    f"Skipping {ticket.id}: live-recorded cassette exists ({key[:12]}…) — "
                    "a fabrication never clobbers a paid recording"
                )
                continue
            save(
                settings.cassettes_dir,
                key,
                model,
                messages,
                {"content": replies[ticket.id].model_dump_json()},
            )
            print(f"Wrote cassette for {ticket.id} ({tier} -> {model}): {key}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
