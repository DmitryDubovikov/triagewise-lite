"""The file-replay provider and the committed eval artifacts, as CI sees them.

promptfoo runs the provider under the system python3 (stdlib-only, outside the uv env);
here we import it by path and check the properties CI leans on: stable keys, loud misses,
a servable artifact — plus the sync guards that need no golden set and therefore MUST run
in CI (unlike tests/test_eval_assets.py): recorded model matches the configured provider,
and the committed prompt file matches the champion template in code.

Repo-tree guards use default Settings (model_construct — no .env/env-var overrides).
"""

from __future__ import annotations

import json

import yaml

from app.config import Settings
from app.workflow.eval_assets import load_replay_provider, render_prompt_file

DEFAULTS = Settings.model_construct()


def test_prompt_key_is_whitespace_and_order_insensitive() -> None:
    provider = load_replay_provider(DEFAULTS.eval_dir)
    a = provider.prompt_key('[{"role": "user", "content": "x"}]')
    b = provider.prompt_key('[ {"content":"x","role":"user"} ]')
    assert a == b


def test_unknown_prompt_is_a_loud_error() -> None:
    provider = load_replay_provider(DEFAULTS.eval_dir)
    result = provider.call_api('[{"role":"user","content":"never recorded"}]', {}, {})
    assert "error" in result
    assert "eval-record" in result["error"]  # the miss must say how to fix itself


def test_recorded_model_matches_configured_provider() -> None:
    """A tier/snapshot bump regenerates the config but can't touch outputs.json — without
    this check the gate would stay green replaying the old model's outputs (rule 4)."""
    config = yaml.safe_load((DEFAULTS.eval_dir / "promptfooconfig.yaml").read_text())
    configured = config["providers"][0]["id"]
    recorded = json.loads((DEFAULTS.eval_dir / "outputs.json").read_text())["model"]
    assert recorded == configured, (
        "eval/outputs.json was recorded with a different model — run `make eval-record`"
    )


def test_committed_prompt_matches_champion_template() -> None:
    """Editing TRIAGE_CHAMPION_TEMPLATE without `make eval-build` must not stay green:
    the gate would keep judging the stale committed prompt."""
    committed = (DEFAULTS.eval_dir / "prompts" / "champion.json").read_text()
    assert committed == render_prompt_file(), (
        "eval/prompts/champion.json is stale — run `make eval-build` (then `make eval-record`)"
    )


def test_committed_outputs_artifact_is_servable() -> None:
    outputs = json.loads((DEFAULTS.eval_dir / "outputs.json").read_text())["outputs"]
    assert outputs, "eval/outputs.json has no recorded outputs"
    for entry in outputs.values():
        assert entry["id"].startswith("GS-")
        assert entry["output"]
