"""Semantic-cache existence gate (iter 4).

All offline: replay mode, throwaway cassette dir, fake embedder with hand-picked vectors —
fastembed itself is never imported (its laziness is asserted below, mirroring the litellm gate).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings
from app.llm import cassettes
from app.llm.router import route
from app.llm.semcache import cosine
from app.llm.tiers import resolve_model

ROOT = Path(__file__).resolve().parent.parent

_SYSTEM = {"role": "system", "content": "sys"}

# cosine("hello world", "hello worlds") = 0.98 (>= 0.90 threshold); "different" is orthogonal.
_VECTORS = {
    "hello world": [1.0, 0.0],
    "hello worlds": [0.98, 0.199],
    "completely different": [0.0, 1.0],
}


def fake_embedder(text: str) -> list[float]:
    return _VECTORS[text]


def _messages(text: str, system: dict = _SYSTEM) -> list[dict]:
    return [system, {"role": "user", "content": text}]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Cache on, replay mode, one cassette authored for 'hello world' on the cheap tier."""
    s = Settings(
        llm_mode="replay",
        semantic_cache_enabled=True,
        cassettes_dir=tmp_path / "cassettes",
        semantic_cache_path=tmp_path / "semcache.jsonl",
        llm_log_path=tmp_path / "llm_calls.jsonl",
    )
    model = resolve_model("cheap", s.tiers_path)
    msgs = _messages("hello world")
    key = cassettes.cassette_key(model, msgs)
    cassettes.save(s.cassettes_dir, key, model, msgs, {"content": "answer-1"})
    return s


def _run(s: Settings, text: str, system: dict = _SYSTEM) -> str:
    return asyncio.run(route("cheap", _messages(text, system), settings=s, embedder=fake_embedder))


def _log(s: Settings) -> list[dict]:
    return [json.loads(line) for line in s.llm_log_path.read_text().splitlines()]


def _store(s: Settings) -> list[dict]:
    """Parseable entries of the JSONL store (mirrors semcache._load's torn-line tolerance)."""
    entries = []
    for line in s.semantic_cache_path.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def test_repeat_request_hits_and_does_not_grow_the_store(settings):
    assert _run(settings, "hello world") == "answer-1"  # miss -> cassette -> stored
    assert _run(settings, "hello world") == "answer-1"  # exact repeat -> hit

    records = _log(settings)
    assert [r["cache"] for r in records] == ["miss", "hit"]
    assert records[1]["cost_usd"] == 0.0
    assert len(_store(settings)) == 1  # a hit is not re-stored: repeat runs converge


def test_close_request_hits_without_any_cassette(settings):
    """The red-thread demo: a paraphrase has NO cassette, yet replay serves it from the cache."""
    _run(settings, "hello world")
    assert _run(settings, "hello worlds") == "answer-1"
    assert [r["cache"] for r in _log(settings)] == ["miss", "hit"]


def test_far_request_misses_and_takes_the_normal_replay_path(settings):
    _run(settings, "hello world")
    with pytest.raises(FileNotFoundError):  # miss -> normal path -> no cassette -> loud error
        _run(settings, "completely different")
    assert len(_store(settings)) == 1  # the failed call stored nothing


def test_other_prompt_prefix_never_hits(settings):
    """Namespace partition: same user text under a different system prompt must not be served."""
    _run(settings, "hello world")
    with pytest.raises(FileNotFoundError):
        _run(settings, "hello world", system={"role": "system", "content": "other prompt"})


def test_flipping_embed_model_degrades_to_miss_not_crash(settings):
    """A live store built by one embedder must not be compared against another embedder's
    vectors (different spaces, even different dimensions): new namespace -> plain miss."""
    _run(settings, "hello world")  # store now holds a 2-d vector
    other = settings.model_copy(update={"semantic_cache_embed_model": "other-model"})
    result = asyncio.run(
        route("cheap", _messages("hello world"), settings=other, embedder=lambda t: [1.0, 0.0, 0.0])
    )
    assert result == "answer-1"  # served by the cassette via the normal miss path
    assert _log(settings)[-1]["cache"] == "miss"


def test_corrupt_store_degrades_to_miss_not_crash(settings):
    settings.semantic_cache_path.parent.mkdir(parents=True, exist_ok=True)
    settings.semantic_cache_path.write_text('{"torn json\n')
    assert _run(settings, "hello world") == "answer-1"  # miss -> cassette
    assert _log(settings)[-1]["cache"] == "miss"
    assert len(_store(settings)) == 1  # the torn line is skipped; the fresh entry appended fine


def test_cache_off_by_default_keeps_iter3_behaviour(settings):
    s = settings.model_copy(update={"semantic_cache_enabled": False})
    result = asyncio.run(route("cheap", _messages("hello world"), settings=s))  # no embedder
    assert result == "answer-1"
    assert [r["cache"] for r in _log(s)] == ["off"]
    assert not s.semantic_cache_path.exists()


def test_router_never_imports_fastembed():
    """Lazy default embedder: importing the router (and replay with cache off) pulls no ONNX."""
    code = "import sys; import app.llm.router; assert 'fastembed' not in sys.modules"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)


def test_cosine_basics():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([1.0, 0.0], [2.0, 0.0]) == pytest.approx(1.0)
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0  # zero vector -> 0, not a crash
