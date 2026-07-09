"""Settings — the single gateway to env (CLAUDE.md rule 6). No scattered os.getenv."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent

LLMMode = Literal["replay", "record", "live"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Cassette mode. replay = $0, offline, never hits the network (default).
    # record/live cost money and are gated by an explicit go (rule 4).
    llm_mode: LLMMode = "replay"

    # Role -> tier names; tiers resolve to models in llm-tiers.yaml.
    triage_tier: str = "cheap"
    judge_tier: str = "smart"

    # OpenAI access — only consumed on record/live, via the LiteLLM SDK.
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None

    # SLO thresholds per call (LLM FinOps, iter 3). A breach WARNs in the SLO log — it
    # never fails the call (existence-gate). Generous defaults; tighten via env to demo.
    slo_max_cost_usd: float = 0.05
    slo_max_latency_ms: float = 15_000

    # Semantic cache over the access layer (iter 4). Off by default: the plain replay path
    # and CI stay byte-identical to iter 3; flip SEMANTIC_CACHE_ENABLED=1 to demo.
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = 0.90
    semantic_cache_embed_model: str = "BAAI/bge-small-en-v1.5"

    # Phoenix online observability (iter 5a). Off by default: replay paths, tests and CI
    # neither import OTel nor try to export anything; flip PHOENIX_ENABLED=1 to trace.
    phoenix_enabled: bool = False
    phoenix_endpoint: str = "http://localhost:6006"
    phoenix_project: str = "triagewise"

    # Online LLM-as-judge (iter 5b): what fraction of traced traffic gets judged. Sampling is
    # deterministic per ticket_id, so the same traffic always picks the same spans.
    judge_sample_rate: float = 0.5

    # Continuous-evaluation loop (iter 6b): how often the Prefect schedule reruns the
    # promotion turn. Short by design — the demo shouldn't wait minutes for a tick.
    loop_interval_seconds: int = 60

    # Paths and control-plane endpoints.
    tiers_path: Path = _ROOT / "llm-tiers.yaml"
    llm_log_path: Path = _ROOT / "logs" / "llm_calls.jsonl"
    semantic_cache_path: Path = _ROOT / "logs" / "semantic_cache.jsonl"
    tickets_path: Path = _ROOT / "fixtures" / "tickets.jsonl"
    # Post-release ticket batch (iter 5a): introduces the new `automation` category so the
    # drift monitor has something to catch. Fabricated replies for BOTH batches live in
    # replies_path and become offline cassettes via scripts.author_cassette.
    tickets_postrelease_path: Path = _ROOT / "fixtures" / "tickets_postrelease.jsonl"
    replies_path: Path = _ROOT / "fixtures" / "replies.jsonl"
    cassettes_dir: Path = _ROOT / "cassettes"
    # Golden set is DVC-versioned (not in git); eval/ holds the committed promptfoo
    # assets generated from it by scripts/build_eval.py.
    golden_path: Path = _ROOT / "data" / "golden.jsonl"
    eval_dir: Path = _ROOT / "eval"
    mlflow_tracking_uri: str = "http://localhost:5050"


@lru_cache
def get_settings() -> Settings:
    return Settings()
