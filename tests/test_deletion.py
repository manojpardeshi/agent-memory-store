from __future__ import annotations

from llm_memory_store import MemoryStore, Scope


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
