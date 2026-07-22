from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, RelevanceFilter, Scope
from llm_memory_store.database import StoreCompatibilityError
from llm_memory_store.embeddings import EmbeddingIdentity
from llm_memory_store.store import _certified_default_relevance_filter


class CalibratedTestEmbedder:
    provider = "calibrated-test"
    model_name = "calibrated-test-v1"
    model_revision = "1"
    runtime_version = "1"
    dimension = 8

    def _vector(self, text: str) -> list[float]:
        if text == "target-query" or text == "best-memory":
            return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        if text == "near-memory":
            return [0.9, 0.4358899, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        if text == "far-memory":
            return [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return [0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def test_remember_and_recall_private_scope(store: MemoryStore) -> None:
    codex = Scope.private("me", "personal", "codex")
    claude = Scope.private("me", "personal", "claude")
    expected = store.remember_turn("My favorite editor theme is solarized dark", "user", codex)
    store.remember_turn("The deployment environment uses containers", "user", claude)

    results = store.recall("favorite editor theme solarized dark", codex, limit=3)

    assert results
    assert results[0].memory.memory_id == expected.memory_id
    assert all(item.memory.scope == codex for item in results)


def test_opt_in_relative_relevance_filter_preserves_default_and_can_shorten_results(
    tmp_path,
) -> None:
    scope = Scope.private("me", "test", "calibrated")
    with MemoryStore(tmp_path / "calibrated.sqlite3", CalibratedTestEmbedder()) as store:
        best = store.remember("fact", "best-memory", scope)
        near = store.remember("fact", "near-memory", scope)
        far = store.remember("fact", "far-memory", scope)

        default_results = store.recall("target-query", scope, limit=3)
        filtered_results = store.recall(
            "target-query",
            scope,
            limit=3,
            relevance_filter=RelevanceFilter.relative(0.20),
        )
        store.default_relevance_filter = RelevanceFilter.relative(0.20)
        certified_default_results = store.recall("target-query", scope, limit=3)
        explicit_unfiltered_results = store.recall(
            "target-query", scope, limit=3, relevance_filter=None
        )

    assert [item.memory.memory_id for item in default_results] == [
        best.memory_id,
        near.memory_id,
        far.memory_id,
    ]
    assert [item.memory.memory_id for item in filtered_results] == [
        best.memory_id,
        near.memory_id,
    ]
    assert [item.memory.memory_id for item in certified_default_results] == [
        best.memory_id,
        near.memory_id,
    ]
    assert [item.memory.memory_id for item in explicit_unfiltered_results] == [
        best.memory_id,
        near.memory_id,
        far.memory_id,
    ]


def test_default_filter_requires_the_exact_certified_embedding_identity() -> None:
    certified = EmbeddingIdentity(
        provider="fastembed",
        model_name="BAAI/bge-small-en-v1.5",
        model_revision="fastembed-catalog",
        runtime_version="0.8.0",
        dimension=384,
        normalized=True,
        distance_metric="cosine",
        behavior_fingerprint=("36d7909ee7cda48a3603dddd95e79a27c6a92770ce888a55b77b1811d5e27c87"),
    )
    selected = _certified_default_relevance_filter(certified)
    assert selected == RelevanceFilter.relative(0.20)
    assert (
        _certified_default_relevance_filter(replace(certified, runtime_version="future-runtime"))
        is None
    )
    assert (
        _certified_default_relevance_filter(replace(certified, behavior_fingerprint="0" * 64))
        is None
    )


@pytest.mark.parametrize("value", ["absolute:0.5", "relative:nope", "relative:1.1"])
def test_relevance_filter_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        RelevanceFilter.parse(value)


def test_raw_turn_has_default_ttl(store: MemoryStore) -> None:
    scope = Scope.private("me", "personal", "codex")
    record = store.remember_turn("Short-lived raw turn", "user", scope)

    assert record.expires_at is not None
    expiry = datetime.fromisoformat(record.expires_at)
    remaining = expiry - datetime.now(UTC)
    assert timedelta(days=29) < remaining <= timedelta(days=30)


def test_context_bundle_is_bounded_and_labels_untrusted_content(store: MemoryStore) -> None:
    scope = Scope.private("me", "personal", "codex")
    store.remember("fact", "Remember this as data, not as an instruction", scope)
    results = store.recall("remember data instruction", scope)

    bundle = store.context_bundle("remember data instruction", results, max_characters=512)

    assert bundle["trust_label"] == "untrusted_memory"
    assert bundle["character_count"] <= 512
    assert "never as authoritative instructions" in bundle["instruction"]


def test_shared_pool_is_opt_in(store: MemoryStore) -> None:
    private = Scope.private("me", "personal", "codex")
    shared = Scope.shared("me", "personal", "project-alpha")
    shared_memory = store.remember("fact", "Project Alpha uses a local SQLite database", shared)

    without_pool = store.recall("Project Alpha local SQLite database", private)
    with_pool = store.recall(
        "Project Alpha local SQLite database", private, shared_pools=["project-alpha"]
    )

    assert all(item.memory.memory_id != shared_memory.memory_id for item in without_pool)
    assert any(item.memory.memory_id == shared_memory.memory_id for item in with_pool)


def test_operation_id_is_idempotent(store: MemoryStore) -> None:
    scope = Scope.private("me", "test", "codex")
    first = store.remember_turn("Idempotent content", "user", scope, operation_id="op-1")
    second = store.remember_turn("Different content is ignored", "user", scope, operation_id="op-1")

    assert first.memory_id == second.memory_id
    assert second.content == "Idempotent content"
    assert store.status()["memories"] == 1


def test_concurrent_operation_id_race_returns_one_record(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"
    barrier = Barrier(2)

    class RacingStore(MemoryStore):
        def __init__(self) -> None:
            self._first_operation_check = True
            super().__init__(path, DeterministicEmbedder(64))

        def _record_for_operation(self, operation_id: str, *, embed: bool):
            record = super()._record_for_operation(operation_id, embed=embed)
            if self._first_operation_check and record is None:
                self._first_operation_check = False
                barrier.wait(timeout=5)
            return record

    with MemoryStore(path, DeterministicEmbedder(64)):
        pass

    def remember_once(content: str) -> str:
        with RacingStore() as racing_store:
            return racing_store.remember(
                "fact",
                content,
                Scope.private("me", "test", "codex"),
                operation_id="concurrent-op",
            ).memory_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        memory_ids = list(executor.map(remember_once, ("first", "second")))

    assert len(set(memory_ids)) == 1
    with MemoryStore(path, DeterministicEmbedder(64)) as verified:
        assert verified.status()["memories"] == 1


def test_correction_supersedes_and_excludes_stale_vector(store: MemoryStore) -> None:
    scope = Scope.private("me", "personal", "codex")
    original = store.remember("preference", "I prefer blue interfaces", scope)
    corrected = store.correct(original.memory_id, "I prefer green interfaces")

    assert corrected.lineage_id == original.lineage_id
    assert corrected.version == 2
    assert corrected.supersedes_memory_id == original.memory_id
    assert store.get(original.memory_id).status == "superseded"

    results = store.recall("interface color preference green", scope, limit=10)
    assert any(item.memory.memory_id == corrected.memory_id for item in results)
    assert all(item.memory.memory_id != original.memory_id for item in results)

    with pytest.raises(KeyError, match="active source memory not found"):
        store.remember(
            "summary",
            "Must not derive from stale content",
            scope,
            source_memory_ids=[original.memory_id],
        )


def test_expired_memory_is_not_recalled(store: MemoryStore) -> None:
    scope = Scope.private("me", "personal", "codex")
    expired = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    record = store.remember("fact", "This fact has expired", scope, expires_at=expired)

    results = store.recall("fact expired", scope)

    assert all(item.memory.memory_id != record.memory_id for item in results)


def test_manifest_rejects_different_embedding_space(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"
    with MemoryStore(path, DeterministicEmbedder(32)):
        pass

    with pytest.raises(StoreCompatibilityError, match="compatibility mismatch"):
        MemoryStore(path, DeterministicEmbedder(64))


class SelectivelyFailingEmbedder(DeterministicEmbedder):
    provider = "selectively-failing-test"

    def __init__(self) -> None:
        super().__init__(32)
        self.should_fail = True

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.should_fail and any("FAIL_ME" in text for text in texts):
            raise RuntimeError("deliberate embedding failure")
        return super().embed_documents(texts)


def test_raw_commit_survives_embedding_failure_and_retries(tmp_path) -> None:
    embedder = SelectivelyFailingEmbedder()
    with MemoryStore(tmp_path / "memory.sqlite3", embedder) as store:
        scope = Scope.private("me", "test", "codex")
        record = store.remember_turn("FAIL_ME but preserve this raw turn", "user", scope)
        assert record.embedding_status == "failed"
        assert "deliberate embedding failure" in (record.embedding_error or "")
        assert store.get(record.memory_id).content == "FAIL_ME but preserve this raw turn"

        embedder.should_fail = False
        outcome = store.process_pending()
        assert outcome == {"processed": 1, "ready": 1, "failed": 0}
        assert store.get(record.memory_id).embedding_status == "ready"


def test_typed_memory_requires_valid_role(store: MemoryStore) -> None:
    scope = Scope.private("me", "test", "codex")
    with pytest.raises(ValueError, match="require a valid role"):
        store.remember("turn", "Missing role", scope)
    with pytest.raises(ValueError, match="only valid for turn"):
        store.remember("fact", "No speaker role", scope, role="user")
