"""Happy-path smoke: route("cheap", ticket) in replay returns a parsed TriageResult, offline.

This is the iter-0 done-gate. Tests run in replay by default (tech-decisions) — never the network.
"""

from __future__ import annotations

import asyncio
from typing import get_args

import pytest

from app.config import Settings
from app.domain.triage import Priority, Sentiment, TriageResult
from app.llm.tiers import load_tiers
from app.persistence.tickets import load_tickets
from app.workflow.triage_flow import triage_ticket


def test_route_cheap_replay_smoke():
    settings = Settings(llm_mode="replay")
    ticket = load_tickets(settings.tickets_path)[0]  # DW-001, which we authored a cassette for
    result = asyncio.run(triage_ticket(ticket, tier="cheap", settings=settings))

    assert isinstance(result, TriageResult)
    assert result.priority in get_args(Priority)
    assert result.sentiment in get_args(Sentiment)
    assert result.draft_reply


def test_replay_without_cassette_errors_offline():
    """No cassette in replay -> clear error, never a silent network call (rule 4)."""
    settings = Settings(llm_mode="replay")
    ticket = load_tickets(settings.tickets_path)[1]  # DW-002 has no cassette
    with pytest.raises(FileNotFoundError):
        asyncio.run(triage_ticket(ticket, tier="cheap", settings=settings))


def test_pin_gate_rejects_floating_alias(tmp_path):
    bad = tmp_path / "bad-tiers.yaml"
    bad.write_text("tiers:\n  cheap: gpt-4.1-nano\n")
    load_tiers.cache_clear()
    with pytest.raises(ValueError, match="dated snapshot"):
        load_tiers(bad)
    load_tiers.cache_clear()
