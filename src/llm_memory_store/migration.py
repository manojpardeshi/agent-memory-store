"""Safe, new-destination embedding-space migration."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import sqlite_vec

from .database import immediate_transaction, utc_now
from .embeddings import Embedder, EmbeddingIdentity, embedding_identity
from .evaluation import load_evaluation_dataset, run_retrieval_evaluation
from .models import RelevanceFilter
from .store import MemoryStore

_SCOPE_COLUMNS = ("id", "kind", "subject", "environment", "owner", "created_at")
_MEMORY_COLUMNS = (
    "id",
    "memory_id",
    "lineage_id",
    "version",
    "scope_id",
    "kind",
    "role",
    "content",
    "content_hash",
    "status",
    "generation",
    "metadata_json",
    "operation_id",
    "created_at",
    "expires_at",
    "supersedes_id",
)


@dataclass(frozen=True, slots=True)
class EmbeddingMigrationPreview:
    source: str
    destination: str
    source_store_id: str
    source_embedding: dict[str, Any]
    target_embedding: dict[str, Any]
    memory_count: int
    active_memory_count: int
    kind_counts: dict[str, int]
    source_logical_digest: str
    quality_dataset: str
    quality_dataset_sha256: str
    destination_available: bool
    digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MigrationQualityError(RuntimeError):
    """Raised when target retrieval quality regresses and no override was given."""

    def __init__(self, report: dict[str, Any]) -> None:
        super().__init__("target embedding quality regressed; destination was not published")
        self.report = report


def _rows(connection: Any, table: str, columns: tuple[str, ...]) -> list[dict[str, Any]]:
    selected = ", ".join(columns)
    return [dict(row) for row in connection.execute(f"SELECT {selected} FROM {table} ORDER BY id")]


def _logical_payload(store: MemoryStore) -> dict[str, Any]:
    edges = [
        dict(row)
        for row in store.connection.execute(
            "SELECT child_id, source_id, relation FROM memory_sources "
            "ORDER BY child_id, source_id, relation"
        )
    ]
    return {
        "scopes": _rows(store.connection, "scopes", _SCOPE_COLUMNS),
        "memories": _rows(store.connection, "memories", _MEMORY_COLUMNS),
        "provenance": edges,
    }


def _logical_digest(store: MemoryStore) -> str:
    payload = json.dumps(_logical_payload(store), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _identity_dict(identity: EmbeddingIdentity) -> dict[str, Any]:
    return dict(identity.to_dict())


def preview_embedding_migration(
    source: str | Path,
    destination: str | Path,
    source_embedder: Embedder,
    target_embedder: Embedder,
    quality_dataset: str | Path,
) -> EmbeddingMigrationPreview:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if source_path == destination_path:
        raise ValueError("source and destination must differ")
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    target_identity = embedding_identity(target_embedder)
    _, dataset_digest = load_evaluation_dataset(quality_dataset)
    with MemoryStore(source_path, source_embedder) as source_store:
        source_identity = source_store.embedding_identity
        if source_identity == target_identity:
            raise ValueError("target embedding identity must differ from the source identity")
        logical_digest = _logical_digest(source_store)
        memory_rows = source_store.connection.execute(
            "SELECT kind, status FROM memories ORDER BY id"
        ).fetchall()
        kind_counts = dict(Counter(str(row["kind"]) for row in memory_rows))
        active_count = sum(row["status"] == "active" for row in memory_rows)
        digest_payload = {
            "source": str(source_path),
            "destination": str(destination_path),
            "source_store_id": source_store.manifest["store_id"],
            "source_embedding": _identity_dict(source_identity),
            "target_embedding": _identity_dict(target_identity),
            "source_logical_digest": logical_digest,
            "quality_dataset_sha256": dataset_digest,
        }
        digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return EmbeddingMigrationPreview(
            source=str(source_path),
            destination=str(destination_path),
            source_store_id=str(source_store.manifest["store_id"]),
            source_embedding=_identity_dict(source_identity),
            target_embedding=_identity_dict(target_identity),
            memory_count=len(memory_rows),
            active_memory_count=active_count,
            kind_counts=kind_counts,
            source_logical_digest=logical_digest,
            quality_dataset=str(Path(quality_dataset).expanduser().resolve()),
            quality_dataset_sha256=dataset_digest,
            destination_available=not destination_path.exists(),
            digest=digest,
        )


def _quality_comparison(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_metrics = source["metrics"]
    target_metrics = target["metrics"]
    checks = {
        "recall_at_k_not_lower": (target_metrics["recall_at_k"] >= source_metrics["recall_at_k"]),
        "mrr_not_lower": target_metrics["mrr"] >= source_metrics["mrr"],
        "distractor_leak_rate_not_higher": (
            target_metrics["distractor_leak_rate"] <= source_metrics["distractor_leak_rate"]
        ),
        "zero_scope_violations": target_metrics["scope_violation_count"] == 0,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "deltas": {
            key: target_metrics[key] - source_metrics[key]
            for key in ("recall_at_k", "mrr", "distractor_leak_rate")
        },
    }


def evaluate_embedding_migration(
    dataset: str | Path, source_embedder: Embedder, target_embedder: Embedder
) -> dict[str, Any]:
    configurations = {
        "default": None,
        "relative_0_20": RelevanceFilter.relative(0.20),
    }
    results: dict[str, Any] = {}
    regression_checks: dict[str, bool] = {}
    for name, relevance_filter in configurations.items():
        source_report = run_retrieval_evaluation(
            dataset, source_embedder, relevance_filter=relevance_filter
        )
        target_report = run_retrieval_evaluation(
            dataset, target_embedder, relevance_filter=relevance_filter
        )
        comparison = _quality_comparison(source_report, target_report)
        regression_checks[name] = bool(comparison["passed"])
        results[name] = {
            "source": source_report,
            "target": target_report,
            "comparison": comparison,
        }
    return {
        "schema_version": 1,
        "completed_at": utc_now(),
        "scope_of_claim": (
            "one synthetic corpus; structural migration and absolute quality are separate"
        ),
        "configurations": results,
        "source_absolute_gate_passed": all(
            result["source"]["passed"] for result in results.values()
        ),
        "target_absolute_gate_passed": all(
            result["target"]["passed"] for result in results.values()
        ),
        "regression_checks": regression_checks,
        "no_regression": all(regression_checks.values()),
    }


def _copy_logical_graph(source: MemoryStore, target: MemoryStore) -> None:
    scopes = _rows(source.connection, "scopes", _SCOPE_COLUMNS)
    memories = [
        dict(row) for row in source.connection.execute("SELECT * FROM memories ORDER BY id")
    ]
    edges = [
        dict(row)
        for row in source.connection.execute(
            "SELECT child_id, source_id, relation FROM memory_sources "
            "ORDER BY child_id, source_id, relation"
        )
    ]
    with immediate_transaction(target.connection):
        for row in scopes:
            target.connection.execute(
                f"INSERT INTO scopes({', '.join(_SCOPE_COLUMNS)}) "
                f"VALUES({', '.join('?' for _ in _SCOPE_COLUMNS)})",
                tuple(row[column] for column in _SCOPE_COLUMNS),
            )
        memory_columns = tuple(memories[0].keys()) if memories else ()
        for row in memories:
            if row["status"] == "active":
                row["embedding_status"] = "pending"
                row["embedding_error"] = None
            target.connection.execute(
                f"INSERT INTO memories({', '.join(memory_columns)}) "
                f"VALUES({', '.join('?' for _ in memory_columns)})",
                tuple(row[column] for column in memory_columns),
            )
        for edge in edges:
            target.connection.execute(
                "INSERT INTO memory_sources(child_id, source_id, relation) VALUES(?, ?, ?)",
                (edge["child_id"], edge["source_id"], edge["relation"]),
            )


def _embed_active_rows(
    store: MemoryStore,
    batch_size: int,
    progress_callback: Callable[[int, int], None] | None = None,
) -> int:
    rows = store.connection.execute(
        "SELECT id, scope_id, content FROM memories WHERE status='active' ORDER BY id"
    ).fetchall()
    embedded = 0
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        vectors = store.embedder.embed_documents([str(row["content"]) for row in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("target embedder returned an unexpected vector count")
        with immediate_transaction(store.connection):
            for row, vector in zip(batch, vectors, strict=True):
                if len(vector) != store.embedding_identity.dimension:
                    raise RuntimeError("target embedder returned an unexpected vector dimension")
                store.connection.execute(
                    "INSERT INTO memory_vectors(rowid, embedding, scope_id) VALUES(?, ?, ?)",
                    (
                        int(row["id"]),
                        sqlite_vec.serialize_float32(vector),
                        int(row["scope_id"]),
                    ),
                )
                store.connection.execute(
                    "UPDATE memories SET embedding_status='ready', embedding_error=NULL WHERE id=?",
                    (int(row["id"]),),
                )
                embedded += 1
        if progress_callback is not None:
            progress_callback(embedded, len(rows))
    return embedded


def migrate_embeddings(
    source: str | Path,
    destination: str | Path,
    source_embedder: Embedder,
    target_embedder: Embedder,
    quality_dataset: str | Path,
    *,
    expected_digest: str | None = None,
    accept_quality_regression: bool = False,
    quality_regression_reason: str | None = None,
    batch_size: int = 64,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    if accept_quality_regression:
        quality_regression_reason = (quality_regression_reason or "").strip()
        if not quality_regression_reason:
            raise ValueError("accepting quality regression requires a written reason")
        if len(quality_regression_reason) > 1000:
            raise ValueError("quality regression reason must be at most 1000 characters")
    elif quality_regression_reason is not None:
        raise ValueError("quality regression reason requires accept_quality_regression=True")
    started = time.perf_counter()
    preview = preview_embedding_migration(
        source, destination, source_embedder, target_embedder, quality_dataset
    )
    if not preview.destination_available:
        raise FileExistsError(f"migration destination already exists: {preview.destination}")
    if expected_digest is not None and expected_digest != preview.digest:
        raise ValueError("embedding migration preview changed; request a new preview")

    quality = evaluate_embedding_migration(quality_dataset, source_embedder, target_embedder)
    if not quality["no_regression"] and not accept_quality_regression:
        raise MigrationQualityError(
            {
                "published": False,
                "preview": preview.to_dict(),
                "quality": quality,
                "failure": "target quality regression",
            }
        )

    source_path = Path(preview.source)
    destination_path = Path(preview.destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with suppress(OSError):
        destination_path.parent.chmod(0o700)

    with tempfile.TemporaryDirectory(
        prefix=f".{destination_path.name}.migration-", dir=destination_path.parent
    ) as directory:
        working = Path(directory)
        snapshot_path = working / "source-snapshot.sqlite3"
        temporary_target = working / "target.sqlite3"
        with MemoryStore(source_path, source_embedder) as live_source:
            live_source.backup(snapshot_path)
        with MemoryStore(snapshot_path, source_embedder) as snapshot:
            snapshot_digest = _logical_digest(snapshot)
            if snapshot_digest != preview.source_logical_digest:
                raise ValueError("source changed after preview; request a new preview")
            with MemoryStore(temporary_target, target_embedder) as target:
                _copy_logical_graph(snapshot, target)
                embedded_count = _embed_active_rows(
                    target, batch_size, progress_callback=progress_callback
                )
                target_digest = _logical_digest(target)
                status = target.status()
                if target_digest != snapshot_digest:
                    raise RuntimeError("destination logical content differs from source snapshot")
                if status["integrity_check"] != "ok":
                    raise RuntimeError("destination integrity check failed")
                if status["orphan_vectors"] or status["missing_vectors"]:
                    raise RuntimeError("destination vector verification failed")
                if target.embedding_identity.to_dict() != preview.target_embedding:
                    raise RuntimeError("destination embedding identity differs from preview")
                target.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        try:
            os.link(temporary_target, destination_path)
        except FileExistsError as exc:
            raise FileExistsError(
                f"migration destination already exists: {destination_path}"
            ) from exc
        temporary_target.unlink()
        destination_path.chmod(0o600)

    return {
        "published": True,
        "destination": str(destination_path),
        "preview": preview.to_dict(),
        "source_logical_digest": preview.source_logical_digest,
        "destination_logical_digest": preview.source_logical_digest,
        "embedded_active_memories": embedded_count,
        "quality_regression_accepted": bool(
            accept_quality_regression and not quality["no_regression"]
        ),
        "quality_regression_override": {
            "requested": accept_quality_regression,
            "reason": quality_regression_reason,
            "operator_boundary": "trusted_local_os_user",
        },
        "quality": quality,
        "verified": True,
        "completed_at": utc_now(),
        "runtime_seconds": time.perf_counter() - started,
    }
