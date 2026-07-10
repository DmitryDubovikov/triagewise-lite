"""Tolerant JSONL reading — one home for the log family's read dialect (iter 7).

Every JSONL log in this project (SLO calls, promotion turns) degrades the same way: a blank,
torn or foreign line is skipped, never fatal — readers work with the newest records they can
still parse. This generator is that policy, written once; last_promotion and the dashboard's
slo_summary fold over it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

M = TypeVar("M", bound=BaseModel)


def iter_records(path: Path, model: type[M]) -> Iterator[M]:
    """Yield every parseable `model` record from a JSONL file ([] when it doesn't exist)."""
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            if not line.strip():
                continue
            try:
                yield model.model_validate_json(line)
            except ValidationError:
                continue
