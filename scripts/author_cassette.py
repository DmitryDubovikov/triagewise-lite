"""Author replay cassettes OFFLINE — no network, no LLM, $0.

The replay flows need committed cassettes but we don't spend money to get them. This fabricates
*format-valid* triage responses (existence-gate, not accuracy) and writes them through the same
cassette_key() the router uses. Messages come from the registry prompts via pv.format() — the
exact path triage_ticket takes — so the key can't drift from the real flow. The registry here is
a throwaway sqlite db (offline), synced from the same sync_prompts().

Two sources, both authored for BOTH prompt templates (champion and challenger), so replay keeps
working whichever version the champion alias points at after a promotion swap (iter 6a):
- fixture tickets (both traffic batches): replies from fixtures/replies.jsonl, verbatim;
- golden tickets: replies derived from their expected labels — the challenger answers them
  faithfully, the champion misses the jokers (deterministic degradation) — which is exactly the
  difference the iter-6a promotion gate exists to catch.

    python -m scripts.author_cassette DW-001            # one ticket (fixture or golden id)
    python -m scripts.author_cassette --all             # everything: fixtures + golden
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
from app.domain.triage import GoldenTicket, Ticket, TriageResult
from app.llm.cassettes import cassette_key, load, save
from app.llm.tiers import resolve_model
from app.persistence.prompts import (
    CHALLENGER,
    CHAMPION,
    format_for_ticket,
    load_triage_prompt,
    open_registry,
    sync_prompts,
)
from app.persistence.tickets import load_golden, load_replies, load_tickets

Job = tuple[Ticket, dict[str, TriageResult]]  # ticket + reply per prompt alias


def _draft(category: str) -> str:
    topic = category.replace("_", " ")
    return f"Thanks for reaching out about {topic} — we're on it and will follow up shortly."


def faithful_reply(ticket: GoldenTicket) -> TriageResult:
    """The reply a prompt that reads the ticket right would give: the expected labels."""
    draft = _draft(ticket.expected.category)
    return TriageResult(**ticket.expected.model_dump(), draft_reply=draft)


def degraded_reply(ticket: GoldenTicket) -> TriageResult:
    """What the naive champion does on a joker: takes the polite surface at face value —
    sentiment flattens toward neutral and the escalation flag flips. Deterministic, and
    guaranteed to differ from expected on exactly two label fields. Public (with
    faithful_reply/build_jobs/write_cassettes) so the promotion tests exercise the same
    fabrication rule that produced the committed cassettes."""
    labels = ticket.expected.model_dump()
    labels["sentiment"] = "neutral" if ticket.expected.sentiment != "neutral" else "positive"
    labels["needs_human"] = not ticket.expected.needs_human
    return TriageResult(**labels, draft_reply=_draft(ticket.expected.category))


def build_jobs(
    tickets: list[Ticket], replies: dict[str, TriageResult], golden: list[GoldenTicket]
) -> list[Job]:
    """Every cassette we want to exist: (ticket, alias -> fabricated reply)."""
    jobs: list[Job] = [(t, {CHAMPION: replies[t.id], CHALLENGER: replies[t.id]}) for t in tickets]
    for g in golden:
        faithful = faithful_reply(g)
        jobs.append(
            (g, {CHAMPION: degraded_reply(g) if g.joker else faithful, CHALLENGER: faithful})
        )
    return jobs


def write_cassettes(client, jobs: list[Job], model: str, cassettes_dir: Path) -> int:
    """Write one cassette per (job, prompt alias) through the exact key path route() uses.
    The single authoring protocol shared by this script and the promotion tests."""
    written = 0
    for alias in (CHAMPION, CHALLENGER):
        prompt = load_triage_prompt(client, alias)
        for ticket, reply_by_alias in jobs:
            messages = format_for_ticket(prompt, ticket)
            key = cassette_key(model, messages)
            existing = load(cassettes_dir, key)
            if existing is not None and ("usage" in existing or "cost_usd" in existing):
                print(
                    f"Skipping {ticket.id} ({alias}): live-recorded cassette exists "
                    f"({key[:12]}…) — a fabrication never clobbers a paid recording"
                )
                continue
            save(
                cassettes_dir,
                key,
                model,
                messages,
                {"content": reply_by_alias[alias].model_dump_json()},
            )
            written += 1
    return written


def main(argv: list[str]) -> int:
    target = argv[0] if argv else "DW-001"
    tier = argv[1] if len(argv) > 1 else "cheap"
    settings = get_settings()

    tickets = load_tickets(settings.tickets_path) + load_tickets(settings.tickets_postrelease_path)
    replies = load_replies(settings.replies_path)
    missing = [t.id for t in tickets if t.id not in replies]
    if missing:
        print(
            f"No fabricated reply for {missing} in {settings.replies_path}. Add them, or "
            "record live (LLM_MODE=record, costs money, rule 4).",
            file=sys.stderr,
        )
        return 1

    golden: list[GoldenTicket] = []
    if settings.golden_path.exists():
        golden = load_golden(settings.golden_path)
    else:
        print(
            f"Golden set missing ({settings.golden_path}) — golden cassettes skipped; "
            "run `uv run dvc pull` to author them (make promote needs them).",
            file=sys.stderr,
        )

    jobs = build_jobs(tickets, replies, golden)
    if target != "--all":
        jobs = [job for job in jobs if job[0].id == target]
        if not jobs:
            print(f"No ticket with id '{target}' in the fixtures or golden set", file=sys.stderr)
            return 1

    # Throwaway offline registry: same sync, same prompts, same messages as the live flow.
    # dl-lite: cassettes cover the CODE templates; a second-generation challenger (promoted
    # champion whose text left the code) would need the live registry's alias targets instead.
    with tempfile.TemporaryDirectory() as tmp:
        offline = settings.model_copy(
            update={"mlflow_tracking_uri": f"sqlite:///{Path(tmp) / 'reg.db'}"}
        )
        client = open_registry(offline)
        sync_prompts(client)
        model = resolve_model(tier, settings.tiers_path)
        written = write_cassettes(client, jobs, model, settings.cassettes_dir)
        print(f"{written} cassettes written ({len(jobs)} tickets x 2 prompts, {tier} -> {model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
