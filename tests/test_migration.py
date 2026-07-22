from __future__ import annotations

from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store import migration as migration_module
from llm_memory_store.migration import (
    MigrationQualityError,
    migrate_embeddings,
    preview_embedding_migration,
)

QUALITY_DATASET = Path(__file__).parents[1] / "evaluation" / "retrieval_v1.json"


class ConstantTargetEmbedder:
    provider = "constant-test"
    model_name = "constant-test-v1"
    model_revision = "1"
    runtime_version = "1"
    dimension = 8

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_embedding_migration_preserves_logical_graph_and_rebuilds_vectors(tmp_path) -> None:
    source_path = tmp_path / "source.sqlite3"
    destination = tmp_path / "migrated.sqlite3"
    source_embedder = DeterministicEmbedder(64)
    target_embedder = DeterministicEmbedder(96)
    scope = Scope.private("me", "test", "migration")
    with MemoryStore(source_path, source_embedder) as source:
        original = source.remember(
            "fact",
            "Original project fact",
            scope,
            operation_id="migration-op-1",
        )
        derived = source.remember(
            "summary",
            "Summary derived from the original",
            scope,
            source_memory_ids=[original.memory_id],
        )
        corrected = source.correct(original.memory_id, "Corrected project fact")
        source_export = source.export_data(all_scopes=True)

    preview = preview_embedding_migration(
        source_path,
        destination,
        source_embedder,
        target_embedder,
        QUALITY_DATASET,
    )
    assert preview.memory_count == 3
    assert preview.active_memory_count == 2
    assert preview.destination_available is True
    assert preview.source_embedding["dimension"] == 64
    assert preview.target_embedding["dimension"] == 96

    receipt = migrate_embeddings(
        source_path,
        destination,
        source_embedder,
        target_embedder,
        QUALITY_DATASET,
        expected_digest=preview.digest,
        accept_quality_regression=True,
        quality_regression_reason="Test permits deterministic dimension comparison",
        batch_size=1,
    )

    assert receipt["published"] is True
    assert receipt["verified"] is True
    assert receipt["embedded_active_memories"] == 2
    assert destination.stat().st_mode & 0o777 == 0o600
    with MemoryStore(destination, target_embedder) as migrated:
        migrated_export = migrated.export_data(all_scopes=True)
        assert migrated.status()["missing_vectors"] == 0
        assert migrated.status()["orphan_vectors"] == 0
        assert migrated.embedding_identity.dimension == 96
        assert migrated.get(derived.memory_id).source_memory_ids == (original.memory_id,)
        assert migrated.get(corrected.memory_id).supersedes_memory_id == original.memory_id
        replay = migrated.remember(
            "fact", "Ignored duplicate operation", scope, operation_id="migration-op-1"
        )
        assert replay.memory_id == original.memory_id
    assert migrated_export["memories"] == source_export["memories"]
    assert migrated_export["provenance"] == source_export["provenance"]
    with MemoryStore(source_path, source_embedder) as unchanged:
        assert unchanged.export_data(all_scopes=True)["memories"] == source_export["memories"]


def test_embedding_migration_blocks_quality_regression_and_publishes_nothing(tmp_path) -> None:
    source_path = tmp_path / "source.sqlite3"
    destination = tmp_path / "must-not-exist.sqlite3"
    source_embedder = DeterministicEmbedder(64)
    with MemoryStore(source_path, source_embedder) as source:
        source.remember("fact", "Source fixture", Scope.private("me", "test", "migration"))

    with pytest.raises(MigrationQualityError) as raised:
        migrate_embeddings(
            source_path,
            destination,
            source_embedder,
            ConstantTargetEmbedder(),
            QUALITY_DATASET,
        )

    assert raised.value.report["published"] is False
    assert raised.value.report["quality"]["no_regression"] is False
    assert not destination.exists()


def test_embedding_migration_rejects_stale_preview_and_existing_destination(tmp_path) -> None:
    source_path = tmp_path / "source.sqlite3"
    destination = tmp_path / "destination.sqlite3"
    source_embedder = DeterministicEmbedder(64)
    target_embedder = DeterministicEmbedder(96)
    scope = Scope.private("me", "test", "migration")
    with MemoryStore(source_path, source_embedder) as source:
        source.remember("fact", "First source fixture", scope)
    preview = preview_embedding_migration(
        source_path, destination, source_embedder, target_embedder, QUALITY_DATASET
    )
    with MemoryStore(source_path, source_embedder) as source:
        source.remember("fact", "Changed after preview", scope)

    with pytest.raises(ValueError, match="preview changed"):
        migrate_embeddings(
            source_path,
            destination,
            source_embedder,
            target_embedder,
            QUALITY_DATASET,
            expected_digest=preview.digest,
        )
    assert not destination.exists()

    destination.write_text("keep")
    with pytest.raises(FileExistsError, match="destination already exists"):
        migrate_embeddings(
            source_path,
            destination,
            source_embedder,
            target_embedder,
            QUALITY_DATASET,
        )
    assert destination.read_text() == "keep"


def test_embedding_migration_atomic_publish_never_clobbers_concurrent_destination(
    tmp_path, monkeypatch
) -> None:
    source_path = tmp_path / "source.sqlite3"
    destination = tmp_path / "raced.sqlite3"
    source_embedder = DeterministicEmbedder(64)
    target_embedder = DeterministicEmbedder(96)
    with MemoryStore(source_path, source_embedder) as source:
        source.remember("fact", "Race fixture", Scope.private("me", "test", "migration"))
    monkeypatch.setattr(
        migration_module,
        "evaluate_embedding_migration",
        lambda *_: {
            "no_regression": True,
            "source_absolute_gate_passed": False,
            "target_absolute_gate_passed": False,
        },
    )
    real_link = migration_module.os.link

    def competing_publish(source, target):
        Path(target).write_text("competitor")
        return real_link(source, target)

    monkeypatch.setattr(migration_module.os, "link", competing_publish)

    with pytest.raises(FileExistsError, match="destination already exists"):
        migrate_embeddings(
            source_path,
            destination,
            source_embedder,
            target_embedder,
            QUALITY_DATASET,
        )
    assert destination.read_text() == "competitor"
