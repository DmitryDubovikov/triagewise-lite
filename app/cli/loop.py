"""Continuous-evaluation transport (iter 6b): the 6a promotion turn on a Prefect schedule.

    make loop           # replay by default -> offline, $0; Ctrl-C stops the runner

Prefect here is scaffolding from sentiment-mlops (rule 2). `serve()` registers the flow and
its interval schedule on the Compose Prefect server (in Prefect 3 scheduling is strictly
server-side) and keeps polling as the runner; the ticks themselves execute HERE, on the
host — the container never runs triage and never reaches OpenAI (execution boundary). Each
scheduled run is a fresh transport boundary: it re-reads Settings, re-opens the registry
handle and replays the same derived golden cassettes as `make promote`; the loop body
itself stays in workflow/promotion_flow. Idempotence is inherited from 6a: once the
challenger is promoted every further tick is a no-op (strict gate, alias assignment), so
the schedule can run forever without drifting the alias or piling up versions.
"""

from __future__ import annotations

import logging
import sys

from prefect import flow

from app.cli.promote import print_report, run_turn
from app.config import LOOP_DEPLOYMENT, LOOP_FLOW, get_settings
from app.workflow.promotion_flow import PromotionReport


@flow(name=LOOP_FLOW, log_prints=True)
async def continuous_evaluation() -> PromotionReport:
    """One scheduled turn: eval champion vs challenger -> gate -> swap -> verify in store.

    Deliberately parameterless: a scheduled run has no caller — the boundary re-reads env
    (Settings) itself, and nothing non-JSON (registry handles, secrets) leaks into the
    deployment's parameter schema on the server. Tests aim env at a throwaway registry and
    call `.fn()` directly — no Prefect API involved."""
    # Transport-configures-logging, tick edition: the run lives in a runner subprocess where
    # prefect owns the root logger (WARNING; basicConfig would be a no-op there). Opt app.*
    # into INFO so the access-layer SLO lines (tier+cost, iter 3) survive; PREFECT_ENV's
    # EXTRA_LOGGERS=app then ships them into the flow-run logs.
    logging.getLogger("app").setLevel(logging.INFO)
    settings = get_settings()
    # run_turn raises with operator hints (dvc pull / make up) — they fail the tick loud.
    report, golden_count = await run_turn(settings)
    print_report(report, golden_count=golden_count, mode=settings.llm_mode)
    return report


def main() -> int:
    from prefect.settings import PREFECT_API_URL

    if not PREFECT_API_URL.value():
        # Without an API URL prefect falls back to an ephemeral server, which deliberately
        # ships without the scheduler — serve() would look alive but no tick would ever come.
        print(
            "PREFECT_API_URL is not set — schedules are server-side in Prefect 3; "
            "use `make loop` (it aims the runner at the Compose server)",
            file=sys.stderr,
        )
        return 1
    settings = get_settings()
    print(
        f"continuous-evaluation loop: every {settings.loop_interval_seconds}s "
        f"(mode={settings.llm_mode}) — Ctrl-C to stop"
    )
    continuous_evaluation.serve(name=LOOP_DEPLOYMENT, interval=settings.loop_interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
