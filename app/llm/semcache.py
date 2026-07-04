"""Semantic cache over the access layer (iter 4).

A hit is a previously answered request whose embedded text is close enough (cosine >=
threshold) within the same namespace — LLM model + embedding model + every message before the
last user turn — so a different tier, prompt version or embedder never serves someone else's
answer. A hit is returned without touching cassettes or the network; a miss falls through to
the normal route() path and the fresh answer is stored.

route() sees none of these mechanics: open_session() hands it a Session that is either a hit
(content ready), a miss (store() persists the fresh answer) or off (store() is a no-op).

The store is one JSONL file scanned linearly, same shape as the SLO log; a torn line degrades
to one skipped entry. # dl-lite: linear-scan JSONL store -> vector store (FAISS/qdrant).

The embedder is a plain callable dependency (tests inject a fake); the default is fastembed —
local ONNX, $0 per call — imported lazily, mirroring the litellm discipline: replay without the
cache never loads it.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import Settings
from app.llm.cassettes import Messages
from app.llm.slo import CacheState

Embedder = Callable[[str], list[float]]


@dataclass
class Session:
    """One route() call's view of the cache: outcome state, hit content, miss destination."""

    state: CacheState
    content: str | None = None  # set on hit
    _miss_dest: tuple[Path, str, str, list[float]] | None = None  # path, namespace, text, vector

    def store(self, content: str) -> None:
        """Persist a miss's fresh answer for the next close-enough request (no-op on hit/off)."""
        if self._miss_dest is None:
            return
        path, namespace, text, vector = self._miss_dest
        append_entry(path, namespace, text, vector, content)


def open_session(
    settings: Settings, model: str, messages: Messages, embedder: Embedder | None = None
) -> Session:
    """Look the request up and hand route() a ready session.

    record is a cassette-authoring mode: a cache hit there would silently skip the
    cassettes.save a later replay depends on, so the cache stays out of record entirely.
    """
    if not settings.semantic_cache_enabled or settings.llm_mode == "record":
        return Session("off")
    text = cacheable_text(messages)
    if text is None:
        return Session("off")
    embedder = embedder or default_embedder(settings.semantic_cache_embed_model)
    vector = embedder(text)
    namespace = namespace_key(model, settings.semantic_cache_embed_model, messages)
    cached = lookup(
        settings.semantic_cache_path, namespace, vector, settings.semantic_cache_threshold
    )
    if cached is not None:
        return Session("hit", content=cached)
    return Session("miss", _miss_dest=(settings.semantic_cache_path, namespace, text, vector))


def cacheable_text(messages: Messages) -> str | None:
    """The text similarity is judged on: the final user turn's content, or None to bypass."""
    if not messages:
        return None
    last = messages[-1]
    content = last.get("content")
    if last.get("role") != "user" or not isinstance(content, str):
        return None
    return content


def namespace_key(model: str, embed_model: str, messages: Messages) -> str:
    """Exact-match partition for candidates: LLM model + embedder + everything before the
    embedded turn. The embedder is part of the key because vectors from different embedding
    models live in incomparable spaces — flipping SEMANTIC_CACHE_EMBED_MODEL over a live store
    must degrade to a miss, not compare (or crash on) foreign vectors."""
    canonical = json.dumps(
        {"model": model, "embed_model": embed_model, "prefix": messages[:-1]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def lookup(path: Path, namespace: str, vector: list[float], threshold: float) -> str | None:
    """Content of the closest same-namespace entry at or above threshold, or None (miss)."""
    best: str | None = None
    best_sim = threshold
    for entry in _load(path):
        if entry["namespace"] != namespace:
            continue
        sim = cosine(vector, entry["vector"])
        if sim >= best_sim:
            best, best_sim = entry["content"], sim
    return best


def append_entry(path: Path, namespace: str, text: str, vector: list[float], content: str) -> None:
    """Append one answered request (only misses are stored, so hits don't grow the file).

    text is never read back — it's the human-debugging aid when eyeballing the store.
    """
    entry = {"namespace": namespace, "text": text, "vector": vector, "content": content}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:  # a torn line degrades to one skipped entry, not a crash
            continue
    return entries


@lru_cache(maxsize=2)
def default_embedder(model_name: str) -> Embedder:
    """The real embedder, built once per model. Lazy fastembed import: replay tests, CI and the
    cache-off path never load ONNX; the first live use downloads the model once (~30 MB)."""
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=model_name)

    def embed(text: str) -> list[float]:
        [vector] = model.embed([text])
        return [float(x) for x in vector]

    return embed
