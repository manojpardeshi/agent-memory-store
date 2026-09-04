#!/usr/bin/env python3
"""Benchmark-only JSON-lines bridge from MemoryBench to the released store API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, TextIO

from llm_memory_store import DeterministicEmbedder, FastEmbedder, MemoryStore, Scope
from llm_memory_store.embeddings import Embedder

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 10_000_000
MAX_SESSIONS_PER_REQUEST = 100
MAX_MESSAGES_PER_SESSION = 10_000
BENCHMARK_SUBJECT = "longmemeval-subject"
BENCHMARK_ENVIRONMENT = "longmemeval"
RANKED_CONTEXT_POLICY = "ranked-v1"
SESSION_DIVERSE_CONTEXT_POLICY = "session-diverse-v1"
WITHIN_SESSION_EXPANSION_CONTEXT_POLICY = "within-session-expansion-v1.1"
EXPANSION_PER_SESSION_CAP = 4
EXPANSION_BODY_FLOOR_CHARS = 400
EXPANSION_BUDGET_RATIO = 1.0
EXPANSION_SESSION_FETCH_LIMIT = 1000

if __package__:
    from scripts.within_session_expansion import (
        context_json_bytes,
        expand_within_sessions,
        fit_to_budget,
    )
else:  # pragma: no cover - stdio subprocess path
    from within_session_expansion import (
        context_json_bytes,
        expand_within_sessions,
        fit_to_budget,
    )
SESSION_DIVERSE_POOL_SIZE = 50
SESSION_DIVERSE_PER_SESSION_CAP = 2


class BridgeRequestError(ValueError):
    """Raised when a bridge request violates the frozen adapter contract."""


def _required_string(value: object, field: str, maximum: int = 100_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeRequestError(f"{field} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise BridgeRequestError(f"{field} must be at most {maximum} characters")
    return cleaned


def _integer(value: object, field: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise BridgeRequestError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


class MemoryBenchBridge:
    """Synchronous raw-ingestion adapter with one exact private store per container."""

    def __init__(
        self,
        data_dir: str | Path,
        embedder: Embedder,
        *,
        context_policy: str = RANKED_CONTEXT_POLICY,
    ) -> None:
        if context_policy not in (
            RANKED_CONTEXT_POLICY,
            SESSION_DIVERSE_CONTEXT_POLICY,
            WITHIN_SESSION_EXPANSION_CONTEXT_POLICY,
        ):
            raise ValueError(f"unsupported context policy: {context_policy}")
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.data_dir, 0o700)
        self.embedder = embedder
        self.context_policy = context_policy

    @staticmethod
    def _container_digest(container_tag: str) -> str:
        return hashlib.sha256(container_tag.encode()).hexdigest()

    def _database_path(self, container_tag: str) -> Path:
        digest = self._container_digest(container_tag)
        return self.data_dir / f"container-{digest}.sqlite3"

    @classmethod
    def _scope(cls, container_tag: str) -> Scope:
        digest = cls._container_digest(container_tag)
        return Scope.private(
            BENCHMARK_SUBJECT,
            BENCHMARK_ENVIRONMENT,
            f"container-{digest}",
        )

    @staticmethod
    def _format_message(
        session_id: str,
        message_index: int,
        role: str,
        content: str,
        metadata: dict[str, Any],
    ) -> str:
        source = {
            "benchmark": "longmemeval-s",
            "date": metadata.get("date"),
            "formatted_date": metadata.get("formattedDate"),
            "message_index": message_index,
            "role": role,
            "session_id": session_id,
        }
        header = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"[longmemeval-source]{header}\n{content}"

    @classmethod
    def _operation_id(cls, container_tag: str, session_id: str, message_index: int) -> str:
        identity = json.dumps(
            [container_tag, session_id, message_index],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"memorybench-raw-v1:{hashlib.sha256(identity.encode()).hexdigest()}"

    @staticmethod
    def _sessions(value: object) -> list[dict[str, Any]]:
        if (
            not isinstance(value, list)
            or not value
            or len(value) > MAX_SESSIONS_PER_REQUEST
        ):
            raise BridgeRequestError(
                f"sessions must contain 1 to {MAX_SESSIONS_PER_REQUEST} sessions"
            )
        sessions: list[dict[str, Any]] = []
        for session_index, raw_session in enumerate(value):
            field = f"sessions[{session_index}]"
            if not isinstance(raw_session, dict):
                raise BridgeRequestError(f"{field} must be an object")
            session_id = _required_string(raw_session.get("sessionId"), f"{field}.sessionId", 512)
            raw_messages = raw_session.get("messages")
            if (
                not isinstance(raw_messages, list)
                or not raw_messages
                or len(raw_messages) > MAX_MESSAGES_PER_SESSION
            ):
                raise BridgeRequestError(
                    f"{field}.messages must contain 1 to {MAX_MESSAGES_PER_SESSION} messages"
                )
            messages: list[dict[str, Any]] = []
            for message_index, raw_message in enumerate(raw_messages):
                message_field = f"{field}.messages[{message_index}]"
                if not isinstance(raw_message, dict):
                    raise BridgeRequestError(f"{message_field} must be an object")
                role = _required_string(raw_message.get("role"), f"{message_field}.role", 32)
                if role not in ("user", "assistant"):
                    raise BridgeRequestError(f"{message_field}.role must be user or assistant")
                raw_content = raw_message.get("content")
                if not isinstance(raw_content, str):
                    raise BridgeRequestError(f"{message_field}.content must be a string")
                if len(raw_content) > 100_000:
                    raise BridgeRequestError(
                        f"{message_field}.content must be at most 100000 characters"
                    )
                source_content_empty = not raw_content.strip()
                content = raw_content.strip() or "[empty source message]"
                messages.append(
                    {
                        "role": role,
                        "content": content,
                        "source_content_empty": source_content_empty,
                    }
                )
            raw_metadata = raw_session.get("metadata", {})
            if not isinstance(raw_metadata, dict):
                raise BridgeRequestError(f"{field}.metadata must be an object")
            metadata: dict[str, Any] = {}
            for key in ("date", "formattedDate"):
                item = raw_metadata.get(key)
                if item is not None:
                    metadata[key] = _required_string(item, f"{field}.metadata.{key}", 512)
            sessions.append(
                {
                    "session_id": session_id,
                    "messages": messages,
                    "metadata": metadata,
                }
            )
        return sessions

    def initialize(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "ingestion_track": "raw-deterministic-v1",
            "synchronous_indexing": True,
            "context_policy": self.context_policy,
            "embedder": {
                "provider": self.embedder.provider,
                "model_name": self.embedder.model_name,
                "model_revision": self.embedder.model_revision,
                "runtime_version": self.embedder.runtime_version,
                "dimension": self.embedder.dimension,
            },
        }
        if self.context_policy == SESSION_DIVERSE_CONTEXT_POLICY:
            result["context_policy_config"] = {
                "ranked_candidate_pool": SESSION_DIVERSE_POOL_SIZE,
                "per_session_cap": SESSION_DIVERSE_PER_SESSION_CAP,
                "unit": "single-message",
                "backfill": "original-rank-order",
            }
        elif self.context_policy == WITHIN_SESSION_EXPANSION_CONTEXT_POLICY:
            result["context_policy_config"] = {
                "baseline": "ranked-v1 top-limit, retained as an ordered prefix",
                "per_session_expansion_cap": EXPANSION_PER_SESSION_CAP,
                "new_sessions_introduced": 0,
                "budget_ratio_to_baseline_bytes": EXPANSION_BUDGET_RATIO,
                "body_floor_chars": EXPANSION_BODY_FLOOR_CHARS,
                "reduction_order": "expansions, then baseline, then drop expansions from tail",
                "model_in_query_path": False,
            }
        return result

    def ingest(self, container_tag: str, raw_sessions: object) -> dict[str, Any]:
        sessions = self._sessions(raw_sessions)
        scope = self._scope(container_tag)
        document_ids: list[str] = []
        with MemoryStore(
            self._database_path(container_tag),
            self.embedder,
            default_turn_ttl_days=None,
        ) as store:
            for session in sessions:
                session_id = session["session_id"]
                session_metadata = session["metadata"]
                for message_index, message in enumerate(session["messages"]):
                    content = self._format_message(
                        session_id,
                        message_index,
                        message["role"],
                        message["content"],
                        session_metadata,
                    )
                    record = store.remember(
                        "turn",
                        content,
                        scope,
                        role=message["role"],
                        metadata={
                            "benchmark": "longmemeval-s",
                            "ingestion_track": "raw-deterministic-v1",
                            "message_index": message_index,
                            "source_content_empty": message["source_content_empty"],
                            "session_date": session_metadata.get("date"),
                            "session_formatted_date": session_metadata.get("formattedDate"),
                            "session_id": session_id,
                        },
                        operation_id=self._operation_id(
                            container_tag,
                            session_id,
                            message_index,
                        ),
                    )
                    if record.content != content:
                        raise RuntimeError(
                            "idempotent benchmark operation resolved to different content"
                        )
                    if record.embedding_status != "ready":
                        raise RuntimeError(
                            f"embedding failed for benchmark memory {record.memory_id}: "
                            f"{record.embedding_error or 'unknown error'}"
                        )
                    document_ids.append(record.memory_id)
        return {"documentIds": document_ids}

    @staticmethod
    def _serialize_results(results: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "content": item.memory.content,
                "created_at": item.memory.created_at,
                "kind": item.memory.kind,
                "memory": item.memory.content,
                "memory_id": item.memory.memory_id,
                "metadata": item.memory.metadata,
                "provenance": {
                    "lineage_id": item.memory.lineage_id,
                    "source_memory_ids": list(item.memory.source_memory_ids),
                },
                "recency_score": item.recency_score,
                "score": item.score,
                "semantic_score": item.semantic_score,
                "trust_label": "untrusted_memory",
            }
            for item in results
        ]

    @staticmethod
    def select_session_diverse(
        ranked_results: list[dict[str, Any]],
        *,
        limit: int,
        per_session_cap: int = SESSION_DIVERSE_PER_SESSION_CAP,
    ) -> list[dict[str, Any]]:
        """Select ranked messages with a cap per provenance session and exact backfill."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if per_session_cap < 1:
            raise ValueError("per_session_cap must be positive")
        admitted: list[tuple[int, dict[str, Any]]] = []
        skipped: list[tuple[int, dict[str, Any]]] = []
        session_counts: defaultdict[str, int] = defaultdict(int)
        for rank, result in enumerate(ranked_results):
            metadata = result.get("metadata")
            session_id = metadata.get("session_id") if isinstance(metadata, dict) else None
            if not isinstance(session_id, str) or not session_id:
                raise ValueError(f"ranked result {rank + 1} has no provenance session_id")
            if session_counts[session_id] < per_session_cap:
                admitted.append((rank, result))
                session_counts[session_id] += 1
                if len(admitted) == limit:
                    break
            else:
                skipped.append((rank, result))
        if len(admitted) < limit:
            admitted.extend(skipped[: limit - len(admitted)])
            admitted.sort(key=lambda pair: pair[0])
        return [result for _, result in admitted]

    @staticmethod
    def _serialize_record(record: Any) -> dict[str, Any]:
        """Same shape as a ranked result, with no scores: used for session neighbours."""
        return {
            "content": record.content,
            "created_at": record.created_at,
            "kind": record.kind,
            "memory": record.content,
            "memory_id": record.memory_id,
            "metadata": record.metadata,
            "provenance": {
                "lineage_id": record.lineage_id,
                "source_memory_ids": list(record.source_memory_ids),
            },
            "recency_score": None,
            "score": None,
            "semantic_score": None,
            "trust_label": "untrusted_memory",
        }

    @classmethod
    def select_within_session_expansion(
        cls,
        ranked_results: list[dict[str, Any]],
        session_records: list[Any],
        query: str,
        *,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """within-session-expansion-v1.1: keep the ranked top-limit as a prefix, add up to
        EXPANSION_PER_SESSION_CAP neighbours per baseline session, fit to baseline bytes."""

        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        baseline = ranked_results[:limit]
        budget = int(context_json_bytes(baseline) * EXPANSION_BUDGET_RATIO)
        wanted = set()
        for item in baseline:
            meta = item.get("metadata") or {}
            if isinstance(meta.get("session_id"), str):
                wanted.add(meta["session_id"])
        by_session: dict[str, list[dict[str, Any]]] = {sid: [] for sid in wanted}
        for record in session_records:
            sid = (record.metadata or {}).get("session_id")
            if sid in by_session:
                by_session[sid].append(cls._serialize_record(record))
        expansions = expand_within_sessions(
            baseline, by_session, cap=EXPANSION_PER_SESSION_CAP
        )
        selected = fit_to_budget(
            baseline,
            expansions,
            query,
            budget_bytes=budget,
            floor_body_chars=EXPANSION_BODY_FLOOR_CHARS,
            reduce_baseline=True,
        )
        return selected, {
            "baseline_context_json_bytes": context_json_bytes(baseline),
            "selected_context_json_bytes": context_json_bytes(selected),
            "baseline_count": len(baseline),
            "expansion_candidates": len(expansions),
            "expansions_admitted": len(selected) - len(baseline),
            "baseline_sessions": len(wanted),
        }

    def search_with_diagnostics(
        self, container_tag: str, query: str, limit: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        path = self._database_path(container_tag)
        if not path.is_file():
            return [], {
                "context_policy": self.context_policy,
                "ranked_candidate_count": 0,
                "selection_duration_ms": 0.0,
                "total_duration_ms": 0.0,
            }
        started = time.perf_counter()
        recall_limit = (
            max(limit, SESSION_DIVERSE_POOL_SIZE)
            if self.context_policy == SESSION_DIVERSE_CONTEXT_POLICY
            else limit
        )
        session_records: list[Any] | None = None
        with MemoryStore(
            path,
            self.embedder,
            default_turn_ttl_days=None,
            read_only=True,
        ) as store:
            scope = self._scope(container_tag)
            results = store.recall(
                query,
                scope,
                limit=recall_limit,
                relevance_filter="default",
            )
            if self.context_policy == WITHIN_SESSION_EXPANSION_CONTEXT_POLICY:
                session_records = store.list_memories(
                    scope, limit=EXPANSION_SESSION_FETCH_LIMIT
                )
        serialized = self._serialize_results(results)
        selection_started = time.perf_counter()
        extra_diagnostics: dict[str, Any] = {}
        if self.context_policy == SESSION_DIVERSE_CONTEXT_POLICY:
            selected = self.select_session_diverse(serialized, limit=limit)
        elif self.context_policy == WITHIN_SESSION_EXPANSION_CONTEXT_POLICY:
            selected, extra_diagnostics = self.select_within_session_expansion(
                serialized, session_records or [], query, limit=limit
            )
        else:
            selected = serialized[:limit]
        selection_duration_ms = (time.perf_counter() - selection_started) * 1000
        diagnostics = {
            "context_policy": self.context_policy,
            "ranked_candidate_count": len(serialized),
            "ranked_pool_top_10_memory_ids": [
                item["memory_id"] for item in serialized[:10]
            ],
            "selection_duration_ms": selection_duration_ms,
            "total_duration_ms": (time.perf_counter() - started) * 1000,
            **extra_diagnostics,
        }
        return selected, diagnostics

    def search(self, container_tag: str, query: str, limit: int) -> list[dict[str, Any]]:
        results, _ = self.search_with_diagnostics(container_tag, query, limit)
        return results

    def clear(self, container_tag: str) -> dict[str, int]:
        path = self._database_path(container_tag)
        deleted = 0
        for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
            if candidate.is_file():
                candidate.unlink()
                deleted += 1
        return {"deleted_files": deleted}

    def handle(self, request: object) -> Any:
        if not isinstance(request, dict):
            raise BridgeRequestError("request must be an object")
        operation = _required_string(request.get("operation"), "operation", 64)
        if operation == "initialize":
            return self.initialize()

        container_tag = _required_string(
            request.get("container_tag"),
            "container_tag",
            512,
        )
        if operation == "ingest":
            return self.ingest(container_tag, request.get("sessions"))
        if operation == "await_indexing":
            raw_ids = request.get("document_ids", [])
            if not isinstance(raw_ids, list) or not all(isinstance(item, str) for item in raw_ids):
                raise BridgeRequestError("document_ids must be an array of strings")
            return {
                "completedIds": raw_ids,
                "failedIds": [],
                "total": len(raw_ids),
            }
        if operation == "search":
            query = _required_string(request.get("query"), "query")
            limit = _integer(request.get("limit", 10), "limit", 1, 100)
            return self.search(container_tag, query, limit)
        if operation == "clear":
            return self.clear(container_tag)
        raise BridgeRequestError(f"unsupported operation: {operation}")


def _embedder(args: argparse.Namespace) -> Embedder:
    if args.embedder == "deterministic":
        return DeterministicEmbedder(args.dimension)
    return FastEmbedder(
        model_name=args.model,
        cache_dir=args.cache_dir,
        local_files_only=args.offline,
    )


def _write_response(
    request_id: object,
    *,
    output: TextIO,
    result: Any = None,
    error: str | None = None,
) -> None:
    value: dict[str, Any] = {"id": request_id, "ok": error is None}
    if error is None:
        value["result"] = result
    else:
        value["error"] = error
    # ASCII escaping keeps U+2028/U+2029 inside one JSON-lines record. Node's readline treats
    # those valid JSON string characters as line boundaries when they are emitted literally.
    output.write(json.dumps(value, ensure_ascii=True, separators=(",", ":")) + "\n")
    output.flush()


def _isolate_protocol_stdout() -> TextIO:
    """Keep protocol output on the original stdout and redirect later fd-1 writes to stderr."""
    protocol_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    return os.fdopen(
        protocol_fd,
        "w",
        encoding=sys.stdout.encoding or "utf-8",
        errors="strict",
        buffering=1,
    )


def serve(bridge: MemoryBenchBridge, output: TextIO) -> int:
    for raw_line in sys.stdin.buffer:
        request_id: object = None
        try:
            if len(raw_line) > MAX_REQUEST_BYTES:
                raise BridgeRequestError(f"request exceeds {MAX_REQUEST_BYTES} bytes")
            request = json.loads(raw_line)
            if not isinstance(request, dict):
                raise BridgeRequestError("request must be an object")
            request_id = request.get("id")
            result = bridge.handle(request)
            _write_response(request_id, result=result, output=output)
        except (BridgeRequestError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
            print(f"memorybench bridge request failed: {type(exc).__name__}", file=sys.stderr)
            _write_response(
                request_id,
                error=f"{type(exc).__name__}: {exc}",
                output=output,
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the benchmark-only MemoryBench JSON-lines bridge."
    )
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--embedder", choices=("fastembed", "deterministic"), default="fastembed")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--cache-dir")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--dimension", type=int, default=64)
    parser.add_argument(
        "--context-policy",
        choices=(RANKED_CONTEXT_POLICY, SESSION_DIVERSE_CONTEXT_POLICY),
        default=RANKED_CONTEXT_POLICY,
    )
    args = parser.parse_args()
    protocol_output = _isolate_protocol_stdout()
    try:
        return serve(
            MemoryBenchBridge(
                args.data_dir,
                _embedder(args),
                context_policy=args.context_policy,
            ),
            protocol_output,
        )
    finally:
        protocol_output.close()


if __name__ == "__main__":
    raise SystemExit(main())
