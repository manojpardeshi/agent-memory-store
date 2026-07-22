from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import llm_memory_store.importing as importing_module
from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.importing import (
    ImportDocumentError,
    import_json_store,
    preview_json_import,
)


class ImportFailEmbedder(DeterministicEmbedder):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if any("import fact" in text.casefold() for text in texts):
            raise RuntimeError("deliberate import embedding failure")
        return super().embed_documents(texts)


def _export_fixture(tmp_path: Path) -> tuple[Path, Path, DeterministicEmbedder, dict]:
    database = tmp_path / "source.sqlite3"
    export = tmp_path / "export.json"
    embedder = DeterministicEmbedder(64)
    scope = Scope.private("me", "test", "import")
    with MemoryStore(database, embedder) as store:
        original = store.remember(
            "fact", "Original import fact", scope, operation_id="import-operation-1"
        )
        store.remember(
            "summary",
            "Derived import summary",
            scope,
            source_memory_ids=[original.memory_id],
        )
        store.correct(original.memory_id, "Corrected import fact")
        store.export_json(export, all_scopes=True)
    return database, export, embedder, json.loads(export.read_text())


def _memories_by_id(document: dict) -> dict[str, dict]:
    return {memory["memory_id"]: memory for memory in document["memories"]}


def _edge_key(edge: dict) -> tuple[str, str, str]:
    return (edge["child_memory_id"], edge["source_memory_id"], edge["relation"])


def test_v2_json_import_round_trip_preserves_logical_graph_and_operation_ids(tmp_path) -> None:
    source_database, export, embedder, source_document = _export_fixture(tmp_path)
    destination = tmp_path / "imported.sqlite3"
    preview = preview_json_import(export, destination, embedder)

    assert preview.source_format_version == 2
    assert preview.self_contained is True
    assert preview.memory_count == 3
    receipt = import_json_store(
        export, destination, embedder, expected_digest=preview.digest, batch_size=1
    )

    assert receipt["published"] is True
    assert receipt["verified"] is True
    assert receipt["provenance_loss_accepted"] is False
    assert destination.stat().st_mode & 0o777 == 0o600
    round_trip = tmp_path / "round-trip.json"
    with MemoryStore(destination, embedder) as imported:
        imported.export_json(round_trip, all_scopes=True)
        replay = imported.remember(
            "fact",
            "Ignored idempotent replay",
            Scope.private("me", "test", "import"),
            operation_id="import-operation-1",
        )
    round_trip_document = json.loads(round_trip.read_text())
    assert replay.memory_id in _memories_by_id(source_document)
    assert _memories_by_id(round_trip_document) == _memories_by_id(source_document)
    assert sorted(round_trip_document["provenance"], key=_edge_key) == sorted(
        source_document["provenance"], key=_edge_key
    )
    assert round_trip_document["external_source_references"] == []
    with MemoryStore(source_database, embedder) as source:
        assert source.status()["memories"] == 3


def test_v1_import_backfills_hashes_and_reports_missing_operation_ids(tmp_path) -> None:
    _, export, embedder, document = _export_fixture(tmp_path)
    document["format_version"] = 1
    document.pop("external_source_references")
    for memory in document["memories"]:
        memory.pop("content_hash")
        memory.pop("operation_id")
    export.write_text(json.dumps(document))
    destination = tmp_path / "v1-import.sqlite3"

    preview = preview_json_import(export, destination, embedder)
    receipt = import_json_store(export, destination, embedder, expected_digest=preview.digest)

    assert preview.source_format_version == 1
    assert "content_hash backfilled from content" in preview.migration_notes
    assert "operation_id unavailable in v1" in receipt["migration_notes"]
    migrated_export = tmp_path / "migrated-v2.json"
    with MemoryStore(destination, embedder) as imported:
        imported.export_json(migrated_export, all_scopes=True)
    migrated = json.loads(migrated_export.read_text())
    assert migrated["format_version"] == 2
    assert all(memory["operation_id"] is None for memory in migrated["memories"])
    assert all(
        memory["content_hash"] == hashlib.sha256(memory["content"].encode()).hexdigest()
        for memory in migrated["memories"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_id", "duplicate_operation", "bad_hash", "bad_generation", "cycle"],
)
def test_import_rejects_collisions_tampering_and_cycles(tmp_path, mutation: str) -> None:
    _, export, embedder, document = _export_fixture(tmp_path)
    if mutation == "duplicate_id":
        document["memories"].append(dict(document["memories"][0]))
    elif mutation == "duplicate_operation":
        document["memories"][1]["operation_id"] = document["memories"][0]["operation_id"]
    elif mutation == "bad_hash":
        document["memories"][0]["content_hash"] = "0" * 64
    elif mutation == "bad_generation":
        document["memories"][1]["generation"] = 99
    else:
        first, second = document["memories"][:2]
        document["provenance"] = [
            {
                "child_memory_id": first["memory_id"],
                "source_memory_id": second["memory_id"],
                "relation": "derived_from",
            },
            {
                "child_memory_id": second["memory_id"],
                "source_memory_id": first["memory_id"],
                "relation": "derived_from",
            },
        ]
        first["source_memory_ids"] = [second["memory_id"]]
        second["source_memory_ids"] = [first["memory_id"]]
        document["memories"] = [first, second]
    export.write_text(json.dumps(document))

    with pytest.raises(ImportDocumentError):
        preview_json_import(export, tmp_path / "rejected.sqlite3", embedder)
    assert not (tmp_path / "rejected.sqlite3").exists()


def test_partial_export_declares_external_source_and_requires_explicit_loss(tmp_path) -> None:
    database = tmp_path / "partial-source.sqlite3"
    export = tmp_path / "partial.json"
    destination = tmp_path / "partial-import.sqlite3"
    embedder = DeterministicEmbedder(64)
    source_scope = Scope.private("me", "test", "source-app")
    child_scope = Scope.private("me", "test", "child-app")
    with MemoryStore(database, embedder) as store:
        source = store.remember("fact", "External source", source_scope)
        child = store.remember(
            "summary",
            "Selected child",
            child_scope,
            source_memory_ids=[source.memory_id],
        )
        store.export_json(export, child_scope)
    document = json.loads(export.read_text())
    assert document["provenance"] == []
    assert document["external_source_references"][0]["source_memory_id"] == source.memory_id

    strict_preview = preview_json_import(export, destination, embedder)
    assert strict_preview.self_contained is False
    with pytest.raises(ImportDocumentError, match="not self-contained"):
        import_json_store(export, destination, embedder, expected_digest=strict_preview.digest)
    assert not destination.exists()

    loss_preview = preview_json_import(export, destination, embedder, allow_missing_sources=True)
    receipt = import_json_store(
        export,
        destination,
        embedder,
        allow_missing_sources=True,
        expected_digest=loss_preview.digest,
    )
    assert receipt["provenance_loss_accepted"] is True
    assert receipt["dropped_external_source_references"][0]["source_memory_id"] == source.memory_id
    with MemoryStore(destination, embedder) as imported:
        assert imported.get(child.memory_id).source_memory_ids == ()


def test_import_embedding_failure_and_stale_preview_publish_nothing(tmp_path) -> None:
    _, export, _, _ = _export_fixture(tmp_path)
    destination = tmp_path / "failed.sqlite3"
    failing = ImportFailEmbedder(64)
    preview = preview_json_import(export, destination, failing)

    with pytest.raises(RuntimeError, match="deliberate import embedding failure"):
        import_json_store(export, destination, failing, expected_digest=preview.digest)
    assert not destination.exists()

    document = json.loads(export.read_text())
    document["exported_at"] = "changed"
    export.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="preview changed"):
        import_json_store(export, destination, failing, expected_digest=preview.digest)
    assert not destination.exists()


def test_import_atomic_publish_never_clobbers_concurrent_destination(tmp_path, monkeypatch) -> None:
    _, export, embedder, _ = _export_fixture(tmp_path)
    destination = tmp_path / "raced.sqlite3"
    real_link = importing_module.os.link

    def competing_publish(source, target):
        Path(target).write_text("competitor")
        return real_link(source, target)

    monkeypatch.setattr(importing_module.os, "link", competing_publish)
    with pytest.raises(FileExistsError, match="destination already exists"):
        import_json_store(export, destination, embedder)
    assert destination.read_text() == "competitor"
