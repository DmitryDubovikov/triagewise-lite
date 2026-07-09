"""Sync the triage prompt into the MLflow Prompt Registry — for the demo / a real run.

    make up                 # MLflow server on localhost:5050
    python -m scripts.register_prompt

Seeds the registry from the templates in app/persistence/prompts.py: the challenger alias is
code-owned and follows the challenger template; the champion alias is bootstrap-only — once it
exists it belongs to the promotion loop (iter 6a), so re-running never rolls a swap back and
never piles up versions. Talks to the registry only — NO LLM call, so it costs nothing.
"""

from __future__ import annotations

from app.config import get_settings
from app.persistence.prompts import TRIAGE_PROMPT_NAME, open_registry, sync_prompts


def main() -> int:
    settings = get_settings()
    client = open_registry(settings)
    synced = sync_prompts(client)

    uri = settings.mlflow_tracking_uri
    print(f"Synced prompt '{TRIAGE_PROMPT_NAME}' to MLflow registry at {uri}")
    for alias, result in synced.items():
        state = "registered new version" if result.created else "unchanged, alias confirmed"
        print(f"  prompts:/{TRIAGE_PROMPT_NAME}@{alias} -> v{result.version}  ({state})")
    print()
    print("See the stored template text with:")
    print(f"  uv run python -m scripts.show_prompt {next(iter(synced), 'champion')}")
    print(f"  or open the MLflow UI: {uri}  (Prompts -> {TRIAGE_PROMPT_NAME})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
