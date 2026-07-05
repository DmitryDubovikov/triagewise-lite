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
from app.observability.phoenix import SPAN_NAME

BASELINE = "base"
CANDIDATE = "postrelease"


def main() -> int:
    from phoenix.client import Client  # external harness client, scripts-only

    settings = get_settings()
    client = Client(base_url=settings.phoenix_endpoint)
    spans = client.spans.get_spans(
        project_identifier=settings.phoenix_project, name=SPAN_NAME, limit=1000
    )
    if len(spans) == 1000:
        print(
            "warning: span fetch hit limit=1000 — sample truncated, verdict may be unreliable",
            file=sys.stderr,
        )

    rows = []
    for span in spans:
        # phoenix.client returns attributes as one flat dict with dotted keys.
        attrs = span.get("attributes") or {}
        batch, category = attrs.get("triage.batch"), attrs.get("triage.category")
        if batch is not None and category is not None:
            rows.append((str(batch), str(category)))
    if not rows:
        print(
            f"No traced triage spans with batch+category in project "
            f"'{settings.phoenix_project}' — run `make traffic` first (PHOENIX_ENABLED=1).",
            file=sys.stderr,
        )
        return 1

    report = category_drift(rows, baseline=BASELINE, candidate=CANDIDATE)
    print(report.model_dump_json(indent=2))
    if not report.drifted:
        print(f"no categorical drift between '{BASELINE}' and '{CANDIDATE}'", file=sys.stderr)
        return 1
    print(f"DRIFT: new categories in '{CANDIDATE}': {', '.join(report.new_categories)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
