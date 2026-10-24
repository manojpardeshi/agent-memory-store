from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, DeterministicReranker, MemoryStore, Scope
from llm_memory_store.rerank import RERANK_DEPTH, RERANK_INPUT_CHARS, rerank_order

SCOPE = Scope.private("me", "test", "rerank")
OTHER = Scope.private("someone-else", "test", "rerank")


class RecordingReranker:
    """Scores by a fixed keyword and records exactly what it was asked to score."""

    model_name = "recording"

    def __init__(self, keyword: str) -> None:
        self.keyword = keyword
        self.calls: list[list[str]] = []

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        self.calls.append(list(documents))
        return [1.0 if self.keyword in doc else 0.0 for doc in documents]


def _fill(store: MemoryStore, count: int = 30) -> None:
    for index in range(count):
        store.remember("fact", f"Note {index} about travel plans and packing lists", SCOPE)


def test_rerank_order_sorts_by_score_with_stable_ties_and_limit() -> None:
    assert rerank_order([0.1, 0.9, 0.5, 0.9], 3) == [1, 3, 2]
    assert rerank_order([0.0, 0.0, 0.0], 2) == [0, 1]
    assert rerank_order([], 5) == []
    assert rerank_order([math.nan, 0.2, 0.1], 3) == [1, 2, 0]  # NaN sorts last


def test_rerank_depth_is_the_validated_twenty_whatever_the_limit(tmp_path: Path) -> None:
    assert RERANK_DEPTH == 20
    reranker = RecordingReranker("passport")
    with MemoryStore(tmp_path / "s.sqlite3", DeterministicEmbedder(64), reranker=reranker) as s:
        _fill(s, 40)
        vector = s.recall("travel plans", SCOPE, limit=35, relevance_filter=None)
        results = s.recall("travel plans", SCOPE, limit=35, relevance_filter=None, rerank=True)
    assert len(reranker.calls[0]) == 20  # never deeper, even for a 35-result recall
    assert [r.memory.memory_id for r in results[20:]] == [r.memory.memory_id for r in vector[20:]]
    assert all(r.rerank_score is None for r in results[20:])


def test_rerank_reorders_only_vector_candidates(tmp_path: Path) -> None:
    reranker = RecordingReranker("passport")
    with MemoryStore(tmp_path / "s.sqlite3", DeterministicEmbedder(64), reranker=reranker) as s:
        _fill(s)
        s.remember("fact", "Renew the passport before the trip to Lisbon", SCOPE)
        pool = s.recall("travel plans", SCOPE, limit=50, relevance_filter=None)[:20]
        results = s.recall("travel plans", SCOPE, limit=10, relevance_filter=None, rerank=True)
    pool_ids = [r.memory.memory_id for r in pool]
    ids = [r.memory.memory_id for r in results]
    assert set(ids) <= set(pool_ids) and len(ids) == 10 and len(set(ids)) == 10
    if any("passport" in r.memory.content for r in pool):
        assert "passport" in results[0].memory.content
    rest = (
        [i for i in pool_ids if i != ids[0]]
        if "passport" in results[0].memory.content
        else pool_ids
    )
    assert ids[1:] == rest[:9] or ids == pool_ids[:10]  # ties keep vector order
    assert all(r.rerank_score is not None for r in results)
    assert "rerank_score" in results[0].to_dict()
    assert all(len(doc) <= RERANK_INPUT_CHARS for doc in reranker.calls[0])
    assert len(reranker.calls[0]) == 20


def test_rerank_never_crosses_scopes(tmp_path: Path) -> None:
    reranker = RecordingReranker("secret")
    with MemoryStore(tmp_path / "s.sqlite3", DeterministicEmbedder(64), reranker=reranker) as s:
        s.remember("fact", "The secret launch code word is heliotrope", OTHER)
        _fill(s, 12)
        results = s.recall("secret code word", SCOPE, limit=10, relevance_filter=None, rerank=True)
    assert all(r.memory.scope == SCOPE for r in results)
    assert all("heliotrope" not in doc for call in reranker.calls for doc in call)


def test_vector_recall_is_unchanged_and_has_no_rerank_score(store: MemoryStore) -> None:
    _fill(store, 5)
    result = store.recall("travel", SCOPE, relevance_filter=None)[0]
    assert result.rerank_score is None and "rerank_score" not in result.to_dict()


def test_rerank_with_hybrid_is_rejected(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="vector retrieval only"):
        store.recall("travel", SCOPE, retrieval="hybrid", rerank=True)


def test_relevance_filter_still_applies_after_reranking(tmp_path: Path) -> None:
    from llm_memory_store import RelevanceFilter

    with MemoryStore(
        tmp_path / "s.sqlite3", DeterministicEmbedder(64), reranker=DeterministicReranker()
    ) as s:
        _fill(s, 12)
        loose = s.recall("travel plans", SCOPE, limit=10, relevance_filter=None, rerank=True)
        strict = s.recall(
            "travel plans",
            SCOPE,
            limit=10,
            relevance_filter=RelevanceFilter.relative(0.0),
            rerank=True,
        )
    top_vector = max(r.semantic_score for r in loose)
    assert set(r.memory.memory_id for r in strict) <= set(r.memory.memory_id for r in loose)
    assert all(r.semantic_score >= top_vector - 1e-9 for r in strict)


def test_default_reranker_is_loaded_lazily(
    store: MemoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import llm_memory_store.store as store_module

    created: list[str] = []

    class FakeFastEmbedReranker(DeterministicReranker):
        def __init__(self) -> None:
            created.append("loaded")

    monkeypatch.setattr(store_module, "FastEmbedReranker", FakeFastEmbedReranker)
    _fill(store, 3)
    store.recall("travel", SCOPE, relevance_filter=None)
    assert created == []  # never loaded for ordinary recall
    store.recall("travel", SCOPE, relevance_filter=None, rerank=True)
    store.recall("travel", SCOPE, relevance_filter=None, rerank=True)
    assert created == ["loaded"]  # loaded once, on first use
