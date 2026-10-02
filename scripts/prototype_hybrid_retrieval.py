#!/usr/bin/env python3
"""Evaluation-only prototype: keyword (SQLite FTS5 BM25) + vector retrieval fused by RRF.

Builds a temporary in-memory FTS5 index over each benchmark store's active messages, so the
product schema is untouched until the evidence justifies integration. Scored with the free
evidence-level metric. No model beyond the store's own local embedder; no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from llm_memory_store import FastEmbedder, MemoryStore
from scripts.analyze_evidence_recall import score
from scripts.memorybench_bridge import RANKED_CONTEXT_POLICY, MemoryBenchBridge
from scripts.run_within_session_expansion_stage1 import resolve_container

HEADER_PREFIX = "[longmemeval-source]"
STOPWORDS = frozenset(
    [
        "a",
        "about",
        "after",
        "again",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "before",
        "being",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "during",
        "each",
        "few",
        "for",
        "from",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "tell",
        "remind",
        "know",
        "recall",
        "remember",
        "mentioned",
    ]
)


def body(content: str) -> str:
    return (
        content.split("\n", 1)[1]
        if content.startswith(HEADER_PREFIX) and "\n" in content
        else content
    )


def fts_query(question: str) -> str | None:
    tokens = [
        t for t in re.findall(r"[a-z0-9]+", question.lower()) if t not in STOPWORDS and len(t) > 1
    ]
    unique = list(dict.fromkeys(tokens))
    return " OR ".join(f'"{t}"' for t in unique) if unique else None


def rrf(rankings: list[tuple[list[int], float]], k: int) -> list[int]:
    scores: dict[int, float] = {}
    for ranked, weight in rankings:
        for rank, doc in enumerate(ranked, start=1):
            scores[doc] = scores.get(doc, 0.0) + weight / (k + rank)
    return [doc for doc, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def rank_question(
    store_path: Path, scope: Any, question: str, embedder: Any, depth: int
) -> dict[str, Any]:
    ro = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    rows = ro.execute(
        "SELECT id, memory_id, content, metadata_json FROM memories WHERE status='active'"
    ).fetchall()
    ro.close()
    by_id = {int(r["id"]): r for r in rows}
    by_memory = {r["memory_id"]: int(r["id"]) for r in rows}
    fts = sqlite3.connect(":memory:")
    fts.execute("CREATE VIRTUAL TABLE f USING fts5(body, tokenize='porter unicode61')")
    fts.executemany(
        "INSERT INTO f(rowid, body) VALUES (?, ?)",
        [(int(r["id"]), body(r["content"])) for r in rows],
    )
    query = fts_query(question)
    started = time.perf_counter()
    bm25 = (
        [
            int(r[0])
            for r in fts.execute(
                "SELECT rowid FROM f WHERE f MATCH ? ORDER BY bm25(f) LIMIT ?", (query, depth)
            )
        ]
        if query
        else []
    )
    bm25_ms = (time.perf_counter() - started) * 1000
    fts.close()
    with MemoryStore(store_path, embedder, default_turn_ttl_days=None, read_only=True) as store:
        recalled = store.recall(question, scope, limit=depth, relevance_filter=None)
    vector = [by_memory[r.memory.memory_id] for r in recalled if r.memory.memory_id in by_memory]
    return {"by_id": by_id, "bm25": bm25, "vector": vector, "bm25_ms": bm25_ms}


def as_results(ids: list[int], by_id: dict[int, Any]) -> list[dict[str, Any]]:
    return [{"metadata": json.loads(by_id[i]["metadata_json"])} for i in ids]


VARIANTS = {
    "vector_only": lambda r: r["vector"],
    "bm25_only": lambda r: r["bm25"],
    "rrf_k60": lambda r: rrf([(r["vector"], 1.0), (r["bm25"], 1.0)], 60),
    "rrf_k60_bm25_half": lambda r: rrf([(r["vector"], 1.0), (r["bm25"], 0.5)], 60),
    "rrf_k20": lambda r: rrf([(r["vector"], 1.0), (r["bm25"], 1.0)], 20),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    for name in ("dataset", "manifest", "stores", "cache-dir", "output"):
        ap.add_argument(f"--{name}", type=Path, required=True)
    ap.add_argument("--depth", type=int, default=50)
    a = ap.parse_args()
    dataset = {str(x["question_id"]): x for x in json.loads(a.dataset.read_text())}
    ids = [str(q) for q in json.loads(a.manifest.read_text())["question_ids"]]
    embedder = FastEmbedder(cache_dir=str(a.cache_dir), local_files_only=True)
    bridge = MemoryBenchBridge(a.stores, embedder, context_policy=RANKED_CONTEXT_POLICY)
    per_variant: dict[str, dict[str, list[dict[str, Any]]]] = {v: {} for v in VARIANTS}
    timings = []
    for qid in ids:
        tag = resolve_container(bridge, qid)
        ranked = rank_question(
            bridge._database_path(tag),
            bridge._scope(tag),
            dataset[qid]["question"],
            embedder,
            a.depth,
        )
        timings.append(ranked["bm25_ms"])
        for name, fn in VARIANTS.items():
            per_variant[name][qid] = as_results(fn(ranked)[:10], ranked["by_id"])
    report = {name: score(dataset, results, ids) for name, results in per_variant.items()}
    report["_bm25_query_ms_p95"] = sorted(timings)[int(0.95 * (len(timings) - 1))]
    a.output.write_text(json.dumps(report, indent=2))
    for name in VARIANTS:
        r = report[name]
        cats = {k: v["complete_evidence"] for k, v in r["categories"].items()}
        print(
            f"{name:20s} recall {r['evidence_recall']:.3f} "
            f"complete {r['complete_evidence']:>3d}/{r['scored_questions']} "
            f"| multi {cats.get('multi-session')} temporal {cats.get('temporal-reasoning')}"
        )
    print(f"bm25 query p95 {report['_bm25_query_ms_p95']:.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
