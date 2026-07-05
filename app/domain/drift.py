"""Drift decision — pure aggregation over (batch, category) observations, no I/O (rule 6).

Categorical distribution shift is the iteration-5a drift signal (existence-gate, not a
statistical test): the post-release batch produces a category the baseline batch never did.
The rows come from traced spans in Phoenix; pulling them is the script's job, deciding is ours.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from pydantic import BaseModel


class CategoryDrift(BaseModel):
    distributions: dict[str, dict[str, int]]  # batch -> category -> count
    new_categories: list[str]  # in candidate, absent from baseline
    drifted: bool


def category_drift(
    rows: Iterable[tuple[str, str]], *, baseline: str, candidate: str
) -> CategoryDrift:
    """rows = (batch_label, category) pairs. Counts are per batch, so re-running traffic
    (append-only traces) inflates counts but never flips the verdict."""
    dist: dict[str, Counter[str]] = defaultdict(Counter)
    for batch, category in rows:
        dist[batch][category] += 1
    new = sorted(set(dist.get(candidate, Counter())) - set(dist.get(baseline, Counter())))
    return CategoryDrift(
        distributions={batch: dict(counts) for batch, counts in sorted(dist.items())},
        new_categories=new,
        drifted=bool(new),
    )
