"""Distill a live promptfoo run into the committed replay artifact eval/outputs.json.

    uv run python -m scripts.extract_eval_outputs

Second half of `make eval-record` (the first half is promptfoo's own live eval writing
eval/.record-results.json). Keys come from replay_provider.prompt_key over promptfoo's
rendered prompt — the same string the provider receives at replay time — so record and
replay can't drift. Deterministic given the same record results: sorted keys, stable dump.
"""

from __future__ import annotations

import json

from app.config import get_settings
from app.workflow.eval_assets import load_replay_provider


def main() -> int:
    settings = get_settings()
    record_path = settings.eval_dir / ".record-results.json"
    provider = load_replay_provider(settings.eval_dir)

    results = json.loads(record_path.read_text())["results"]["results"]
    outputs: dict[str, dict[str, str]] = {}
    for r in results:
        description = r["testCase"]["description"]
        output = (r.get("response") or {}).get("output")
        if output is None:
            raise SystemExit(
                f"record run has no output for '{description}' — not extracting "
                "a partial artifact; fix the live run first"
            )
        key = provider.prompt_key(r["prompt"]["raw"])
        outputs[key] = {"id": description.split(":")[0], "output": output}

    doc = {
        "_generated": "by scripts/extract_eval_outputs.py (make eval-record) — do not edit; "
        "the committed replay artifact for the CI eval gate",
        "model": results[0]["provider"]["id"],
        "outputs": dict(sorted(outputs.items())),
    }
    target = settings.eval_dir / "outputs.json"
    target.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {target} ({len(outputs)} recorded outputs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
