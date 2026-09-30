"""The batched recall must return exactly what the per-candidate implementation returned.

A reference copy of the previous algorithm runs against the same store with time frozen, and
every result field must match: memory, score, semantic score, recency score, distance, and
order, including ties broken by memory id, across limits and relevance filters.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest
import sqlite_vec

import llm_memory_store.store as store_module
from llm_memory_store import RelevanceFilter, Scope

FIXED_NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: D102 - mirrors datetime.now
        return FIXED_NOW if tz is not None else FIXED_NOW.replace(tzinfo=None)


def _reference_recall(store, query, scope, shared_pools, *, limit, half_life, weight, filt):
    """The pre-batching algorithm, verbatim in logic."""
    scopes = [scope] + [Scope.shared(scope.subject, scope.environment, p) for p in shared_pools]
    scope_ids = [sid for s in scopes if (sid := store._find_scope_id(s))]
    if not scope_ids:
        return []
    vector = sqlite_vec.serialize_float32(store.embedder.embed_query(query))
    candidate_limit = max(limit * 4, 20)
    candidates: dict[int, float] = {}
    for sid in scope_ids:
        for row in store.connection.execute(
            "SELECT rowid, distance FROM memory_vectors "
            "WHERE embedding MATCH ? AND k = ? AND scope_id = ? ORDER BY distance",
            (vector, candidate_limit, sid),
        ).fetchall():
            iid, dist = int(row["rowid"]), float(row["distance"])
            candidates[iid] = min(dist, candidates.get(iid, dist))
    results = []
    for iid, distance in candidates.items():
        row = store.connection.execute(
            "SELECT status, embedding_status, created_at, expires_at FROM memories WHERE id=?",
            (iid,),
        ).fetchone()
        if row is None or row["status"] != "active" or row["embedding_status"] != "ready":
            continue
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= FIXED_NOW:
            continue
        created = datetime.fromisoformat(row["created_at"])
        age = max(0.0, (FIXED_NOW - created).total_seconds() / 86_400)
        sem = max(0.0, min(1.0, 1.0 - distance))
        rec = math.pow(0.5, age / half_life)
        score = weight * sem + (1 - weight) * rec
        record = store._record_by_internal_id(iid)
        results.append((score, record.memory_id, record, sem, rec, distance))
    results.sort(key=lambda r: (-r[0], r[1]))
    if filt is not None and results:
        floor = results[0][3] - filt.maximum_semantic_score_gap
        results = [r for r in results if r[3] >= floor]
    return [(r[2], r[0], r[3], r[4], r[5]) for r in results[:limit]]


def _populate(store, rng: random.Random) -> Scope:
    scope = Scope.private("tester", "test", "agent")
    words = ["editor", "coffee", "hiking", "budget", "dentist", "garden", "piano", "flight"]
    ids = []
    for i in range(70):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(2, 6)))
        ids.append(store.remember("fact", f"{text} note {i % 9}", scope).memory_id)
    for _ in range(4):  # identical content, identical age: forces score ties
        ids.append(store.remember("fact", "coffee editor tie case", scope).memory_id)
    store.remember("fact", "coffee shared pool fact", Scope.shared("tester", "test", "team"))
    store.correct(ids[0], "coffee editor corrected")
    past = (FIXED_NOW - timedelta(days=1)).isoformat()
    store.remember("fact", "coffee editor expired", scope, expires_at=past)
    # Spread creation times so recency matters; tie rows keep one shared timestamp.
    for iid, in store.connection.execute("SELECT id FROM memories").fetchall():
        days = rng.uniform(0, 120)
        store.connection.execute(
            "UPDATE memories SET created_at=? WHERE id=? AND content != 'coffee editor tie case'",
            ((FIXED_NOW - timedelta(days=days)).isoformat(), iid),
        )
    store.connection.execute(
        "UPDATE memories SET created_at=? WHERE content='coffee editor tie case'",
        ((FIXED_NOW - timedelta(days=3)).isoformat(),),
    )
    store.connection.commit()
    return scope


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_batched_recall_matches_reference_exactly(store, monkeypatch, seed) -> None:
    rng = random.Random(seed)
    scope = _populate(store, rng)
    monkeypatch.setattr(store_module, "datetime", _FrozenDatetime)
    filters = [None, RelevanceFilter("relative_semantic_gap", 0.05),
               RelevanceFilter("relative_semantic_gap", 0.3)]
    for query in ["coffee editor", "hiking budget", "dentist flight piano", "garden"]:
        for limit in (1, 3, 5, 10, 25):
            for filt in filters:
                for pools in ((), ("team",)):
                    got = store.recall(query, scope, shared_pools=pools, limit=limit,
                                       relevance_filter=filt)
                    want = _reference_recall(store, query, scope, pools, limit=limit,
                                             half_life=30.0, weight=0.8, filt=filt)
                    assert [(r.memory, r.score, r.semantic_score, r.recency_score, r.distance)
                            for r in got] == want, (query, limit, filt, pools)


def test_recall_query_count_does_not_grow_with_candidates(store) -> None:
    scope = _populate(store, random.Random(9))
    statements: list[str] = []
    store.connection.set_trace_callback(statements.append)
    try:
        store.recall("coffee editor", scope, limit=5, relevance_filter=None)
        small = len(statements)
        statements.clear()
        store.recall("coffee editor", scope, limit=25, relevance_filter=None)
        large = len(statements)
    finally:
        store.connection.set_trace_callback(None)
    # 20 candidates versus 100: under the old path this grew by roughly 3 per candidate.
    assert large == small, (small, large)
