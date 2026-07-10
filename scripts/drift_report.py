"""Drift report — query Phoenix's span store, not its UI (CLAUDE.md rule 8).

    make drift-report        (after `make traffic` sent both batches)

Pulls traced triage spans over the Phoenix REST client, aggregates category distributions
per `triage.batch`, and prints the CategoryDrift verdict. Exit 0 = drift caught (the
post-release batch produced categories the baseline never did) — the iteration-5a
existence-gate, checked mechanically. Exit 1 = no drift visible (or no traced spans yet).
"""

from __future__ import annotations

import sys

from app.config import get_settings
from app.domain.drift import category_drift
from app.observability.phoenix import (
    BASELINE_BATCH,
    CANDIDATE_BATCH,
    batch_category_rows,
    fetch_triage_spans,
)


def main() -> int:
    from phoenix.client import Client  # external harness client, scripts-only

    settings = get_settings()
    client = Client(base_url=settings.phoenix_endpoint)
    spans, truncated = fetch_triage_spans(client, settings)
    if truncated:
        print(
            "warning: span fetch hit the page limit — sample truncated, verdict may be unreliable",
            file=sys.stderr,
        )

    rows = batch_category_rows(spans)
    if not rows:
        print(
            f"No traced triage spans with batch+category in project "
            f"'{settings.phoenix_project}' — run `make traffic` first (PHOENIX_ENABLED=1).",
            file=sys.stderr,
        )
        return 1

    report = category_drift(rows, baseline=BASELINE_BATCH, candidate=CANDIDATE_BATCH)
    print(report.model_dump_json(indent=2))
    if not report.drifted:
        print(
            f"no categorical drift between '{BASELINE_BATCH}' and '{CANDIDATE_BATCH}'",
            file=sys.stderr,
        )
        return 1
    print(f"DRIFT: new categories in '{CANDIDATE_BATCH}': {', '.join(report.new_categories)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
