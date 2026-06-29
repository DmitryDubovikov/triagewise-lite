"""Triage domain — pure schema + parsing, no I/O (CLAUDE.md rule 6).

The output shape is FROZEN (rule 3): no fields beyond these five, ever. Scale is more
tickets, not more fields.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

Priority = Literal["low", "medium", "high", "urgent"]
Sentiment = Literal["negative", "neutral", "positive"]


class Ticket(BaseModel):
    id: str
    subject: str
    body: str


class TriageResult(BaseModel):
    category: str
    priority: Priority
    sentiment: Sentiment
    needs_human: bool
    draft_reply: str


def parse_triage(content: str) -> TriageResult:
    """Parse the LLM's JSON text into a validated TriageResult.

    Tolerates a ```json fenced block, since models like to wrap output.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json") :]
    return TriageResult.model_validate(json.loads(text.strip()))
