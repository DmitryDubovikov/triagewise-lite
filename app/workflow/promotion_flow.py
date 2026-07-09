"""Promotion loop (iter 6a): re-eval both aliases on golden -> gate -> swap champion.

The manual core of continuous evaluation (the Prefect schedule wrapper is iter 6b). The
registry handle and the golden set come in from the transport boundary (CLAUDE.md rule 6);
every LLM exchange goes through route(), so in the default replay mode the whole loop runs
offline/$0 on the derived golden cassettes. After a (possible) swap the report re-reads the
champion alias from the store (rule 8: verify the store, not the UI) — and because prompt
loading is alias-fresh, any live process picks the new champion up on its next call
(hot-reload, no restart).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from app.config import Settings
from app.domain.promotion import score_triage, should_promote
from app.domain.triage import GoldenTicket
from app.persistence.prompts import CHALLENGER, CHAMPION, load_triage_prompt, promote_challenger
from app.workflow.triage_flow import triage_ticket

if TYPE_CHECKING:
    from mlflow import MlflowClient


class AliasScore(NamedTuple):
    """One side of the gate: which version an alias resolved to and how it scored."""

    alias: str
    version: int
    score: float


class PromotionReport(NamedTuple):
    champion: AliasScore
    challenger: AliasScore
    promoted: bool
    champion_version_after: int  # fresh store read after the (possible) swap, rule 8


async def evaluate_alias(
    client: MlflowClient,
    alias: str,
    golden: list[GoldenTicket],
    *,
    settings: Settings,
) -> AliasScore:
    """Mean label-match score of one prompt alias over the golden set, at the triage tier.

    Each ticket takes the same triage_ticket path production traffic takes (spans, cache,
    SLO log) — the gate measures exactly what a promoted prompt would do in prod."""
    version = load_triage_prompt(client, alias).version
    scores = []
    for ticket in golden:
        result = await triage_ticket(
            ticket, tier=settings.triage_tier, client=client, alias=alias, settings=settings
        )
        scores.append(score_triage(result, ticket.expected))
    return AliasScore(alias=alias, version=version, score=sum(scores) / len(scores))


async def run_promotion(
    client: MlflowClient, golden: list[GoldenTicket], *, settings: Settings
) -> PromotionReport:
    """One turn of the loop: eval both aliases, gate, swap on a strict challenger win."""
    if not golden:
        raise ValueError("empty golden set — nothing to evaluate the gate on")
    champion = await evaluate_alias(client, CHAMPION, golden, settings=settings)
    challenger = await evaluate_alias(client, CHALLENGER, golden, settings=settings)
    promoted = should_promote(champion.score, challenger.score)
    if promoted:
        promote_challenger(client, challenger.version)
    after = load_triage_prompt(client, CHAMPION).version
    return PromotionReport(
        champion=champion, challenger=challenger, promoted=promoted, champion_version_after=after
    )
