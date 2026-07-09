"""Thin promotion transport (CLAUDE.md rule 6): one manual turn of the evaluation loop.

    make promote        # replay by default -> offline, $0, runs on the derived golden cassettes

Scores champion vs challenger on the golden set, applies the strict gate, swaps the champion
alias in the MLflow registry on a challenger win, and verifies the result in the store
(rule 8). Idempotent: after a swap both aliases point at the same version, the strict gate
finds no winner, and a re-run is a no-op — the alias doesn't drift, versions don't pile up.

Also home to the pieces shared with the scheduled transport (app/cli/loop.py): run_turn
(boundary work + the loop turn, raising operator-hinted errors) and print_report — so the
two tellings of the same turn can't drift apart.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.config import Settings, get_settings
from app.persistence.prompts import CHAMPION, TRIAGE_PROMPT_NAME, open_registry
from app.persistence.tickets import load_golden
from app.workflow.promotion_flow import PromotionReport, run_promotion


async def run_turn(settings: Settings) -> tuple[PromotionReport, int]:
    """One gate turn from Settings: golden + registry boundary, then the 6a loop body.

    Failures carry operator hints instead of raw traces: FileNotFoundError (golden missing,
    dvc) and RuntimeError (registry not ready, make up). The manual transport maps them to
    stderr + exit 1; the scheduled one lets them fail the tick. Returns the report and the
    golden count (for print_report)."""
    if not settings.golden_path.exists():
        raise FileNotFoundError(
            f"Golden set missing: {settings.golden_path} — run `uv run dvc pull`"
        )
    golden = load_golden(settings.golden_path)
    client = open_registry(settings)

    from mlflow.exceptions import MlflowException  # lazy, like everywhere mlflow is touched

    try:
        report = await run_promotion(client, golden, settings=settings)
    except MlflowException as exc:
        raise RuntimeError(
            f"Registry not ready: {exc}\nRun `make up` and "
            "`uv run python -m scripts.register_prompt` first."
        ) from exc
    return report, len(golden)


def print_report(report: PromotionReport, *, golden_count: int, mode: str) -> None:
    """Render one gate turn — shared by the manual (promote) and scheduled (loop) transports."""
    print(f"Promotion gate over {golden_count} golden tickets (mode={mode}):")
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


def main() -> int:
    # Transport configures logging; the access layer just logs (SLO lines land on stderr).
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    settings = get_settings()
    try:
        report, golden_count = asyncio.run(run_turn(settings))
    except (FileNotFoundError, RuntimeError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print_report(report, golden_count=golden_count, mode=settings.llm_mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
