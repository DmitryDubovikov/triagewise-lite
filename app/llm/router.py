"""route("tier", ...) — the single LLM chokepoint (CLAUDE.md rule 6).

Layers call route() and never name a model or import an SDK directly. Cassette mode decides
whether we touch the network: replay is offline/$0 (default); record/live cost money (rule 4).

Access layer (iter 3): every call is measured — latency + cost (litellm.completion_cost on
record/live; the recorded cassette value on replay) — and appended to the SLO log. Latency is
always this process's wall time: on replay that's the cassette read, and the record's
mode="replay" is what tells a reader not to mistake it for a network round-trip.

Semantic cache (iter 4, opt-in via Settings): a close-enough repeat is served straight from
the cache — before cassettes, before the network — and logged as cache=hit; a miss goes the
normal path below and is stored. The mechanics live behind semcache.open_session(); route()
only sequences hit/miss/off. The embedder is injectable; the default (fastembed) is as lazy
as litellm.

LiteLLM discipline (rule 5): SDK-only (never Proxy), lazy import, telemetry off, no callbacks,
keys/base_url only via Settings. In replay the SDK is never imported at all.
"""

from __future__ import annotations

import time

from app.config import Settings, get_settings
from app.llm import cassettes, semcache, slo
from app.llm.cassettes import Messages
from app.llm.slo import CostSource
from app.llm.tiers import resolve_model


async def route(
    tier: str,
    messages: Messages,
    *,
    settings: Settings | None = None,
    embedder: semcache.Embedder | None = None,
) -> str:
    """Resolve tier -> model, run the exchange per LLM_MODE, return the assistant text."""
    settings = settings or get_settings()
    model = resolve_model(tier, settings.tiers_path)

    start = time.perf_counter()
    cost_usd: float = 0.0
    cost_source: CostSource = "none"

    cache = semcache.open_session(settings, model, messages, embedder)
    if cache.content is not None:
        content = cache.content
    elif settings.llm_mode == "replay":
        key = cassettes.cassette_key(model, messages)
        response = cassettes.load(settings.cassettes_dir, key)
        if response is None:
            raise FileNotFoundError(
                f"No cassette for tier '{tier}' (model {model}, key {key[:12]}…) in "
                f"{settings.cassettes_dir}. replay never hits the network; record it explicitly "
                "(LLM_MODE=record costs money, rule 4)."
            )
        content = response["content"]
        if "cost_usd" in response:  # what the recorded call cost; actual spend here is $0
            cost_usd, cost_source = float(response["cost_usd"]), "cassette"
    else:
        content, usage, live_cost = await _live_completion(model, messages, settings)
        if live_cost is not None:
            cost_usd, cost_source = live_cost, "live"
        if settings.llm_mode == "record":
            payload: dict = {"content": content, "usage": usage}
            if live_cost is not None:  # unknown pricing stays absent, not a recorded $0
                payload["cost_usd"] = cost_usd
            key = cassettes.cassette_key(model, messages)
            cassettes.save(settings.cassettes_dir, key, model, messages, payload)

    cache.store(content)  # no-op unless this call was a cache miss

    latency_ms = (time.perf_counter() - start) * 1000
    slo.log_call(
        tier=tier,
        model=model,
        settings=settings,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        cost_source=cost_source,
        cache=cache.state,
    )
    return content


async def _live_completion(
    model: str, messages: Messages, settings: Settings
) -> tuple[str, dict | None, float | None]:
    """The one bare acompletion call. Reached only on record/live.

    Returns (content, usage, cost_usd); cost is None when litellm has no pricing for the model
    — the call must not fail after the money is already spent.
    """
    import litellm  # lazy: replay never imports the SDK

    # Shut every leak channel before the first call (rule 5).
    litellm.telemetry = False
    litellm.callbacks = []
    litellm.success_callback = []
    litellm.failure_callback = []

    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
    resp = await litellm.acompletion(
        model=model,
        messages=messages,
        api_key=api_key,
        base_url=settings.openai_base_url,
    )
    content = resp["choices"][0]["message"]["content"]

    usage = getattr(resp, "usage", None)
    usage_dict = usage.model_dump(exclude_none=True) if usage is not None else None
    try:
        cost = float(litellm.completion_cost(completion_response=resp))
    except Exception:
        cost = None
    return content, usage_dict, cost
