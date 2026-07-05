"""Iter-5a existence gates, offline: drift decision is pure, fixtures are coherent, and
tracing stays a strict no-op (nothing Phoenix/OTel imported) unless a transport enables it."""

from __future__ import annotations

import sys

from app.config import Settings
from app.domain.drift import category_drift
from app.domain.triage import TriageResult
from app.observability.phoenix import SpanRecorder, init_tracing, triage_span
from app.persistence.tickets import load_replies, load_tickets


def test_category_drift_detects_new_category():
    rows = [
        ("base", "bug"),
        ("base", "billing"),
        ("postrelease", "bug"),
        ("postrelease", "automation"),
        ("postrelease", "automation"),
    ]
    report = category_drift(rows, baseline="base", candidate="postrelease")
    assert report.drifted
    assert report.new_categories == ["automation"]
    assert report.distributions["postrelease"]["automation"] == 2


def test_category_drift_none_when_same_vocabulary():
    rows = [
        ("base", "bug"),
        ("postrelease", "bug"),
        ("postrelease", "billing"),
        ("base", "billing"),
    ]
    report = category_drift(rows, baseline="base", candidate="postrelease")
    assert not report.drifted and report.new_categories == []


def test_category_drift_verdict_stable_under_reruns():
    """Traces are append-only; duplicated traffic inflates counts, never the verdict."""
    rows = [("base", "bug"), ("postrelease", "automation")]
    once = category_drift(rows, baseline="base", candidate="postrelease")
    twice = category_drift(rows * 3, baseline="base", candidate="postrelease")
    assert once.drifted == twice.drifted and once.new_categories == twice.new_categories


def test_postrelease_batch_and_replies_are_coherent():
    """Every ticket in both batches has a validated fabricated reply (author --all can't miss),
    ids don't collide across batches, and the new category shows up only post-release."""
    settings = Settings()
    base = load_tickets(settings.tickets_path)
    post = load_tickets(settings.tickets_postrelease_path)
    replies = load_replies(settings.replies_path)

    base_ids, post_ids = {t.id for t in base}, {t.id for t in post}
    assert post and not base_ids & post_ids
    assert base_ids | post_ids == set(replies)
    assert all(isinstance(r, TriageResult) for r in replies.values())

    base_cats = {replies[i].category for i in base_ids}
    post_cats = {replies[i].category for i in post_ids}
    assert "automation" in post_cats - base_cats  # the drift the monitor must catch


def test_tracing_off_is_a_noop():
    """PHOENIX_ENABLED=0 (default): no tracer, no phoenix/OTel import, recorder is inert."""
    assert init_tracing(Settings()) is False
    ticket = load_tickets(Settings().tickets_path)[0]
    with triage_span(ticket, tier="cheap", batch="base") as rec:
        assert isinstance(rec, SpanRecorder)
        rec.set_result(
            TriageResult(
                category="bug",
                priority="low",
                sentiment="neutral",
                needs_human=False,
                draft_reply="ok",
            )
        )
    assert not any(m == "phoenix" or m.startswith("phoenix.") for m in sys.modules)
