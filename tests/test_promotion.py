"""Promotion-loop existence gate (iter 6a): eval -> gate -> swap -> hot-reload, offline/$0.

Runs against a throwaway sqlite registry and a tmp cassette dir authored through the same
build_jobs/write_cassettes recipe as the committed cassettes: the challenger's fabricated
replies match the golden labels, the champion's miss the joker — so the strict gate has
something to decide, deterministically, with no LLM anywhere.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.domain.promotion import score_triage, should_promote
from app.domain.triage import GoldenLabels, GoldenTicket, TriageResult
from app.llm.cassettes import cassette_key, load
from app.llm.tiers import resolve_model
from app.persistence.prompts import (
    CHALLENGER,
    CHAMPION,
    format_for_ticket,
    load_triage_prompt,
    open_registry,
    sync_prompts,
)
from app.persistence.tickets import load_golden
from app.workflow.promotion_flow import run_promotion
from app.workflow.triage_flow import triage_ticket
from scripts.author_cassette import build_jobs, write_cassettes

GOLDEN = [
    GoldenTicket(
        id="GT-1",
        subject="App crashes when exporting a board",
        body="Every export to CSV crashes the tab. Started after the last update.",
        expected=GoldenLabels(
            category="bug", priority="high", sentiment="negative", needs_human=False
        ),
    ),
    GoldenTicket(
        id="GT-2",
        subject="Loving the new boards",
        body="The new board view is great. Any chance of a dark mode for it?",
        expected=GoldenLabels(
            category="feature_request", priority="low", sentiment="positive", needs_human=False
        ),
    ),
    GoldenTicket(
        id="GT-3",
        subject="Thanks so much for all your help so far",
        body="Really appreciate the support team. That said, nothing has worked for two weeks "
        "and we are evaluating alternatives.",
        expected=GoldenLabels(
            category="bug", priority="high", sentiment="negative", needs_human=True
        ),
        joker="hidden_negative",
    ),
]


@pytest.fixture
def loop_env(tmp_path: Path):
    """Synced sqlite registry + cassettes for both prompts over the inline golden set,
    authored through the exact recipe the committed cassettes come from (one rule, one home)."""
    settings = Settings(
        llm_mode="replay",
        mlflow_tracking_uri=f"sqlite:///{tmp_path / 'reg.db'}",
        cassettes_dir=tmp_path / "cassettes",
        llm_log_path=tmp_path / "llm_calls.jsonl",
    )
    client = open_registry(settings)
    sync_prompts(client)
    model = resolve_model(settings.triage_tier, settings.tiers_path)
    write_cassettes(client, build_jobs([], {}, GOLDEN), model, settings.cassettes_dir)
    return client, settings


def test_score_triage_counts_matched_label_fields():
    expected = GOLDEN[0].expected
    perfect = TriageResult(**expected.model_dump(), draft_reply="anything")
    assert score_triage(perfect, expected) == 1.0
    half_off = perfect.model_copy(update={"sentiment": "neutral", "needs_human": True})
    assert score_triage(half_off, expected) == 0.5


def test_gate_is_strict():
    assert should_promote(0.8, 0.9)
    assert not should_promote(0.9, 0.9)  # a tie keeps the incumbent
    assert not should_promote(0.9, 0.8)


def test_promotion_swaps_champion_alias(loop_env):
    client, settings = loop_env
    challenger_version = load_triage_prompt(client, CHALLENGER).version
    report = asyncio.run(run_promotion(client, GOLDEN, settings=settings))

    assert report.challenger.score > report.champion.score
    assert report.promoted
    # Verify in the store, not the report (rule 8): champion now points at challenger's version.
    assert load_triage_prompt(client, CHAMPION).version == challenger_version
    assert report.champion_version_after == challenger_version


def test_promotion_rerun_is_noop(loop_env):
    client, settings = loop_env
    asyncio.run(run_promotion(client, GOLDEN, settings=settings))
    promoted_version = load_triage_prompt(client, CHAMPION).version

    rerun = asyncio.run(run_promotion(client, GOLDEN, settings=settings))
    assert not rerun.promoted  # equal scores -> the strict gate keeps the incumbent
    assert load_triage_prompt(client, CHAMPION).version == promoted_version


def test_sync_after_promotion_does_not_roll_back(loop_env):
    """Re-seeding from code must not undo the swap: the promotion loop owns the champion alias."""
    client, settings = loop_env
    asyncio.run(run_promotion(client, GOLDEN, settings=settings))
    promoted_version = load_triage_prompt(client, CHAMPION).version

    synced = sync_prompts(client)
    assert load_triage_prompt(client, CHAMPION).version == promoted_version
    assert all(not s.created for s in synced.values())  # and no version bloat


def test_hot_reload_same_process(loop_env):
    """One process, one registry handle: triage before the swap answers with the champion's
    degraded reply, after the swap with the challenger's — no client reopen, no restart."""
    client, settings = loop_env
    joker = GOLDEN[2]

    before = asyncio.run(
        triage_ticket(joker, tier=settings.triage_tier, client=client, settings=settings)
    )
    assert before.sentiment == "neutral"  # champion misses the hidden negative

    asyncio.run(run_promotion(client, GOLDEN, settings=settings))

    after = asyncio.run(
        triage_ticket(joker, tier=settings.triage_tier, client=client, settings=settings)
    )
    assert after.sentiment == "negative"  # the next call already speaks the promoted prompt


@pytest.mark.skipif(
    not Settings.model_construct().golden_path.exists(),
    reason="golden set not present (dvc pull) — skipped in CI by design",
)
def test_committed_cassettes_cover_golden_for_both_prompts(tmp_path: Path):
    """`make promote` replays the real golden set: every ticket needs a committed cassette
    under BOTH templates, or the loop dies mid-eval. Stale here = re-run author_cassette.
    model_construct: this checks the committed tree, so transient env (TRIAGE_TIER) must
    not re-aim it (the test_eval_assets pattern)."""
    settings = Settings.model_construct(mlflow_tracking_uri=f"sqlite:///{tmp_path / 'reg.db'}")
    client = open_registry(settings)
    sync_prompts(client)
    golden = load_golden(settings.golden_path)
    model = resolve_model(settings.triage_tier, settings.tiers_path)

    missing = []
    for alias in (CHAMPION, CHALLENGER):
        prompt = load_triage_prompt(client, alias)
        for ticket in golden:
            key = cassette_key(model, format_for_ticket(prompt, ticket))
            if load(settings.cassettes_dir, key) is None:
                missing.append((alias, ticket.id))
    assert not missing, (
        f"derived cassettes missing/stale — run `uv run python -m scripts.author_cassette --all`:"
        f" {missing[:5]}"
    )
