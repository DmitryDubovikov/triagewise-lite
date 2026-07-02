"""Happy-path smoke + prompt-registry existence gate (iter 1).

Triage now loads its prompt by alias from MLflow Prompt Registry. Tests run offline against a
throwaway sqlite registry (no server, no network) and in replay (no LLM), so the whole gate is $0.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import get_args

import pytest

from app.config import Settings
from app.domain.triage import Priority, Sentiment, TriageResult
from app.llm.tiers import load_tiers
from app.persistence.prompts import (
    CHALLENGER,
    CHAMPION,
    load_triage_prompt,
    open_registry,
    sync_prompts,
)
from app.persistence.tickets import load_tickets
from app.workflow.triage_flow import triage_ticket


@pytest.fixture
def registry(tmp_path: Path):
    """An offline sqlite-backed registry, synced with champion v1 + challenger v2."""
    settings = Settings(llm_mode="replay", mlflow_tracking_uri=f"sqlite:///{tmp_path / 'reg.db'}")
    client = open_registry(settings)
    synced = sync_prompts(client)
    versions = {alias: s.version for alias, s in synced.items()}
    return client, settings, versions


def test_triage_champion_replay_smoke(registry):
    """route('cheap', champion prompt) in replay -> parsed TriageResult, offline, $0."""
    client, settings, _ = registry
    ticket = load_tickets(settings.tickets_path)[0]  # DW-001, which we authored a cassette for
    result = asyncio.run(
        triage_ticket(ticket, tier="cheap", client=client, alias=CHAMPION, settings=settings)
    )

    assert isinstance(result, TriageResult)
    assert result.priority in get_args(Priority)
    assert result.sentiment in get_args(Sentiment)
    assert result.draft_reply


def test_champion_and_challenger_aliases_resolve(registry):
    """Verify in the store, not the UI (rule 8): both aliases point at distinct versions."""
    client, _, versions = registry
    champion = load_triage_prompt(client, CHAMPION)
    challenger = load_triage_prompt(client, CHALLENGER)

    assert champion.version == versions[CHAMPION]
    assert challenger.version == versions[CHALLENGER]
    assert champion.version != challenger.version


def test_sync_prompts_is_idempotent(registry):
    """Re-syncing an unchanged template creates no new version and moves no alias (idempotent)."""
    client, _, versions = registry
    resynced = sync_prompts(client)

    assert all(not s.created for s in resynced.values())  # nothing re-registered
    assert {a: s.version for a, s in resynced.items()} == versions  # versions/aliases unchanged


def test_replay_without_cassette_errors_offline(registry):
    """No cassette in replay -> clear error, never a silent network call (rule 4)."""
    client, settings, _ = registry
    ticket = load_tickets(settings.tickets_path)[1]  # DW-002 has no cassette
    with pytest.raises(FileNotFoundError):
        asyncio.run(triage_ticket(ticket, tier="cheap", client=client, settings=settings))


def test_pin_gate_rejects_floating_alias(tmp_path):
    bad = tmp_path / "bad-tiers.yaml"
    bad.write_text("tiers:\n  cheap: gpt-4.1-nano\n")
    load_tiers.cache_clear()
    with pytest.raises(ValueError, match="dated snapshot"):
        load_tiers(bad)
    load_tiers.cache_clear()
