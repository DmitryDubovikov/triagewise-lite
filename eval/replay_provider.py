"""File-replay provider for the CI eval gate (promptfoo custom python provider).

promptfoo owns the live triage calls (tech-decisions); this provider is their offline half:
it serves outputs recorded by `make eval-record` from the committed eval/outputs.json.
Keys hash the rendered prompt, so any prompt-template change invalidates every entry and
the gate goes red on misses until someone re-records locally — stale outputs can never
silently keep CI green. Stdlib-only on purpose: promptfoo runs this with the system
python3, outside the uv env, so it must not import app/*.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

OUTPUTS_PATH = Path(__file__).resolve().parent / "outputs.json"

RECORD_HINT = "re-record with `make eval-record` (live, costs money — rule 4)"

# promptfoo keeps this module loaded in one persistent python process for the whole run,
# so the artifact is read once, not once per test.
_RECORDED: dict[str, Any] | None = None


def _recorded() -> dict[str, Any] | None:
    global _RECORDED
    if _RECORDED is None and OUTPUTS_PATH.exists():
        _RECORDED = json.loads(OUTPUTS_PATH.read_text())["outputs"]
    return _RECORDED


def prompt_key(prompt: str) -> str:
    """Hash the rendered prompt, whitespace-insensitively (chat prompts render as JSON)."""
    try:
        canon = json.dumps(json.loads(prompt), sort_keys=True, separators=(",", ":"))
    except ValueError:
        canon = prompt
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]


def call_api(prompt: str, options: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    recorded = _recorded()
    if recorded is None:
        return {"error": f"{OUTPUTS_PATH.name} missing — {RECORD_HINT}"}
    key = prompt_key(prompt)
    entry = recorded.get(key)
    if entry is None:
        return {"error": f"no recorded output (key {key}) — prompt changed? {RECORD_HINT}"}
    return {"output": entry["output"]}
