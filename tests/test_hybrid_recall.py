from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.database import KEYWORD_INDEX_TABLE, StoreCompatibilityError
from llm_memory_store.store import keyword_query

SCOPE = Scope.private("me", "test", "codex")
NEEDLE = "My locker combination is stored under the codename quibblefrost"


class WholeTextHashEmbedder(DeterministicEmbedder):
    """Embeds each whole text as one hashed point, so shared words give no vector similarity.

    This isolates the keyword half of hybrid recall: any exact-word match it finds is one the
    vector ranking cannot.
    """

    model_name = "whole-text-hash-v1"

    def _embed(self, text: str) -> list[float]:
        raw = hashlib.blake2b(text.encode(), digest_size=self.dimension).digest()
        vector = [byte - 127.5 for byte in raw]
        norm = sum(value * value for value in vector) ** 0.5
        return [value / norm for value in vector]

    def embed_query(self, text: str) -> list[float]:
        # A query naming the needle's codename points directly away from the needle, so the
        # vector ranking places it last rather than wherever hashing happens to land it.
        if "quibblefrost" in text:
            return [-value for value in self._embed(NEEDLE)]
        return self._embed(text)


def _fill(store: MemoryStore, scope: Scope = SCOPE, count: int = 40) -> None:
    for index in range(count):
        store.remember("fact", f"Filler note number {index} about ordinary errands", scope)


def _drop_keyword_index(path: Path) -> None:
    """Return a store to its pre-index shape, as created by an earlier runtime."""
    connection = sqlite3.connect(path)
    for suffix in ("after_insert", "after_delete", "after_update"):
        connection.execute(f"DROP TRIGGER {KEYWORD_INDEX_TABLE}_{suffix}")
    connection.execute(f"DROP TABLE {KEYWORD_INDEX_TABLE}")
    connection.commit()
    connection.close()


@pytest.fixture
def hashed_store(tmp_path: Path):
    instance = MemoryStore(tmp_path / "hashed.sqlite3", WholeTextHashEmbedder(64))
    try:
        yield instance
    finally:
        instance.close()


def test_new_store_has_a_verified_keyword_index(store: MemoryStore) -> None:
    store.remember("fact", "The deploy key rotates monthly", SCOPE)
    assert store.keyword_index is True
    assert store.status()["keyword_index"] == "ok"


def test_hybrid_finds_an_exact_word_match_the_vector_ranking_misses(
    hashed_store: MemoryStore,
) -> None:
    # The needle is oldest, so recency cannot lift it into the vector top three.
    needle = hashed_store.remember("fact", NEEDLE, SCOPE)
    _fill(hashed_store)

    vector = hashed_store.recall("quibblefrost", SCOPE, limit=3, relevance_filter=None)
    hybrid = hashed_store.recall(
        "quibblefrost", SCOPE, limit=3, relevance_filter=None, retrieval="hybrid"
    )

    assert needle.memory_id not in [r.memory.memory_id for r in vector]
    assert hybrid[0].memory.memory_id == needle.memory_id
    assert hybrid[0].fusion_score is not None
    assert hybrid[0].to_dict()["fusion_score"] == hybrid[0].fusion_score
    # Keyword-only results still carry their true vector distance: here, directly opposite.
    assert hybrid[0].distance == pytest.approx(2.0, abs=1e-6)
    assert hybrid[0].semantic_score == 0.0


def test_hybrid_is_ordered_by_fusion_score(store: MemoryStore) -> None:
    _fill(store, count=10)
    store.remember("fact", "The quarterly budget review is on Friday", SCOPE)
    results = store.recall(
        "budget review", SCOPE, limit=8, relevance_filter=None, retrieval="hybrid"
    )
    scores = [result.fusion_score for result in results]
    assert scores == sorted(scores, reverse=True)


def test_vector_mode_output_is_unchanged(store: MemoryStore) -> None:
    store.remember("fact", "The deploy key rotates monthly", SCOPE)
    result = store.recall("deploy key", SCOPE, relevance_filter=None)[0]
    assert result.fusion_score is None
    assert "fusion_score" not in result.to_dict()


def test_hybrid_never_crosses_scopes(hashed_store: MemoryStore) -> None:
    other = Scope.private("someone-else", "test", "codex")
    hashed_store.remember("fact", NEEDLE, other)
    _fill(hashed_store, count=5)

    results = hashed_store.recall(
        "quibblefrost", SCOPE, limit=10, relevance_filter=None, retrieval="hybrid"
    )

    assert all(result.memory.scope == SCOPE for result in results)
    assert NEEDLE not in [result.memory.content for result in results]


def test_hybrid_reaches_named_shared_pools_only(hashed_store: MemoryStore) -> None:
    pool = Scope.shared("me", "test", "team")
    hashed_store.remember("fact", NEEDLE, pool)
    _fill(hashed_store, count=5)

    without = hashed_store.recall(
        "quibblefrost", SCOPE, limit=10, relevance_filter=None, retrieval="hybrid"
    )
    with_pool = hashed_store.recall(
        "quibblefrost",
        SCOPE,
        shared_pools=["team"],
        limit=3,
        relevance_filter=None,
        retrieval="hybrid",
    )

    assert NEEDLE not in [result.memory.content for result in without]
    assert with_pool[0].memory.content == NEEDLE


def test_hybrid_excludes_superseded_and_expired_memories(hashed_store: MemoryStore) -> None:
    _fill(hashed_store, count=5)
    original = hashed_store.remember("fact", NEEDLE, SCOPE)
    corrected = hashed_store.correct(original.memory_id, "The codename quibblefrost was retired")
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    hashed_store.remember("fact", "quibblefrost backup codename", SCOPE, expires_at=past)

    ids = [
        result.memory.memory_id
        for result in hashed_store.recall(
            "quibblefrost", SCOPE, limit=10, relevance_filter=None, retrieval="hybrid"
        )
    ]

    assert corrected.memory_id in ids
    assert original.memory_id not in ids
    assert len([i for i in ids if i == corrected.memory_id]) == 1
    assert all("backup" not in hashed_store.get(memory_id).content for memory_id in ids)


def test_relevance_filter_still_applies_in_hybrid_mode(hashed_store: MemoryStore) -> None:
    from llm_memory_store import RelevanceFilter

    _fill(hashed_store)
    hashed_store.remember("fact", NEEDLE, SCOPE)
    unfiltered = hashed_store.recall(
        "quibblefrost", SCOPE, limit=10, relevance_filter=None, retrieval="hybrid"
    )
    filtered = hashed_store.recall(
        "quibblefrost",
        SCOPE,
        limit=10,
        relevance_filter=RelevanceFilter.relative(0.0),
        retrieval="hybrid",
    )
    anchor = max(result.semantic_score for result in unfiltered)
    assert len(filtered) < len(unfiltered)
    assert all(result.semantic_score >= anchor - 1e-9 for result in filtered)


def test_forgotten_memory_terms_leave_the_keyword_index(hashed_store: MemoryStore) -> None:
    needle = hashed_store.remember("fact", NEEDLE, SCOPE)
    hashed_store.remember("fact", "An unrelated keeper note", SCOPE)

    hashed_store.forget(needle.memory_id)

    connection = hashed_store.connection
    connection.execute(
        f"CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main, {KEYWORD_INDEX_TABLE}, 'row')"
    )
    terms = {row[0] for row in connection.execute("SELECT term FROM temp.vocab")}
    assert "quibblefrost" not in terms
    assert "keeper" in terms
    assert hashed_store.status()["keyword_index"] == "ok"
    hashed_store.close()
    assert b"quibblefrost" not in Path(hashed_store.path).read_bytes()


def test_expiry_purge_keeps_the_keyword_index_consistent(hashed_store: MemoryStore) -> None:
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    hashed_store.remember("fact", NEEDLE, SCOPE, expires_at=past)
    hashed_store.remember("fact", "An unrelated keeper note", SCOPE)

    hashed_store.purge_expired()

    assert hashed_store.status()["keyword_index"] == "ok"
    hybrid = hashed_store.recall("quibblefrost", SCOPE, relevance_filter=None, retrieval="hybrid")
    assert [result.memory.content for result in hybrid] == ["An unrelated keeper note"]


def test_store_from_before_the_index_is_backfilled_when_opened_writable(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    embedder = WholeTextHashEmbedder(64)
    with MemoryStore(path, embedder) as store:
        _fill(store, count=5)
        needle = store.remember("fact", NEEDLE, SCOPE)
    _drop_keyword_index(path)

    with MemoryStore(path, embedder, read_only=True) as read_only:
        assert read_only.keyword_index is False
        assert read_only.status()["keyword_index"] == "absent"
        assert read_only.recall("quibblefrost", SCOPE, relevance_filter=None)
        with pytest.raises(StoreCompatibilityError, match="keyword index"):
            read_only.recall("quibblefrost", SCOPE, retrieval="hybrid")

    with MemoryStore(path, embedder) as reopened:
        assert reopened.status()["keyword_index"] == "ok"
        hit = reopened.recall(
            "quibblefrost", SCOPE, limit=1, relevance_filter=None, retrieval="hybrid"
        )
        assert hit[0].memory.memory_id == needle.memory_id

    with MemoryStore(path, embedder, read_only=True) as read_only:
        assert read_only.status()["keyword_index"] == "unverified"
        assert read_only.recall("quibblefrost", SCOPE, retrieval="hybrid", relevance_filter=None)


def test_query_text_cannot_inject_fts_syntax(store: MemoryStore) -> None:
    store.remember("fact", "The deploy key rotates monthly", SCOPE)
    for hostile in (
        'deploy" OR NEAR(key',
        "deploy * AND ^key",
        'content:"deploy"',
        "NOT key",
        'key"""',
    ):
        store.recall(hostile, SCOPE, relevance_filter=None, retrieval="hybrid")


def test_keyword_query_drops_stopwords_and_quotes_every_term() -> None:
    assert keyword_query("What did I say about the Café budget?") == '"say" OR "café" OR "budget"'
    assert keyword_query("what is it") is None
    assert keyword_query('snake_case "quoted"') == '"snake" OR "case" OR "quoted"'


def test_retrieval_mode_is_validated(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="retrieval"):
        store.recall("anything", SCOPE, retrieval="keyword")


def test_fusion_scores_are_exact_so_equal_scores_tie() -> None:
    """Rank 5 alone and ranks 18 + 330 both score exactly 1/65; floats would split them."""
    from fractions import Fraction

    from llm_memory_store.store import reciprocal_rank_fusion

    first = list(range(100, 117)) + [2]  # id 2 at vector rank 18
    second = list(range(1000, 1329)) + [2]  # id 2 at keyword rank 330
    scores = reciprocal_rank_fusion([[90, 91, 92, 93, 1], [], first, second])
    assert scores[1] == Fraction(1, 65)
    assert scores[2] == Fraction(1, 78) + Fraction(1, 390) == Fraction(1, 65)
    assert 1.0 / 78 + 1.0 / 390 != 1.0 / 65  # the float artifact the exact scores remove
