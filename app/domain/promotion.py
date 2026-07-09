"""Promotion domain — pure gate math, no I/O (CLAUDE.md rule 6).

The promotion gate compares champion and challenger by label match against the golden set:
score = mean fraction of matched label fields (category, priority, sentiment, needs_human;
draft_reply is free text and has no reference answer). Strictly-greater is deliberate: a tie
keeps the incumbent, so re-running the loop after a swap (both aliases on the same version)
is a natural no-op.

Label match is the gate's *mechanism*, not an accuracy claim (existence-gate): on the derived
golden cassettes the score difference is fabricated by construction.
"""

from __future__ import annotations

from app.domain.triage import GoldenLabels, TriageResult

LABEL_FIELDS = tuple(GoldenLabels.model_fields)  # category, priority, sentiment, needs_human


def score_triage(result: TriageResult, expected: GoldenLabels) -> float:
    """Fraction of golden label fields the triage got right (0.0–1.0)."""
    matched = sum(getattr(result, field) == getattr(expected, field) for field in LABEL_FIELDS)
    return matched / len(LABEL_FIELDS)


def should_promote(champion_score: float, challenger_score: float) -> bool:
    """The gate: the challenger must strictly beat the champion; a tie keeps the incumbent."""
    return challenger_score > champion_score
