"""Online LLM-as-judge — the phoenix.evals harness (iter 5b).

The judge OWNS its LLM call (the tech-decisions exception, like promptfoo): it does not go
through route()/cassettes, so every run is live money and is gated behind an explicit go
(rule 4, `make judge`). The model is still resolved from llm-tiers.yaml via JUDGE_TIER —
no model name in code. `client="openai"` pins the harness to the bare OpenAI SDK client so
it never routes through litellm (rule 5's discipline stays confined to our router), and
key/base_url are passed explicitly from Settings, never ambient env.

phoenix.evals is imported lazily inside the runner: replay paths, tests and CI never load it.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.domain.judge import JudgeCandidate, JudgeVerdict
from app.llm.tiers import resolve_model
from app.observability.phoenix import JUDGE_ANNOTATION

logger = logging.getLogger(__name__)

_CHOICES = {"correct": 1.0, "incorrect": 0.0}

_TEMPLATE = """You are auditing the triage of Driftwood (a SaaS task-tracker) support tickets.

Ticket:
{ticket}

Triage output (JSON: category, priority, sentiment, needs_human, draft_reply):
{triage}

Is this triage correct? "correct" means the category plausibly fits the ticket, the priority
is sensible for the reported impact, and the sentiment matches the customer's actual tone
(watch for negativity hidden under politeness). Otherwise answer "incorrect".
"""


def judge_candidates(candidates: list[JudgeCandidate], settings: Settings) -> list[JudgeVerdict]:
    """Judge sampled spans one by one at JUDGE_TIER. LIVE — costs money on every call."""
    from phoenix.evals import LLM, create_classifier  # lazy: only the live judge path loads evals

    client_kwargs: dict[str, Any] = {}
    if settings.openai_api_key is not None:
        client_kwargs["api_key"] = settings.openai_api_key.get_secret_value()
    if settings.openai_base_url is not None:
        client_kwargs["base_url"] = settings.openai_base_url
    llm = LLM(
        provider="openai",
        client="openai",
        model=resolve_model(settings.judge_tier, settings.tiers_path),
        **client_kwargs,
    )
    evaluator = create_classifier(
        name=JUDGE_ANNOTATION, prompt_template=_TEMPLATE, llm=llm, choices=_CHOICES
    )

    verdicts: list[JudgeVerdict] = []
    for candidate in candidates:
        try:
            score = evaluator.evaluate(
                {"ticket": candidate.ticket_text, "triage": candidate.triage_json}
            )[0]
        except Exception:
            # One failed judgement (network, 429, unparsable verdict) must not lose the
            # verdicts already paid for: skip this span — unannotated, it stays a candidate
            # for the next run — and keep judging the rest.
            logger.warning("judge failed on span %s — skipping", candidate.span_id, exc_info=True)
            continue
        if score.label is None:  # evaluate() validates labels against choices; guard, don't lie
            logger.warning("judge returned no label for span %s — skipping", candidate.span_id)
            continue
        verdicts.append(
            JudgeVerdict(
                span_id=candidate.span_id,
                label=score.label,
                score=score.score,
                explanation=score.explanation,
            )
        )
    return verdicts
