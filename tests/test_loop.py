"""Continuous-evaluation flow existence gate (iter 6b): the Prefect wrapper runs the same
promotion turn, offline/$0. Tests call the undecorated `.fn()` directly — the Prefect API
(server or ephemeral) never starts here; the schedule itself is exercised by `make loop`,
not pytest. The flow is deliberately parameterless (a scheduled run has no caller), so the
fixture injects the throwaway registry the honest way: through env, the same channel a
scheduled run reads.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.cli.loop import continuous_evaluation
from app.config import get_settings
from app.persistence.prompts import CHALLENGER, CHAMPION, load_triage_prompt
from tests.test_promotion import GOLDEN, seed_registry


@pytest.fixture
def flow_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The shared seed_registry recipe, exposed to the flow via env — plus the golden set
    written to disk, since the boundary loads it from settings.golden_path."""
    golden_path = tmp_path / "golden.jsonl"
    golden_path.write_text("\n".join(json.dumps(t.model_dump(exclude_none=True)) for t in GOLDEN))
    env = {
        "LLM_MODE": "replay",
        "MLFLOW_TRACKING_URI": f"sqlite:///{tmp_path / 'reg.db'}",
        "CASSETTES_DIR": str(tmp_path / "cassettes"),
        "LLM_LOG_PATH": str(tmp_path / "llm_calls.jsonl"),
        "GOLDEN_PATH": str(golden_path),
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    yield seed_registry(settings), settings
    get_settings.cache_clear()  # monkeypatch restores env; don't leak the cached tmp Settings


def test_flow_run_swaps_champion_in_store(flow_env):
    client, _ = flow_env
    challenger_version = load_triage_prompt(client, CHALLENGER).version

    report = asyncio.run(continuous_evaluation.fn())

    assert report.promoted
    # Verify in the store, not the report (rule 8): the scheduled turn moved the alias.
    assert load_triage_prompt(client, CHAMPION).version == challenger_version


def test_flow_tick_after_swap_is_noop(flow_env):
    """The schedule reruns forever — every tick after the swap must leave the store alone."""
    client, _ = flow_env
    asyncio.run(continuous_evaluation.fn())
    promoted_version = load_triage_prompt(client, CHAMPION).version

    rerun = asyncio.run(continuous_evaluation.fn())

    assert not rerun.promoted
    assert load_triage_prompt(client, CHAMPION).version == promoted_version


def test_flow_fails_loud_without_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A scheduled run with no golden set must fail the tick with the dvc hint, not eval
    an empty set and 'promote' on garbage. No flow_env: the turn dies at the golden check,
    before it would ever touch a registry — seeding one here would be pure setup waste."""
    monkeypatch.setenv("GOLDEN_PATH", str(tmp_path / "absent.jsonl"))
    get_settings.cache_clear()
    try:
        with pytest.raises(FileNotFoundError, match="dvc pull"):
            asyncio.run(continuous_evaluation.fn())
    finally:
        get_settings.cache_clear()


def test_flow_signature_stays_json_clean():
    """serve() publishes the flow's parameter schema to the Prefect server — nothing
    non-JSON (registry handles, Settings with secrets) may sit in the signature, and a
    string annotation must not break subprocess parameter validation (the pydantic
    'not fully defined' failure a scheduled run once died on)."""
    validated = continuous_evaluation.validate_parameters({})
    assert validated == {}
