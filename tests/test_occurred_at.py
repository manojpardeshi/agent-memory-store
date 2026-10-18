from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.importing import import_json_store, preview_json_import

SCOPE = Scope.private("me", "test", "occurred")
LAST_YEAR = "2025-03-15T09:30:00+02:00"
LAST_YEAR_UTC = "2025-03-15T07:30:00.000000+00:00"


def _drop_occurred_at(path: Path) -> None:
    """Return a store to the shape created by a runtime from before occurred_at existed."""
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE memories DROP COLUMN occurred_at")
    connection.commit()
    connection.close()


def test_occurred_at_is_optional_and_absent_by_default(store: MemoryStore) -> None:
    record = store.remember("fact", "The office moved to the fifth floor", SCOPE)
    assert record.occurred_at is None
    assert record.to_dict()["occurred_at"] is None
    assert store.get(record.memory_id).occurred_at is None


def test_occurred_at_is_stored_normalized_to_utc(store: MemoryStore) -> None:
    record = store.remember_turn("We signed the lease today", "user", SCOPE, occurred_at=LAST_YEAR)
    assert record.occurred_at == LAST_YEAR_UTC
    assert store.get(record.memory_id).occurred_at == LAST_YEAR_UTC


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("2025-03-15T09:30:00", "timezone"),
        ((datetime.now(UTC) + timedelta(days=1)).isoformat(), "future"),
        ("yesterday", "Invalid isoformat|invalid"),
    ],
)
def test_occurred_at_is_validated(store: MemoryStore, value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        store.remember("fact", "Validation probe", SCOPE, occurred_at=value)


def test_small_clock_skew_is_tolerated(store: MemoryStore) -> None:
    ahead = (datetime.now(UTC) + timedelta(minutes=2)).isoformat()
    assert store.remember("fact", "Skewed clock", SCOPE, occurred_at=ahead).occurred_at


def test_recall_recency_uses_occurred_at(store: MemoryStore) -> None:
    old = store.remember("fact", "Team lunch is on Fridays", SCOPE, occurred_at=LAST_YEAR)
    new = store.remember("fact", "Team lunch is on Fridays", SCOPE)

    results = {
        r.memory.memory_id: r
        for r in store.recall("team lunch Fridays", SCOPE, limit=2, relevance_filter=None)
    }

    assert results[old.memory_id].semantic_score == pytest.approx(
        results[new.memory_id].semantic_score
    )
    assert results[old.memory_id].recency_score < 0.01
    assert results[new.memory_id].recency_score > 0.99
    assert results[new.memory_id].score > results[old.memory_id].score


def test_expiry_still_counts_from_storage_time(tmp_path: Path) -> None:
    with MemoryStore(tmp_path / "ttl.sqlite3", DeterministicEmbedder(64)) as store:
        turn = store.remember_turn("Imported old message", "user", SCOPE, occurred_at=LAST_YEAR)
        expires = datetime.fromisoformat(turn.expires_at)
        assert expires > datetime.now(UTC) + timedelta(days=29)
        assert store.recall("Imported old message", SCOPE, relevance_filter=None)


def test_context_header_shows_occurred_at_only_when_set(store: MemoryStore) -> None:
    store.remember("fact", "Plain memory about gardens", SCOPE)
    store.remember("event", "Planted tulips in the garden", SCOPE, occurred_at=LAST_YEAR)
    results = store.recall("garden", SCOPE, limit=5, relevance_filter=None)
    bundle = store.context_bundle("garden", results)
    headers = [line for line in bundle["context_text"].splitlines() if line.startswith("[memory")]
    with_time = [h for h in headers if "occurred_at=" in h]
    assert len(headers) == 2 and len(with_time) == 1
    assert f"occurred_at={LAST_YEAR_UTC}" in with_time[0]


def test_correction_keeps_occurred_at(store: MemoryStore) -> None:
    original = store.remember("fact", "The deadline was Monday", SCOPE, occurred_at=LAST_YEAR)
    corrected = store.correct(original.memory_id, "The deadline was Tuesday")
    assert corrected.occurred_at == LAST_YEAR_UTC
    assert corrected.created_at != original.created_at


def test_export_import_round_trip_preserves_occurred_at(tmp_path: Path) -> None:
    embedder = DeterministicEmbedder(64)
    with MemoryStore(tmp_path / "source.sqlite3", embedder) as source:
        dated = source.remember("fact", "Dated memory", SCOPE, occurred_at=LAST_YEAR)
        undated = source.remember("fact", "Undated memory", SCOPE)
        source.export_json(tmp_path / "export.json", all_scopes=True)
    exported = {
        m["memory_id"]: m for m in json.loads((tmp_path / "export.json").read_text())["memories"]
    }
    assert exported[dated.memory_id]["occurred_at"] == LAST_YEAR_UTC
    assert exported[undated.memory_id]["occurred_at"] is None

    destination = tmp_path / "imported.sqlite3"
    preview = preview_json_import(tmp_path / "export.json", destination, embedder)
    import_json_store(
        tmp_path / "export.json", destination, embedder, expected_digest=preview.digest
    )
    with MemoryStore(destination, embedder) as imported:
        assert imported.get(dated.memory_id).occurred_at == LAST_YEAR_UTC
        assert imported.get(undated.memory_id).occurred_at is None


def test_import_of_export_without_the_field_leaves_it_empty(tmp_path: Path) -> None:
    embedder = DeterministicEmbedder(64)
    with MemoryStore(tmp_path / "source.sqlite3", embedder) as source:
        memory = source.remember("fact", "Exported before 0.3", SCOPE)
        source.export_json(tmp_path / "export.json", all_scopes=True)
    document = json.loads((tmp_path / "export.json").read_text())
    for item in document["memories"]:
        item.pop("occurred_at")
    (tmp_path / "old-export.json").write_text(json.dumps(document))
    destination = tmp_path / "imported.sqlite3"
    preview = preview_json_import(tmp_path / "old-export.json", destination, embedder)
    import_json_store(
        tmp_path / "old-export.json", destination, embedder, expected_digest=preview.digest
    )
    with MemoryStore(destination, embedder) as imported:
        assert imported.get(memory.memory_id).occurred_at is None


def test_store_from_before_the_column_is_upgraded_when_opened_writable(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    embedder = DeterministicEmbedder(64)
    with MemoryStore(path, embedder) as store:
        old = store.remember("fact", "Remembered before the upgrade", SCOPE)
    _drop_occurred_at(path)

    with MemoryStore(path, embedder, read_only=True) as read_only:
        assert read_only.has_occurred_at is False
        assert read_only.get(old.memory_id).occurred_at is None
        assert read_only.recall("Remembered before the upgrade", SCOPE, relevance_filter=None)

    with MemoryStore(path, embedder) as upgraded:
        assert upgraded.has_occurred_at is True
        assert upgraded.get(old.memory_id).occurred_at is None
        new = upgraded.remember("fact", "Remembered after", SCOPE, occurred_at=LAST_YEAR)
        assert upgraded.get(new.memory_id).occurred_at == LAST_YEAR_UTC
        assert upgraded.status()["integrity_check"] == "ok"
