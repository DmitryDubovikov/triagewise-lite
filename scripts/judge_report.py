"""Judge report — verify the judge's verdicts in Phoenix's store, not its UI (rule 8).

    make judge-report        (after `make judge` annotated sampled spans)

Pulls traced triage spans and their judge annotations over the Phoenix REST client and prints
label counts plus per-ticket verdicts. Exit 0 = at least one judge annotation exists (the
iteration-5b existence-gate, checked mechanically). Exit 1 = nothing judged yet.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from app.config import get_settings
from app.observability.phoenix import (
    JUDGE_ANNOTATION,
    fetch_judge_annotations,
    fetch_triage_spans,
)


def main() -> int:
    from phoenix.client import Client  # external harness client, scripts-only

    settings = get_settings()
    client = Client(base_url=settings.phoenix_endpoint)
    spans, truncated = fetch_triage_spans(client, settings)
    if truncated:
        print("warning: span fetch hit the page limit — report may be incomplete", file=sys.stderr)
    if not spans:
        print(
            f"No traced triage spans in project '{settings.phoenix_project}' — "
            "run `make traffic` first (PHOENIX_ENABLED=1).",
            file=sys.stderr,
        )
        return 1

    annotations = fetch_judge_annotations(client, settings, spans)
    if not annotations:
        print(
            f"No '{JUDGE_ANNOTATION}' annotations yet — run `make judge` (live, rule 4).",
            file=sys.stderr,
        )
        return 1

    ticket_by_span = {
        (span.get("context") or {}).get("span_id"): (span.get("attributes") or {}).get(
            "triage.ticket_id"
        )
        for span in spans
    }
    verdicts = []
    for a in annotations:
        result = a.get("result") or {}
        verdicts.append(
            {
                "ticket_id": ticket_by_span.get(a["span_id"]),
                "label": result.get("label"),
                "score": result.get("score"),
            }
        )
    report = {
        "annotation": JUDGE_ANNOTATION,
        "spans_traced": len(spans),
        "spans_judged": len(verdicts),
        "labels": dict(Counter(v["label"] for v in verdicts)),
        "verdicts": sorted(verdicts, key=lambda v: str(v["ticket_id"])),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
