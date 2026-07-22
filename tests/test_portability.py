from __future__ import annotations

import json

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.database import restore_database


def test_json_export_contains_versions_and_provenance(store: MemoryStore, tmp_path) -> None:
    scope = Scope.private("me", "personal", "codex")
    source = store.remember_turn("Source content", "user", scope)
    derived = store.remember("fact", "Derived content", scope, source_memory_ids=[source.memory_id])
    destination = tmp_path / "export.json"

    result = store.export_json(destination, scope)
    data = json.loads(destination.read_text())

    assert result["memories"] == 2
    assert data["format_version"] == 2
    assert {item["memory_id"] for item in data["memories"]} == {
        source.memory_id,
        derived.memory_id,
    }
    assert data["provenance"][0]["child_memory_id"] == derived.memory_id
    assert data["provenance"][0]["source_memory_id"] == source.memory_id
    assert data["external_source_references"] == []
    assert data["memories"][0]["content_hash"]
    assert "operation_id" in data["memories"][0]
    assert destination.stat().st_mode & 0o777 == 0o600


def test_subject_export_spans_private_and_shared_scopes(store: MemoryStore) -> None:
    store.remember("fact", "Private", Scope.private("me", "personal", "codex"))
    store.remember("fact", "Shared", Scope.shared("me", "personal", "pool"))
    store.remember("fact", "Someone else", Scope.private("other", "personal", "codex"))

    exported = store.export_data(subject="me")

    assert {item["content"] for item in exported["memories"]} == {"Private", "Shared"}


def test_backup_restore_round_trip(store: MemoryStore, tmp_path) -> None:
    scope = Scope.private("me", "personal", "codex")
    first = store.remember("fact", "Included in backup", scope)
    backup = tmp_path / "backup.sqlite3"
    store.backup(backup)
    assert backup.stat().st_mode & 0o777 == 0o600
    store.remember("fact", "Not included in backup", scope)

    restored = tmp_path / "restored.sqlite3"
    restore_database(backup, restored)
    assert restored.stat().st_mode & 0o777 == 0o600
    with MemoryStore(restored, DeterministicEmbedder(64)) as restored_store:
        exported = restored_store.export_data(all_scopes=True)
        assert [item["memory_id"] for item in exported["memories"]] == [first.memory_id]
        assert restored_store.status()["integrity_check"] == "ok"
        assert restored_store.status()["orphan_vectors"] == 0


def test_portability_operations_do_not_clobber_by_default(store: MemoryStore, tmp_path) -> None:
    scope = Scope.private("me", "personal", "codex")
    store.remember("fact", "Sensitive", scope)
    export = tmp_path / "export.json"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"

    store.export_json(export, scope)
    with pytest.raises(FileExistsError):
        store.export_json(export, scope)
    store.backup(backup)
    with pytest.raises(FileExistsError):
        store.backup(backup)
    restored.write_text("keep me")
    with pytest.raises(FileExistsError, match="restore destination already exists"):
        restore_database(backup, restored)
    assert restored.read_text() == "keep me"


def test_whole_store_export_requires_explicit_selector(store: MemoryStore) -> None:
    with pytest.raises(ValueError, match="select exactly one"):
        store.export_data()
    assert store.export_data(all_scopes=True)["all_scopes"] is True
