"""Thin online-judge transport (CLAUDE.md rule 6): sample traced traffic, judge, annotate.

    make judge        (explicit go — this is LIVE and costs money, rule 4)

Pulls traced triage spans from Phoenix, samples them (JUDGE_SAMPLE_RATE, deterministic per
ticket), judges each sampled span at JUDGE_TIER via phoenix.evals (the judge owns its call —
tech-decisions exception, like promptfoo) and writes verdicts back as span annotations, which
Phoenix shows next to the traces. Incremental: already-judged spans are skipped, so re-running
without new traffic is a no-op and $0.
"""

from __future__ import annotations

import logging
import sys

from app.config import get_settings
from app.observability.judge import judge_candidates
from app.workflow.judge_flow import judge_traffic


def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    settings = get_settings()
    if settings.openai_api_key is None:
        print(
            "The judge is a live LLM call (rule 4) — set OPENAI_API_KEY in .env first.",
            file=sys.stderr,
        )
        return 1

    from phoenix.client import Client  # lazy: only this transport talks to Phoenix

    client = Client(base_url=settings.phoenix_endpoint)
    report = judge_traffic(
        client, settings, runner=lambda candidates: judge_candidates(candidates, settings)
    )

    if report.truncated:
        print(
            "warning: span fetch hit the page limit — older spans were not considered",
            file=sys.stderr,
        )
    for verdict in report.verdicts:
        print(f"[{verdict.span_id}] {verdict.label}: {verdict.explanation}")
    print(
        f"{len(report.verdicts)} spans judged at tier={settings.judge_tier} "
        f"({report.spans_seen} traced, {report.already_judged} already judged, "
        f"sample_rate={settings.judge_sample_rate})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
