"""Guards for the golden-set -> eval/ bridge (iter 2).

The golden set is DVC-versioned and absent in CI (local dir remote — no dvc pull there),
so these tests skip cleanly without it; locally they hold the line against the one known
risk of committing generated assets: silent drift between source and derivative.

These guard the *repo tree*, so paths come from default Settings (model_construct = field
defaults, no .env/env-var overrides): a transient TRIAGE_TIER export must not fail — or
silently re-aim — a check on committed files.
"""

from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.persistence.tickets import load_golden
from app.workflow.eval_assets import build_from_settings

DEFAULTS = Settings.model_construct()

pytestmark = pytest.mark.skipif(
    not DEFAULTS.golden_path.exists(),
    reason="golden set not present (dvc pull) — skipped in CI by design",
)


def test_golden_shape() -> None:
    golden = load_golden(DEFAULTS.golden_path)  # validation itself is the assertion
    assert len(golden) == 40
    assert len({t.id for t in golden}) == len(golden)
    assert sum(1 for t in golden if t.joker) == 8


def test_committed_assets_in_sync_with_golden() -> None:
    for rel, content in build_from_settings(DEFAULTS).items():
        committed = DEFAULTS.eval_dir / rel
        assert committed.read_text() == content, f"eval/{rel} is stale — run `make eval-build`"


def test_recorded_outputs_cover_golden() -> None:
    outputs = json.loads((DEFAULTS.eval_dir / "outputs.json").read_text())["outputs"]
    recorded_ids = sorted(entry["id"] for entry in outputs.values())
    golden_ids = sorted(t.id for t in load_golden(DEFAULTS.golden_path))
    assert recorded_ids == golden_ids, "eval/outputs.json is stale — run `make eval-record`"
