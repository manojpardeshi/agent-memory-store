#!/usr/bin/env python3
"""Measure the product's hybrid recall against vector recall on LongMemEval-S benchmark stores.

Unlike `prototype_hybrid_retrieval.py`, this exercises the shipped code path: each benchmark
store is copied with SQLite's backup API, opened writable so the product builds its keyword
index, and queried through `MemoryStore.recall` in both modes.

The benchmark adapter prefixes every stored message with a `[longmemeval-source]` JSON header
(dates, month names, role, session id). Real users store only their message, and the header's
shared words are keyword noise, so `--strip-benchmark-header` rewrites each copy's content to
the message body before the index is built. Stored embeddings are untouched, so the vector
arms are identical either way. Scoring uses the free
evidence-level metric; nothing here calls a paid service. The source stores are never modified.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from llm_memory_store import FastEmbedder, MemoryStore
from llm_memory_store.database import load_vector_extension
from scripts.analyze_evidence_recall import score
from scripts.memorybench_bridge import RANKED_CONTEXT_POLICY, MemoryBenchBridge
from scripts.run_within_session_expansion_stage1 import resolve_container

ARMS = {
    "vector_unfiltered": {"retrieval": "vector", "relevance_filter": None},
    "hybrid_unfiltered": {"retrieval": "hybrid", "relevance_filter": None},
    "vector_default_filter": {"retrieval": "vector", "relevance_filter": "default"},
    "hybrid_default_filter": {"retrieval": "hybrid", "relevance_filter": "default"},
}
TIMING_REPEATS = 3
HEADER_PREFIX = "[longmemeval-source]"


def database_bytes(connection: sqlite3.Connection) -> int:
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    return int(page_size) * int(page_count)


def copy_store(source: Path, destination: Path) -> int:
    reader = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    writer = sqlite3.connect(destination)
    try:
        load_vector_extension(reader)
        reader.backup(writer)
        return database_bytes(writer)
    finally:
        writer.close()
        reader.close()


def strip_benchmark_header(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            UPDATE memories SET content = substr(content, instr(content, char(10)) + 1)
            WHERE content LIKE ? AND instr(content, char(10)) > 0
            """,
            (HEADER_PREFIX + "%",),
        )
        connection.commit()
    finally:
        connection.close()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[int(fraction * (len(ordered) - 1))]


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("dataset", "manifest", "stores", "cache-dir", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--strip-benchmark-header", action="store_true")
    args = parser.parse_args()

    dataset = {str(x["question_id"]): x for x in json.loads(args.dataset.read_text())}
    ids = [str(q) for q in json.loads(args.manifest.read_text())["question_ids"]]
    embedder = FastEmbedder(cache_dir=str(args.cache_dir), local_files_only=True)
    bridge = MemoryBenchBridge(args.stores, embedder, context_policy=RANKED_CONTEXT_POLICY)

    results: dict[str, dict[str, list[dict[str, Any]]]] = {arm: {} for arm in ARMS}
    latency_ms: dict[str, list[float]] = {arm: [] for arm in ARMS}
    build_ms: list[float] = []
    growth: list[float] = []
    with tempfile.TemporaryDirectory(prefix="hybrid-eval-") as scratch:
        for question_id in ids:
            tag = resolve_container(bridge, question_id)
            copy = Path(scratch) / "store.sqlite3"
            before = copy_store(bridge._database_path(tag), copy)
            if args.strip_benchmark_header:
                strip_benchmark_header(copy)
            started = time.perf_counter()
            store = MemoryStore(copy, embedder, default_turn_ttl_days=None)
            build_ms.append((time.perf_counter() - started) * 1000)
            try:
                growth.append(database_bytes(store.connection) / before - 1)
                question = dataset[question_id]["question"]
                scope = bridge._scope(tag)
                for arm, options in ARMS.items():
                    recalled = store.recall(question, scope, limit=10, **options)
                    timings = []
                    for _ in range(TIMING_REPEATS):
                        tick = time.perf_counter()
                        store.recall(question, scope, limit=10, **options)
                        timings.append((time.perf_counter() - tick) * 1000)
                    latency_ms[arm].append(min(timings))
                    results[arm][question_id] = [
                        {"metadata": dict(result.memory.metadata)} for result in recalled
                    ]
            finally:
                store.close()
                for leftover in Path(scratch).iterdir():
                    leftover.unlink()

    report: dict[str, Any] = {
        "schema_version": 1,
        "manifest": str(args.manifest),
        "benchmark_header_stripped": args.strip_benchmark_header,
        "question_count": len(ids),
        "metric_scope": "evidence-level retrieval recall; not answer quality",
        "arms": {arm: score(dataset, results[arm], ids) for arm in ARMS},
        "latency_ms_including_query_embedding": {
            arm: {
                "p50": round(statistics.median(values), 2),
                "p95": round(percentile(values, 0.95), 2),
            }
            for arm, values in latency_ms.items()
        },
        "keyword_index": {
            "first_open_build_ms_p50": round(statistics.median(build_ms), 1),
            "first_open_build_ms_max": round(max(build_ms), 1),
            "database_growth_fraction_p50": round(statistics.median(growth), 4),
            "database_growth_fraction_max": round(max(growth), 4),
        },
    }
    if args.aggregate_only:
        for arm in report["arms"].values():
            arm.pop("questions", None)
    args.output.write_text(json.dumps(report, indent=2))
    for arm, result in report["arms"].items():
        latency = report["latency_ms_including_query_embedding"][arm]
        print(
            f"{arm:24s} recall {result['evidence_recall']:.3f} "
            f"complete {result['complete_evidence']:>3d}/{result['scored_questions']} "
            f"| p50 {latency['p50']} ms p95 {latency['p95']} ms"
        )
    print(json.dumps(report["keyword_index"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
