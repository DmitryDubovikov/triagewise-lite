"""Author a replay cassette OFFLINE — no network, $0.

The replay smoke needs a committed cassette but we don't spend money to get one in iter 0.
This fabricates a *format-valid* triage response (existence-gate, not accuracy) and writes it
through the same cassette_key() the router uses, so router replay finds it.

    python -m scripts.author_cassette DW-001 cheap

The fabricated response is a fixture, not a real model output; real cassettes come from
LLM_MODE=record (which costs money, rule 4).
"""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.llm.cassettes import cassette_key, save
from app.llm.tiers import resolve_model
from app.persistence.tickets import get_ticket, load_tickets
from app.workflow.triage_flow import build_messages

# Hand-authored, format-valid triage replies keyed by ticket id.
_FIXTURE_REPLIES: dict[str, dict] = {
    "DW-001": {
        "category": "account_access",
        "priority": "high",
        "sentiment": "negative",
        "needs_human": True,
        "draft_reply": (
            "Sorry you're locked out. I've flagged your account for a manual reset — "
            "you'll get a fresh link within a few minutes so you make your standup."
        ),
    },
}


def main(argv: list[str]) -> int:
    ticket_id = argv[0] if argv else "DW-001"
    tier = argv[1] if len(argv) > 1 else "cheap"
    settings = get_settings()

    if ticket_id not in _FIXTURE_REPLIES:
        print(
            f"No hand-authored reply for '{ticket_id}' (have: {sorted(_FIXTURE_REPLIES)}). "
            "Add one to _FIXTURE_REPLIES, or record it live (LLM_MODE=record, costs money).",
            file=sys.stderr,
        )
        return 1

    ticket = get_ticket(load_tickets(settings.tickets_path), ticket_id)
    if ticket is None:
        print(f"No ticket with id '{ticket_id}' in fixture", file=sys.stderr)
        return 1
    messages = build_messages(ticket)
    model = resolve_model(tier)
    key = cassette_key(model, messages)

    reply = _FIXTURE_REPLIES[ticket_id]
    save(settings.cassettes_dir, key, model, messages, {"content": json.dumps(reply)})
    print(f"Wrote cassette for {ticket_id} ({tier} -> {model}): {key}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
