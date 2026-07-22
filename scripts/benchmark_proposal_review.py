#!/usr/bin/env python3
"""Measure deterministic proposal review at the accepted personal-scale ceiling."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from llm_memory_store import (
    DeterministicEmbedder,
    DeterministicRuleExtractor,
    MemoryStore,
    Scope,
    create_proposal_bundle,
    review_proposals,
)
from llm_memory_store.database import immediate_transaction, utc_now


def run_benchmark(row_count: int, limit_seconds: float) -> dict[str, object]:
    if row_count < 1:
        raise ValueError("row_count must be positive")
    if limit_seconds <= 0:
        raise ValueError("limit_seconds must be positive")
    with tempfile.TemporaryDirectory(prefix="llm-memory-review-") as directory:
        path = Path(directory) / "review.sqlite3"
        scope = Scope.private("synthetic-owner", "review-benchmark", "benchmark-app")
        with MemoryStore(path, DeterministicEmbedder(64)) as store:
            source = store.remember_turn(
                "Fact: The proposal review target is ultraviolet.", "user", scope
            )
            bundle = create_proposal_bundle(
                store, [source.memory_id], scope, DeterministicRuleExtractor()
            )
            scope_id = store.connection.execute(
                "SELECT id FROM scopes WHERE kind=? AND subject=? AND environment=? AND owner=?",
                (scope.kind, scope.subject, scope.environment, scope.owner),
            ).fetchone()["id"]
            created_at = utc_now()
            rows = []
            for index in range(row_count):
                content = f"Synthetic benchmark memory {index:06d}"
                memory_id = f"benchmark-memory-{index:06d}"
                rows.append(
                    (
                        memory_id,
                        f"benchmark-lineage-{index:06d}",
                        scope_id,
                        content,
                        hashlib.sha256(content.encode()).hexdigest(),
                        created_at,
                    )
                )
            with immediate_transaction(store.connection):
                store.connection.executemany(
                    """
                    INSERT INTO memories(
                        memory_id, lineage_id, version, scope_id, kind, role, content,
                        content_hash, status, generation, embedding_status, metadata_json,
                        operation_id, created_at, expires_at
                    ) VALUES(?, ?, 1, ?, 'fact', NULL, ?, ?, 'active', 0, 'pending', '{}',
                             NULL, ?, NULL)
                    """,
                    rows,
                )
            before_changes = store.connection.total_changes
            tracemalloc.start()
            started = time.perf_counter()
            report = review_proposals(store, bundle)
            elapsed = time.perf_counter() - started
            _, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            non_mutating = store.connection.total_changes == before_changes
            passed = (
                elapsed <= limit_seconds and non_mutating and report.counts["proposal_count"] == 1
            )
            return {
                "schema_version": 1,
                "benchmark": "proposal-review-personal-scale",
                "active_target_scope_rows": row_count + 1,
                "proposal_count": report.counts["proposal_count"],
                "elapsed_seconds": round(elapsed, 6),
                "peak_traced_bytes": peak_bytes,
                "limit_seconds": limit_seconds,
                "database_total_changes_unchanged": non_mutating,
                "passed": passed,
            }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--limit-seconds", type=float, default=2.0)
    args = parser.parse_args()
    report = run_benchmark(args.rows, args.limit_seconds)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
