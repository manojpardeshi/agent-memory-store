"""Compare current status() with its former Python-set implementation on synthetic data."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope


def _former_status(store: MemoryStore) -> dict[str, Any]:
    connection = store.connection
    by_kind = {
        row["kind"]: int(row["count"])
        for row in connection.execute("SELECT kind, count(*) AS count FROM memories GROUP BY kind")
    }
    by_embedding = {
        row["embedding_status"]: int(row["count"])
        for row in connection.execute(
            "SELECT embedding_status, count(*) AS count FROM memories GROUP BY embedding_status"
        )
    }
    memory_ids = {
        int(row["id"]) for row in connection.execute("SELECT id FROM memories").fetchall()
    }
    vector_ids = {
        int(row["rowid"])
        for row in connection.execute("SELECT rowid FROM memory_vectors").fetchall()
    }
    ready_ids = {
        int(row["id"])
        for row in connection.execute(
            "SELECT id FROM memories WHERE status='active' AND embedding_status='ready'"
        ).fetchall()
    }
    return {
        "database": str(store.path),
        "store_id": store.manifest["store_id"],
        "schema_version": store.manifest["schema_version"],
        "embedding": store.embedding_identity.to_dict(),
        "default_turn_ttl_days": store.default_turn_ttl_days,
        "default_relevance_filter": (
            store.default_relevance_filter.to_dict()
            if store.default_relevance_filter is not None
            else None
        ),
        "memories": len(memory_ids),
        "by_kind": by_kind,
        "by_embedding_status": by_embedding,
        "orphan_vectors": len(vector_ids - memory_ids),
        "missing_vectors": len(ready_ids - vector_ids),
        "keyword_index": store._keyword_index_status(),
        "integrity_check": connection.execute("PRAGMA integrity_check").fetchone()[0],
    }


def _measure(function: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], float, int]:
    tracemalloc.start()
    started = time.perf_counter()
    report = function()
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return report, elapsed, peak


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=int, help="number of synthetic memories")
    args = parser.parse_args()
    if args.records < 1:
        parser.error("records must be positive")
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "status.sqlite3"
        with MemoryStore(path, DeterministicEmbedder(64)) as store:
            scope = Scope.private("benchmark", "local", "status")
            for index in range(args.records):
                store.remember(
                    "fact", f"Synthetic status record {index}", scope, embed=index % 5 == 0
                )
            runs = []
            expected = None
            for name, function in (
                ("former", lambda: _former_status(store)),
                ("current", store.status),
                ("former", lambda: _former_status(store)),
                ("current", store.status),
            ):
                report, elapsed, peak = _measure(function)
                if expected is None:
                    expected = report
                elif report != expected:
                    raise RuntimeError("status results differ")
                runs.append(
                    {
                        "implementation": name,
                        "seconds": round(elapsed, 3),
                        "python_peak_mb": round(peak / 1_048_576, 3),
                    }
                )
            print(
                json.dumps(
                    {
                        "records": args.records,
                        "database_mb": round(path.stat().st_size / 1_048_576, 3),
                        "runs": runs,
                        "integrity_check": expected["integrity_check"],
                        "orphan_vectors": expected["orphan_vectors"],
                        "missing_vectors": expected["missing_vectors"],
                    }
                )
            )


if __name__ == "__main__":
    main()
