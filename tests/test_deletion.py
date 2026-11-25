from __future__ import annotations

import sqlite3

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope


def test_delete_preview_and_cascade_cover_lineages_and_descendants(store: MemoryStore) -> None:
    scope = Scope.private("me", "personal", "codex")
    source = store.remember_turn("My editor theme is dark", "user", scope)
    fact = store.remember(
        "fact",
        "The user prefers a dark editor theme",
        scope,
        source_memory_ids=[source.memory_id],
    )
    corrected_fact = store.correct(fact.memory_id, "The user prefers solarized dark")
    unrelated = store.remember("fact", "Unrelated memory", scope)

    preview = store.preview_forget(source.memory_id)

    assert set(preview.memory_ids) == {
        source.memory_id,
        fact.memory_id,
        corrected_fact.memory_id,
    }
    assert unrelated.memory_id not in preview.memory_ids

    receipt = store.forget(source.memory_id)

    assert receipt.verified is True
    assert receipt.deleted_memories == 3
    for memory_id in preview.memory_ids:
        try:
            store.get(memory_id)
        except KeyError:
            pass
        else:
            raise AssertionError(f"deleted memory still exists: {memory_id}")
    assert store.get(unrelated.memory_id).memory_id == unrelated.memory_id
    assert store.status()["orphan_vectors"] == 0


def test_forget_scope_deletes_cross_scope_derived_descendants(store: MemoryStore) -> None:
    private = Scope.private("me", "test", "codex")
    shared = Scope.shared("me", "test", "pool")
    source = store.remember_turn("Private source", "user", private)
    derived = store.remember(
        "summary", "Shared derived summary", shared, source_memory_ids=[source.memory_id]
    )

    preview = store.preview_forget_scope(private)
    assert set(preview.memory_ids) == {source.memory_id, derived.memory_id}

    receipt = store.forget_scope(private)
    assert receipt.verified is True
    assert store.status()["memories"] == 0


def test_forget_empty_scope_is_idempotent(store: MemoryStore) -> None:
    receipt = store.forget_scope(Scope.private("me", "test", "missing"))
    assert receipt.verified is True
    assert receipt.deleted_memories == 0


def test_forget_rejects_stale_descendant_preview_without_deleting(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"
    scope = Scope.private("me", "test", "agent")
    with (
        MemoryStore(path, DeterministicEmbedder()) as deleting,
        MemoryStore(path, DeterministicEmbedder()) as writing,
    ):
        source = deleting.remember("fact", "Source fact", scope)
        preview = deleting.preview_forget(source.memory_id)
        child = writing.remember(
            "summary", "Derived summary", scope, source_memory_ids=[source.memory_id]
        )

        with pytest.raises(ValueError, match="preview changed"):
            deleting.forget(source.memory_id, expected_digest=preview.digest)
        assert deleting.get(child.memory_id).source_memory_ids == (source.memory_id,)
        assert deleting.get(source.memory_id).memory_id == source.memory_id

        receipt = deleting.forget(
            source.memory_id,
            expected_digest=deleting.preview_forget(source.memory_id).digest,
        )
        assert receipt.verified is True
        assert receipt.deleted_memories == 2
        with pytest.raises(KeyError):
            deleting.get(child.memory_id)


def test_forget_holds_write_lock_while_selecting_descendants(tmp_path, monkeypatch) -> None:
    path = tmp_path / "memory.sqlite3"
    scope = Scope.private("me", "test", "agent")
    with (
        MemoryStore(path, DeterministicEmbedder()) as deleting,
        MemoryStore(path, DeterministicEmbedder()) as writing,
    ):
        source = deleting.remember("fact", "Source fact", scope)
        writing.connection.execute("PRAGMA busy_timeout=100")
        original_preview = deleting.preview_forget

        def preview_during_delete(memory_id: str):
            assert deleting.connection.in_transaction
            preview = original_preview(memory_id)
            with pytest.raises(sqlite3.OperationalError, match="database is locked"):
                writing.remember(
                    "summary", "Concurrent derived summary", scope, source_memory_ids=[memory_id]
                )
            return preview

        monkeypatch.setattr(deleting, "preview_forget", preview_during_delete)
        receipt = deleting.forget(source.memory_id)
        assert receipt.verified is True
        assert receipt.deleted_memories == 1
        assert deleting.status()["memories"] == 0


def test_forget_scope_rejects_stale_preview(tmp_path) -> None:
    path = tmp_path / "memory.sqlite3"
    scope = Scope.private("me", "test", "agent")
    with MemoryStore(path, DeterministicEmbedder()) as store:
        preview = store.preview_forget_scope(scope)
        assert preview.count == 0
        memory = store.remember("fact", "New memory", scope)
        with pytest.raises(ValueError, match="preview changed"):
            store.forget_scope(scope, expected_digest=preview.digest)
        assert store.get(memory.memory_id).memory_id == memory.memory_id
