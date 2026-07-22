from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from llm_memory_store import MemoryStore, Scope


def _timestamp(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat(timespec="microseconds")


def test_expiry_purge_removes_safe_rows_and_blocks_live_descendants(
    store: MemoryStore,
) -> None:
    scope = Scope.private("me", "test", "purge")
    expired = _timestamp(timedelta(days=-2))
    cutoff = _timestamp(timedelta(days=-1))

    live_source = store.remember("fact", "Durable source", scope)
    expired_leaf = store.remember(
        "summary",
        "Expired derived leaf",
        scope,
        source_memory_ids=[live_source.memory_id],
        expires_at=expired,
    )
    blocked_source = store.remember(
        "turn", "Expired raw source", scope, role="user", expires_at=expired
    )
    live_summary = store.remember(
        "summary",
        "Durable summary of raw source",
        scope,
        source_memory_ids=[blocked_source.memory_id],
    )
    unrelated_expired = store.remember(
        "fact", "Independent expired fact", scope, expires_at=expired
    )

    preview = store.preview_expiry_purge(cutoff)

    assert set(preview.expired_memory_ids) == {
        expired_leaf.memory_id,
        blocked_source.memory_id,
        unrelated_expired.memory_id,
    }
    assert set(preview.purge_memory_ids) == {
        expired_leaf.memory_id,
        unrelated_expired.memory_id,
    }
    assert preview.blocked_memory_ids == (blocked_source.memory_id,)
    assert preview.blocking_memory_ids == (live_summary.memory_id,)
    assert preview.expired_count == 3
    assert preview.purge_count == 2
    assert preview.blocked_count == 1

    receipt = store.purge_expired(cutoff, expected_digest=preview.digest)

    assert receipt.verified is True
    assert receipt.deleted_memories == 2
    assert receipt.deleted_vectors == 2
    assert receipt.deleted_provenance_edges == 1
    for memory_id in preview.purge_memory_ids:
        with pytest.raises(KeyError):
            store.get(memory_id)
    assert store.get(live_source.memory_id).memory_id == live_source.memory_id
    assert store.get(blocked_source.memory_id).memory_id == blocked_source.memory_id
    assert store.get(live_summary.memory_id).memory_id == live_summary.memory_id


def test_expiry_purge_removes_wholly_expired_correction_lineage(store: MemoryStore) -> None:
    scope = Scope.private("me", "test", "purge")
    expired = _timestamp(timedelta(days=-2))
    cutoff = _timestamp(timedelta(days=-1))
    original = store.remember("preference", "Old preference", scope, expires_at=expired)
    corrected = store.correct(original.memory_id, "Corrected preference")

    preview = store.preview_expiry_purge(cutoff)
    assert set(preview.purge_memory_ids) == {original.memory_id, corrected.memory_id}
    assert preview.blocked_count == 0

    receipt = store.purge_expired(cutoff)

    assert receipt.deleted_memories == 2
    assert receipt.deleted_vectors == 1
    assert receipt.deleted_provenance_edges == 1
    with pytest.raises(KeyError):
        store.get(original.memory_id)
    with pytest.raises(KeyError):
        store.get(corrected.memory_id)


def test_expiry_purge_rejects_stale_digest_without_partial_deletion(store: MemoryStore) -> None:
    scope = Scope.private("me", "test", "purge")
    expired = _timestamp(timedelta(days=-2))
    cutoff = _timestamp(timedelta(days=-1))
    first = store.remember("fact", "First expired fact", scope, expires_at=expired)
    preview = store.preview_expiry_purge(cutoff)
    second = store.remember("fact", "Second expired fact", scope, expires_at=expired)

    with pytest.raises(ValueError, match="preview changed"):
        store.purge_expired(cutoff, expected_digest=preview.digest)

    assert store.get(first.memory_id).memory_id == first.memory_id
    assert store.get(second.memory_id).memory_id == second.memory_id


@pytest.mark.parametrize("as_of", ["not-a-time", "2026-07-19T12:00:00"])
def test_expiry_purge_requires_valid_timezone_aware_cutoff(store: MemoryStore, as_of: str) -> None:
    with pytest.raises(ValueError):
        store.preview_expiry_purge(as_of)


def test_empty_expiry_purge_is_verified(store: MemoryStore) -> None:
    preview = store.preview_expiry_purge("2000-01-01T00:00:00Z")
    receipt = store.purge_expired(preview.cutoff, expected_digest=preview.digest)

    assert preview.expired_count == 0
    assert receipt.deleted_memories == 0
    assert receipt.deleted_vectors == 0
    assert receipt.deleted_provenance_edges == 0
    assert receipt.verified is True
