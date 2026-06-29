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

    # Paths and control-plane endpoints.
    tiers_path: Path = _ROOT / "llm-tiers.yaml"
    tickets_path: Path = _ROOT / "fixtures" / "tickets.jsonl"
    cassettes_dir: Path = _ROOT / "cassettes"
    mlflow_tracking_uri: str = "http://localhost:5050"


@lru_cache
def get_settings() -> Settings:
    return Settings()
