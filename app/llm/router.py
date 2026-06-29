"""route("tier", ...) — the single LLM chokepoint (CLAUDE.md rule 6).

Layers call route() and never name a model or import an SDK directly. Cassette mode decides
whether we touch the network: replay is offline/$0 (default); record/live cost money (rule 4).

LiteLLM discipline (rule 5): SDK-only (never Proxy), lazy import, telemetry off, no callbacks,
keys/base_url only via Settings. In replay the SDK is never imported at all.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.llm import cassettes
from app.llm.cassettes import Messages
from app.llm.tiers import resolve_model


async def route(tier: str, messages: Messages, *, settings: Settings | None = None) -> str:
    """Resolve tier -> model, run the exchange per LLM_MODE, return the assistant text."""
    settings = settings or get_settings()
    model = resolve_model(tier, settings.tiers_path)
    key = cassettes.cassette_key(model, messages)

    if settings.llm_mode == "replay":
        response = cassettes.load(settings.cassettes_dir, key)
        if response is None:
            raise FileNotFoundError(
                f"No cassette for tier '{tier}' (model {model}, key {key[:12]}…) in "
                f"{settings.cassettes_dir}. replay never hits the network; record it explicitly "
                "(LLM_MODE=record costs money, rule 4)."
            )
        return response["content"]

    content = await _live_completion(model, messages, settings)
    if settings.llm_mode == "record":
        cassettes.save(settings.cassettes_dir, key, model, messages, {"content": content})
    return content


async def _live_completion(model: str, messages: Messages, settings: Settings) -> str:
    """The one bare acompletion call. Reached only on record/live."""
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
    return resp["choices"][0]["message"]["content"]
