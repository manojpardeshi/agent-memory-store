"""Validated JSON format migration and failure-atomic store import."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import immediate_transaction, utc_now
from .embeddings import Embedder, embedding_identity
from .migration import _embed_active_rows
from .models import Scope
from .store import MAX_CONTENT_LENGTH, MemoryStore

MAX_IMPORT_BYTES = 100 * 1024 * 1024
MAX_IMPORT_MEMORIES = 100_000
MAX_IMPORT_REFERENCES = 500_000
_KINDS = {"turn", "fact", "preference", "summary", "event"}
_ROLES = {"user", "assistant", "system", "tool"}
_RELATIONS = {"derived_from", "summarizes", "supersedes", "observed_from"}


class ImportDocumentError(ValueError):
    """Raised when an import document violates the interchange contract."""


@dataclass(frozen=True, slots=True)
class JsonImportPreview:
    source: str
    destination: str
    file_sha256: str
    file_size_bytes: int
    source_format_version: int
    target_format_version: int
    memory_count: int
    active_memory_count: int
    kind_counts: dict[str, int]
    provenance_count: int
    external_source_reference_count: int
    self_contained: bool
    allow_missing_sources: bool
    target_embedding: dict[str, Any]
    source_manifest: dict[str, Any]
    migration_notes: tuple[str, ...]
    destination_available: bool
    digest: str

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["migration_notes"] = list(self.migration_notes)
        return value


def _required_string(value: Any, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImportDocumentError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise ImportDocumentError(f"{field} must be at most {maximum} characters")
    return value


def _timestamp(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    raw = _required_string(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportDocumentError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ImportDocumentError(f"{field} must include a timezone")
    return parsed.astimezone(UTC).isoformat(timespec="microseconds")


def _reject_json_constant(constant: str) -> None:
    raise ImportDocumentError(f"non-standard JSON constant: {constant}")


def _load_json(path: Path) -> tuple[dict[str, Any], bytes, str]:
    size = path.stat().st_size
    if size > MAX_IMPORT_BYTES:
        raise ImportDocumentError(f"import file exceeds {MAX_IMPORT_BYTES} bytes")
    raw = path.read_bytes()
    try:
        value = json.loads(raw, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise ImportDocumentError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ImportDocumentError("import root must be an object")
    return value, raw, hashlib.sha256(raw).hexdigest()


def _canonical_document(path: Path) -> tuple[dict[str, Any], str, tuple[str, ...]]:
    value, _, file_digest = _load_json(path)
    if value.get("format") != "llm-memory-export":
        raise ImportDocumentError("unsupported import format")
    version = value.get("format_version")
    if version not in (1, 2):
        raise ImportDocumentError("supported format_version values are 1 and 2")
    raw_memories = value.get("memories")
    raw_edges = value.get("provenance")
    raw_manifest = value.get("manifest")
    if not isinstance(raw_memories, list):
        raise ImportDocumentError("memories must be a list")
    if len(raw_memories) > MAX_IMPORT_MEMORIES:
        raise ImportDocumentError("memory count exceeds import limit")
    if not isinstance(raw_edges, list):
        raise ImportDocumentError("provenance must be a list")
    raw_external = value.get("external_source_references", []) if version == 2 else []
    if not isinstance(raw_external, list):
        raise ImportDocumentError("external_source_references must be a list")
    if len(raw_edges) + len(raw_external) > MAX_IMPORT_REFERENCES:
        raise ImportDocumentError("provenance reference count exceeds import limit")
    if not isinstance(raw_manifest, dict):
        raise ImportDocumentError("manifest must be an object")

    memories: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    operation_ids: set[str] = set()
    lineage_versions: set[tuple[str, int]] = set()
    notes: list[str] = []
    if version == 1:
        notes.extend(("content_hash backfilled from content", "operation_id unavailable in v1"))
    for index, item in enumerate(raw_memories):
        if not isinstance(item, dict):
            raise ImportDocumentError(f"memories[{index}] must be an object")
        memory_id = _required_string(item.get("memory_id"), f"memories[{index}].memory_id")
        if memory_id in by_id:
            raise ImportDocumentError(f"duplicate memory_id: {memory_id}")
        lineage_id = _required_string(item.get("lineage_id"), f"memories[{index}].lineage_id")
        version_number = item.get("version")
        generation = item.get("generation")
        if (
            not isinstance(version_number, int)
            or isinstance(version_number, bool)
            or version_number < 1
        ):
            raise ImportDocumentError(f"memories[{index}].version must be a positive integer")
        if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
            raise ImportDocumentError(f"memories[{index}].generation must be non-negative")
        lineage_key = (lineage_id, version_number)
        if lineage_key in lineage_versions:
            raise ImportDocumentError("duplicate lineage/version pair")
        lineage_versions.add(lineage_key)
        kind = item.get("kind")
        role = item.get("role")
        if kind not in _KINDS:
            raise ImportDocumentError(f"memories[{index}].kind is invalid")
        if (kind == "turn" and role not in _ROLES) or (kind != "turn" and role is not None):
            raise ImportDocumentError(f"memories[{index}].role is invalid for its kind")
        content = _required_string(
            item.get("content"), f"memories[{index}].content", maximum=MAX_CONTENT_LENGTH
        )
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        content_hash = expected_hash if version == 1 else item.get("content_hash")
        if content_hash != expected_hash:
            raise ImportDocumentError(f"content hash mismatch for memory {memory_id}")
        status = item.get("status")
        if status not in {"active", "superseded"}:
            raise ImportDocumentError(f"memories[{index}].status is invalid")
        embedding_status = item.get("embedding_status", "pending")
        embedding_error = item.get("embedding_error")
        if embedding_status not in {"pending", "ready", "failed"}:
            raise ImportDocumentError(f"memories[{index}].embedding_status is invalid")
        if embedding_error is not None and (
            not isinstance(embedding_error, str) or len(embedding_error) > 2000
        ):
            raise ImportDocumentError(f"memories[{index}].embedding_error is invalid")
        scope_value = item.get("scope")
        if not isinstance(scope_value, dict):
            raise ImportDocumentError(f"memories[{index}].scope must be an object")
        try:
            scope = Scope(
                scope_value.get("kind"),
                scope_value.get("subject"),
                scope_value.get("environment"),
                scope_value.get("owner"),
            )
        except (TypeError, ValueError) as exc:
            raise ImportDocumentError(f"invalid scope for memory {memory_id}: {exc}") from exc
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            raise ImportDocumentError(f"memories[{index}].metadata must be an object")
        metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        if len(metadata_json) > 100_000:
            raise ImportDocumentError(f"metadata is too large for memory {memory_id}")
        operation_id = item.get("operation_id") if version == 2 else None
        if operation_id is not None:
            operation_id = _required_string(operation_id, "operation_id", maximum=1000)
            if operation_id in operation_ids:
                raise ImportDocumentError(f"duplicate operation_id: {operation_id}")
            operation_ids.add(operation_id)
        source_ids = item.get("source_memory_ids", [])
        if not isinstance(source_ids, list) or any(not isinstance(v, str) for v in source_ids):
            raise ImportDocumentError(f"memories[{index}].source_memory_ids must be strings")
        if len(source_ids) != len(set(source_ids)):
            raise ImportDocumentError(f"duplicate source ID for memory {memory_id}")
        supersedes = item.get("supersedes_memory_id")
        if supersedes is not None and not isinstance(supersedes, str):
            raise ImportDocumentError(f"invalid supersedes ID for memory {memory_id}")
        canonical = {
            "memory_id": memory_id,
            "lineage_id": lineage_id,
            "version": version_number,
            "scope": scope.to_dict(),
            "kind": kind,
            "role": role,
            "content": content,
            "content_hash": content_hash,
            "status": status,
            "generation": generation,
            "embedding_status": embedding_status,
            "embedding_error": embedding_error,
            "metadata": metadata,
            "metadata_json": metadata_json,
            "operation_id": operation_id,
            "created_at": _timestamp(item.get("created_at"), "created_at"),
            "expires_at": _timestamp(item.get("expires_at"), "expires_at", optional=True),
            "supersedes_memory_id": supersedes,
            "source_memory_ids": tuple(source_ids),
        }
        memories.append(canonical)
        by_id[memory_id] = canonical

    internal_edges: list[dict[str, Any]] = []
    external_edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    tagged_edges = [(edge, False) for edge in raw_edges]
    tagged_edges.extend((edge, True) for edge in raw_external)
    for index, (edge, declared_external) in enumerate(tagged_edges):
        if not isinstance(edge, dict):
            raise ImportDocumentError(f"provenance[{index}] must be an object")
        child = _required_string(edge.get("child_memory_id"), "child_memory_id")
        source = _required_string(edge.get("source_memory_id"), "source_memory_id")
        relation = edge.get("relation")
        if relation not in _RELATIONS:
            raise ImportDocumentError("invalid provenance relation")
        key = (child, source, relation)
        if key in seen_edges:
            raise ImportDocumentError("duplicate provenance edge")
        seen_edges.add(key)
        if child not in by_id:
            raise ImportDocumentError(f"provenance child is missing: {child}")
        canonical_edge = {
            "child_memory_id": child,
            "source_memory_id": source,
            "relation": relation,
        }
        if source in by_id:
            if version == 2 and declared_external:
                raise ImportDocumentError("external source reference points to included memory")
            internal_edges.append(canonical_edge)
        else:
            if version == 2 and not declared_external:
                raise ImportDocumentError("v2 dangling edge must be externally declared")
            source_generation = edge.get("source_generation")
            source_hash = edge.get("source_content_hash")
            if version == 2:
                if not isinstance(source_generation, int) or source_generation < 0:
                    raise ImportDocumentError("external source generation is invalid")
                if (
                    not isinstance(source_hash, str)
                    or len(source_hash) != 64
                    or any(character not in "0123456789abcdef" for character in source_hash)
                ):
                    raise ImportDocumentError("external source hash is invalid")
            canonical_edge.update(
                {"source_generation": source_generation, "source_content_hash": source_hash}
            )
            external_edges.append(canonical_edge)

    edges_by_child: dict[str, set[str]] = defaultdict(set)
    for edge in [*internal_edges, *external_edges]:
        edges_by_child[edge["child_memory_id"]].add(edge["source_memory_id"])
    for memory in memories:
        if set(memory["source_memory_ids"]) != edges_by_child[memory["memory_id"]]:
            raise ImportDocumentError(
                f"source IDs and provenance disagree for memory {memory['memory_id']}"
            )

    _validate_lineages_and_graph(memories, by_id, internal_edges, external_edges, version)
    return (
        {
            "source_format_version": version,
            "manifest": raw_manifest,
            "memories": memories,
            "internal_edges": internal_edges,
            "external_edges": external_edges,
        },
        file_digest,
        tuple(notes),
    )


def _validate_lineages_and_graph(
    memories: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    internal_edges: list[dict[str, Any]],
    external_edges: list[dict[str, Any]],
    source_version: int,
) -> None:
    lineages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for memory in memories:
        lineages[memory["lineage_id"]].append(memory)
    edge_keys = {
        (edge["child_memory_id"], edge["source_memory_id"], edge["relation"])
        for edge in internal_edges
    }
    for lineage in lineages.values():
        lineage.sort(key=lambda item: item["version"])
        if [item["version"] for item in lineage] != list(range(1, len(lineage) + 1)):
            raise ImportDocumentError("lineage versions must be contiguous from 1")
        active = [item for item in lineage if item["status"] == "active"]
        if len(active) != 1 or active[0] is not lineage[-1]:
            raise ImportDocumentError("each lineage must have one active highest version")
        for index, memory in enumerate(lineage):
            expected = None if index == 0 else lineage[index - 1]["memory_id"]
            if memory["supersedes_memory_id"] != expected:
                raise ImportDocumentError("invalid supersession chain")
            if (
                expected is not None
                and (memory["memory_id"], expected, "supersedes") not in edge_keys
            ):
                raise ImportDocumentError("supersession edge is missing")

    children: dict[str, list[str]] = defaultdict(list)
    indegree = {memory_id: 0 for memory_id in by_id}
    generations: dict[str, list[int]] = defaultdict(list)
    for edge in internal_edges:
        child = edge["child_memory_id"]
        source = edge["source_memory_id"]
        children[source].append(child)
        indegree[child] += 1
        generations[child].append(by_id[source]["generation"])
    for edge in external_edges:
        if source_version == 2:
            generations[edge["child_memory_id"]].append(edge["source_generation"])
    queue = deque(memory_id for memory_id, count in indegree.items() if count == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for child in children.get(current, ()):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(by_id):
        raise ImportDocumentError("provenance graph contains a cycle")
    for memory in memories:
        source_generations = generations[memory["memory_id"]]
        if source_generations or source_version == 2 or not memory["source_memory_ids"]:
            expected_generation = max(source_generations, default=-1) + 1
            if memory["generation"] != expected_generation:
                raise ImportDocumentError(f"invalid generation for memory {memory['memory_id']}")


def _compatible_manifest(manifest: dict[str, Any], target: dict[str, Any]) -> None:
    fields = {
        "embedding_provider": "provider",
        "model_name": "model_name",
        "model_revision": "model_revision",
        "dimension": "dimension",
        "normalized": "normalized",
        "distance_metric": "distance_metric",
        "behavior_fingerprint": "behavior_fingerprint",
    }
    mismatches = [
        source
        for source, destination in fields.items()
        if manifest.get(source) != target[destination]
    ]
    if mismatches:
        raise ImportDocumentError(
            "export embedding manifest is incompatible with target: " + ", ".join(mismatches)
        )


def preview_json_import(
    source: str | Path,
    destination: str | Path,
    embedder: Embedder,
    *,
    allow_missing_sources: bool = False,
) -> JsonImportPreview:
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if source_path == destination_path:
        raise ValueError("source and destination must differ")
    document, file_digest, notes = _canonical_document(source_path)
    target_identity = embedding_identity(embedder).to_dict()
    _compatible_manifest(document["manifest"], target_identity)
    memories = document["memories"]
    digest_payload = {
        "source": str(source_path),
        "destination": str(destination_path),
        "file_sha256": file_digest,
        "target_embedding": target_identity,
        "allow_missing_sources": allow_missing_sources,
    }
    digest = hashlib.sha256(
        json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return JsonImportPreview(
        source=str(source_path),
        destination=str(destination_path),
        file_sha256=file_digest,
        file_size_bytes=source_path.stat().st_size,
        source_format_version=document["source_format_version"],
        target_format_version=2,
        memory_count=len(memories),
        active_memory_count=sum(memory["status"] == "active" for memory in memories),
        kind_counts=dict(Counter(memory["kind"] for memory in memories)),
        provenance_count=len(document["internal_edges"]),
        external_source_reference_count=len(document["external_edges"]),
        self_contained=not document["external_edges"],
        allow_missing_sources=allow_missing_sources,
        target_embedding=target_identity,
        source_manifest=document["manifest"],
        migration_notes=notes,
        destination_available=not destination_path.exists(),
        digest=digest,
    )


def _populate_store(store: MemoryStore, document: dict[str, Any]) -> None:
    memories = sorted(document["memories"], key=lambda item: (item["lineage_id"], item["version"]))
    scopes: dict[tuple[str, str, str, str], int] = {}
    internal_ids: dict[str, int] = {}
    with immediate_transaction(store.connection):
        for memory in memories:
            scope = memory["scope"]
            key = (scope["kind"], scope["subject"], scope["environment"], scope["owner"])
            if key not in scopes:
                cursor = store.connection.execute(
                    "INSERT INTO scopes(kind, subject, environment, owner, created_at) "
                    "VALUES(?, ?, ?, ?, ?)",
                    (*key, memory["created_at"]),
                )
                scopes[key] = int(cursor.lastrowid)
            supersedes_id = (
                internal_ids[memory["supersedes_memory_id"]]
                if memory["supersedes_memory_id"] is not None
                else None
            )
            embedding_status = (
                "pending" if memory["status"] == "active" else memory["embedding_status"]
            )
            embedding_error = None if memory["status"] == "active" else memory["embedding_error"]
            cursor = store.connection.execute(
                """
                INSERT INTO memories(
                    memory_id, lineage_id, version, scope_id, kind, role, content,
                    content_hash, status, generation, embedding_status, embedding_error,
                    metadata_json, operation_id, created_at, expires_at, supersedes_id
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory["memory_id"],
                    memory["lineage_id"],
                    memory["version"],
                    scopes[key],
                    memory["kind"],
                    memory["role"],
                    memory["content"],
                    memory["content_hash"],
                    memory["status"],
                    memory["generation"],
                    embedding_status,
                    embedding_error,
                    memory["metadata_json"],
                    memory["operation_id"],
                    memory["created_at"],
                    memory["expires_at"],
                    supersedes_id,
                ),
            )
            internal_ids[memory["memory_id"]] = int(cursor.lastrowid)
        for edge in document["internal_edges"]:
            store.connection.execute(
                "INSERT INTO memory_sources(child_id, source_id, relation) VALUES(?, ?, ?)",
                (
                    internal_ids[edge["child_memory_id"]],
                    internal_ids[edge["source_memory_id"]],
                    edge["relation"],
                ),
            )


def import_json_store(
    source: str | Path,
    destination: str | Path,
    embedder: Embedder,
    *,
    allow_missing_sources: bool = False,
    expected_digest: str | None = None,
    batch_size: int = 64,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be between 1 and 1000")
    started = time.perf_counter()
    preview = preview_json_import(
        source, destination, embedder, allow_missing_sources=allow_missing_sources
    )
    if not preview.destination_available:
        raise FileExistsError(f"import destination already exists: {preview.destination}")
    if expected_digest is not None and expected_digest != preview.digest:
        raise ValueError("JSON import preview changed; request a new preview")
    document, current_digest, notes = _canonical_document(Path(preview.source))
    if current_digest != preview.file_sha256:
        raise ValueError("JSON import file changed after preview")
    if document["external_edges"] and not allow_missing_sources:
        raise ImportDocumentError(
            "import is not self-contained; preview with allow_missing_sources explicitly"
        )

    destination_path = Path(preview.destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with suppress(OSError):
        destination_path.parent.chmod(0o700)
    with tempfile.TemporaryDirectory(
        prefix=f".{destination_path.name}.import-", dir=destination_path.parent
    ) as directory:
        temporary = Path(directory) / "import.sqlite3"
        with MemoryStore(temporary, embedder) as target:
            _populate_store(target, document)
            embedded = _embed_active_rows(target, batch_size, progress_callback=progress_callback)
            status = target.status()
            if status["integrity_check"] != "ok":
                raise RuntimeError("imported database integrity check failed")
            if status["missing_vectors"] or status["orphan_vectors"]:
                raise RuntimeError("imported database vector verification failed")
            imported_ids = {
                row["memory_id"]
                for row in target.connection.execute("SELECT memory_id FROM memories")
            }
            expected_ids = {memory["memory_id"] for memory in document["memories"]}
            if imported_ids != expected_ids:
                raise RuntimeError("imported memory identity verification failed")
            target.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        try:
            os.link(temporary, destination_path)
        except FileExistsError as exc:
            raise FileExistsError(f"import destination already exists: {destination_path}") from exc
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                raise RuntimeError(
                    "atomic import publication requires temporary and destination files "
                    "on the same filesystem"
                ) from exc
            raise
        temporary.unlink()
        destination_path.chmod(0o600)
    return {
        "published": True,
        "destination": str(destination_path),
        "preview": preview.to_dict(),
        "imported_memories": len(document["memories"]),
        "embedded_active_memories": embedded,
        "dropped_external_source_references": document["external_edges"],
        "provenance_loss_accepted": bool(document["external_edges"]),
        "migration_notes": list(notes),
        "verified": True,
        "completed_at": utc_now(),
        "runtime_seconds": time.perf_counter() - started,
    }
