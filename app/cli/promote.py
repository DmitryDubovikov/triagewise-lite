"""Thin promotion transport (CLAUDE.md rule 6): one manual turn of the evaluation loop.

    make promote        # replay by default -> offline, $0, runs on the derived golden cassettes

Scores champion vs challenger on the golden set, applies the strict gate, swaps the champion
alias in the MLflow registry on a challenger win, and verifies the result in the store
(rule 8). Idempotent: after a swap both aliases point at the same version, the strict gate
finds no winner, and a re-run is a no-op — the alias doesn't drift, versions don't pile up.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.config import get_settings
from app.persistence.prompts import CHAMPION, TRIAGE_PROMPT_NAME, open_registry
from app.persistence.tickets import load_golden
from app.workflow.promotion_flow import run_promotion


def main() -> int:
    # Transport configures logging; the access layer just logs (SLO lines land on stderr).
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    settings = get_settings()
    if not settings.golden_path.exists():
        print(
            f"Golden set missing: {settings.golden_path} — run `uv run dvc pull`",
            file=sys.stderr,
        )
        return 1
    golden = load_golden(settings.golden_path)
    client = open_registry(settings)

    from mlflow.exceptions import MlflowException  # lazy, like everywhere mlflow is touched

    try:
        report = asyncio.run(run_promotion(client, golden, settings=settings))
    except MlflowException as exc:
        print(
            f"Registry not ready: {exc}\nRun `make up` and "
            "`uv run python -m scripts.register_prompt` first.",
            file=sys.stderr,
        )
        return 1

    print(f"Promotion gate over {len(golden)} golden tickets (mode={settings.llm_mode}):")
    for side in (report.champion, report.challenger):
        print(f"  {side.alias:<10} v{side.version}  score={side.score:.3f}")
    if report.promoted:
        print(f"gate: challenger wins -> champion alias swapped to v{report.challenger.version}")
    else:
        print("gate: challenger does not strictly beat champion -> no swap")
    print(
        f"verify (store, rule 8): prompts:/{TRIAGE_PROMPT_NAME}@{CHAMPION} -> "
        f"v{report.champion_version_after}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
