#!/usr/bin/env python3
"""Classify where vector recall ranks the evidence turns it misses, on the tuning pool.

Tuning data only (docs/architecture/held-out-renewal-plan.md): per-question inspection is allowed
for the development 180. The benchmark header is stripped from scratch copies, as in
`evaluate_hybrid_recall.py`, so vector recall sees what a real user stored.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from llm_memory_store import FastEmbedder, MemoryStore
from scripts.analyze_evidence_recall import evidence_turns
from scripts.evaluate_hybrid_recall import copy_store, strip_benchmark_header
from scripts.memorybench_bridge import RANKED_CONTEXT_POLICY, MemoryBenchBridge
from scripts.run_within_session_expansion_stage1 import resolve_container

SESSION = re.compile(r"^(?P<q>.+)-session-(?P<i>\d+)$")
DEPTH = 100


def position(metadata: dict[str, Any]) -> tuple[int, int] | None:
    match = SESSION.match(str(metadata.get("session_id", "")))
    if match is None or not isinstance(metadata.get("message_index"), int):
        return None
    return int(match.group("i")), metadata["message_index"]


def classify(evidence: tuple[int, int], ranked: list[tuple[int, int] | None]) -> str:
    top_sessions = {p[0] for p in ranked[:10] if p}
    rank = ranked.index(evidence) + 1 if evidence in ranked else None
    if rank is not None and rank <= 30:
        return "near miss (rank 11-30)"
    if evidence[0] in top_sessions:
        return "session in top 10, turn not"
    return "rank 31-100" if rank is not None else "beyond rank 100"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, default=Path("demo-artifacts/longmemeval_s_cleaned.json")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evaluation/memorybench/longmemeval-kimi-development-v1.json"),
    )
    parser.add_argument("--stores", type=Path, default=Path("demo-artifacts/memorybench/stores"))
    parser.add_argument(
        "--cache-dir", type=Path, default=Path("demo-artifacts/memorybench/fastembed-cache")
    )
    args = parser.parse_args()
    dataset = {str(x["question_id"]): x for x in json.loads(args.dataset.read_text())}
    ids = [str(q) for q in json.loads(args.manifest.read_text())["question_ids"]]
    embedder = FastEmbedder(cache_dir=str(args.cache_dir), local_files_only=True)
    bridge = MemoryBenchBridge(args.stores, embedder, context_policy=RANKED_CONTEXT_POLICY)

    kinds: collections.Counter[str] = collections.Counter()
    by_category: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    complete: collections.Counter[str] = collections.Counter()
    scored: collections.Counter[str] = collections.Counter()
    with tempfile.TemporaryDirectory() as scratch:
        for qid in ids:
            item = dataset[qid]
            evidence = evidence_turns(item)
            if not evidence:
                continue
            category = item["question_type"]
            scored[category] += 1
            tag = resolve_container(bridge, qid)
            copy = Path(scratch) / "store.sqlite3"
            copy_store(bridge._database_path(tag), copy)
            strip_benchmark_header(copy)
            with MemoryStore(copy, embedder, default_turn_ttl_days=None) as store:
                results = store.recall(
                    item["question"], bridge._scope(tag), limit=DEPTH, relevance_filter=None
                )
            ranked = [position(r.memory.metadata) for r in results]
            complete[category] += evidence <= set(ranked[:10])
            for missed in evidence - set(ranked[:10]):
                kind = classify(missed, ranked)
                kinds[kind] += 1
                by_category[category][kind] += 1
            for leftover in Path(scratch).iterdir():
                leftover.unlink()
    report = {
        "complete_evidence_top10": {c: f"{complete[c]}/{scored[c]}" for c in sorted(scored)},
        "missed_turns_by_kind": dict(kinds),
        "missed_turns_by_category": {c: dict(v) for c, v in sorted(by_category.items())},
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
