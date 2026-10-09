#!/usr/bin/env python3
"""Evaluation-only prototype: hybrid fusion variants that trust keyword evidence selectively.

Plain reciprocal rank fusion gives a memory that shares one incidental word with the query the
same credit as the strongest vector match. These variants weight or gate the keyword ranking by
how specific the match is, measured with BM25-style inverse document frequency over the memories
the query can actually reach.

Tuning data only: the stratified sixty LongMemEval-S questions (benchmark header stripped, as in
`evaluate_hybrid_recall.py`) and the retrieval_v1 / retrieval_v2 synthetic suites. retrieval_v2
was diagnosed before this design and is therefore not independent evidence for any variant here.
Free and local; the product is unchanged.
"""

# ruff: noqa: E501 -- authored word lists and report rows stay on one line.

from __future__ import annotations

import argparse
import json
import math
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlite_vec

from llm_memory_store import FastEmbedder, MemoryStore, RelevanceFilter
from llm_memory_store.database import KEYWORD_INDEX_TABLE
from llm_memory_store.evaluation import (
    _is_accessible,
    load_evaluation_dataset,
    score_evaluation_rankings,
)
from llm_memory_store.store import HYBRID_RRF_K, keyword_query
from scripts.analyze_evidence_recall import score as evidence_score
from scripts.evaluate_hybrid_recall import copy_store, strip_benchmark_header
from scripts.memorybench_bridge import RANKED_CONTEXT_POLICY, MemoryBenchBridge
from scripts.run_within_session_expansion_stage1 import resolve_container


@dataclass
class QueryFeatures:
    vector: list[int]  # internal ids, vector order
    keyword: list[int]  # internal ids, full-query BM25 order
    semantic: dict[int, float]
    term_docs: dict[str, set[int]]  # query term -> reachable memories containing it
    reachable: int
    anchor: float | None

    def idf(self, term: str) -> float:
        df = len(self.term_docs[term])
        return math.log((self.reachable - df + 0.5) / (df + 0.5) + 1)

    def coverage(self, internal_id: int) -> float:
        """IDF-weighted share of the query's corpus-present terms that this memory contains."""
        present = [t for t, docs in self.term_docs.items() if docs]
        total = sum(self.idf(t) for t in present)
        if not total:
            return 0.0
        return sum(self.idf(t) for t in present if internal_id in self.term_docs[t]) / total


def extract(
    store: MemoryStore,
    query: str,
    scope: Any,
    shared_pools: tuple[str, ...],
    limit: int,
) -> QueryFeatures:
    depth = min(max(50, limit * 5), 500)
    scope_ids = [store._find_scope_id(scope)]
    scope_ids += [
        store._find_scope_id(type(scope).shared(scope.subject, scope.environment, pool))
        for pool in shared_pools
    ]
    scope_ids = [i for i in scope_ids if i]
    by_memory = {
        row["memory_id"]: int(row["id"])
        for row in store.connection.execute("SELECT id, memory_id FROM memories")
    }
    recalled = store.recall(
        query, scope, shared_pools=shared_pools, limit=min(depth, 100), relevance_filter=None
    )
    vector = [by_memory[r.memory.memory_id] for r in recalled]
    keyword = store._keyword_ranking(query, scope_ids, depth)
    marks = ",".join("?" * len(scope_ids))
    reachable = store.connection.execute(
        f"""SELECT count(*) FROM memories WHERE scope_id IN ({marks})
            AND status='active' AND embedding_status='ready'""",
        scope_ids,
    ).fetchone()[0]
    match = keyword_query(query)
    terms = [t.strip('"') for t in match.split(" OR ")] if match else []
    term_docs = {
        term: {
            int(row[0])
            for row in store.connection.execute(
                f"""SELECT m.id FROM {KEYWORD_INDEX_TABLE} k JOIN memories m ON m.id = k.rowid
                    WHERE {KEYWORD_INDEX_TABLE} MATCH ? AND m.scope_id IN ({marks})
                      AND m.status='active' AND m.embedding_status='ready'""",
                (f'"{term}"', *scope_ids),
            )
        }
        for term in terms
    }
    query_vector = sqlite_vec.serialize_float32(store.embedder.embed_query(query))
    ids = sorted(set(vector) | set(keyword))
    distances = store._vector_distances(query_vector, ids)
    semantic = {i: max(0.0, min(1.0, 1.0 - d)) for i, d in distances.items()}
    anchor = semantic[vector[0]] if vector else None
    return QueryFeatures(vector, keyword, semantic, term_docs, reachable, anchor)


def fuse(contributions: list[tuple[list[int], Callable[[int], float]]]) -> list[int]:
    scores: dict[int, float] = {}
    for ranking, weight in contributions:
        for rank, doc in enumerate(ranking, start=1):
            w = weight(doc)
            if w > 0:
                scores[doc] = scores.get(doc, 0.0) + w / (HYBRID_RRF_K + rank)
    return [d for d, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def idf_gated_keyword(f: QueryFeatures, max_df_fraction: float, floor: int = 0) -> list[int]:
    """Keyword ranking restricted to memories matching at least one rare query term.

    A term is rare when at most max(floor, fraction x reachable) memories contain it; the floor
    keeps the gate meaningful in small stores, where the fraction alone is below one memory.
    """
    limit = max(floor, max_df_fraction * f.reachable)
    rare = {t for t, docs in f.term_docs.items() if 0 < len(docs) <= limit}
    return [d for d in f.keyword if any(d in f.term_docs[t] for t in rare)]


ONE = lambda _doc: 1.0  # noqa: E731

VARIANTS: dict[str, Callable[[QueryFeatures], list[int]]] = {
    "vector": lambda f: f.vector,
    "rrf": lambda f: fuse([(f.vector, ONE), (f.keyword, ONE)]),
    "idf_gate_0.02": lambda f: fuse([(f.vector, ONE), (idf_gated_keyword(f, 0.02), ONE)]),
    "idf_gate_0.05": lambda f: fuse([(f.vector, ONE), (idf_gated_keyword(f, 0.05), ONE)]),
    "idf_gate_0.10": lambda f: fuse([(f.vector, ONE), (idf_gated_keyword(f, 0.10), ONE)]),
    "idf_gate_0.02_floor1": lambda f: fuse(
        [(f.vector, ONE), (idf_gated_keyword(f, 0.02, floor=1), ONE)]
    ),
    "idf_gate_0.02_floor2": lambda f: fuse(
        [(f.vector, ONE), (idf_gated_keyword(f, 0.02, floor=2), ONE)]
    ),
    "idf_gate_0.01_floor1": lambda f: fuse(
        [(f.vector, ONE), (idf_gated_keyword(f, 0.01, floor=1), ONE)]
    ),
    "coverage_weight": lambda f: fuse([(f.vector, ONE), (f.keyword, f.coverage)]),
    "coverage_gate_0.34": lambda f: fuse(
        [(f.vector, ONE), ([d for d in f.keyword if f.coverage(d) >= 0.34], ONE)]
    ),
    "coverage_gate_0.50": lambda f: fuse(
        [(f.vector, ONE), ([d for d in f.keyword if f.coverage(d) >= 0.50], ONE)]
    ),
}


def apply_filter(ranking: list[int], f: QueryFeatures, gap: float | None) -> list[int]:
    if gap is None or f.anchor is None:
        return ranking
    return [d for d in ranking if f.semantic.get(d, 0.0) >= f.anchor - gap]


def run_synthetic(path: Path, embedder: Any) -> dict[str, Any]:
    dataset, _ = load_evaluation_dataset(path)
    report: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as directory:
        store = MemoryStore(Path(directory) / "s.sqlite3", embedder)
        fixture_of: dict[int, str] = {}
        for memory in dataset.memories:
            record = store.remember(memory.kind, memory.content, memory.scope, role=memory.role)
            internal = store.connection.execute(
                "SELECT id FROM memories WHERE memory_id=?", (record.memory_id,)
            ).fetchone()[0]
            fixture_of[int(internal)] = memory.fixture_id
        gap = store.default_relevance_filter.maximum_semantic_score_gap
        features = {}
        for query in dataset.queries:
            limit = sum(_is_accessible(m, query) for m in dataset.memories)
            features[query.query_id] = (
                extract(store, query.query, query.private_scope, query.shared_pools, limit),
                limit,
            )
        store.close()
    for name, variant in VARIANTS.items():
        rankings = {
            qid: [fixture_of[d] for d in apply_filter(variant(f), f, gap)][:limit]
            for qid, (f, limit) in features.items()
        }
        result = score_evaluation_rankings(dataset, rankings, runtime_seconds=0.0)
        report[name] = {
            "passed": result["passed"],
            **{
                k: round(result["metrics"][k], 4)
                for k in ("recall_at_k", "mrr", "distractor_leak_rate")
            },
            "scope_violations": result["metrics"]["scope_violation_count"],
        }
        styles_path = path.with_name(f"{path.stem}_styles.json")
        if styles_path.exists():
            styles = json.loads(styles_path.read_text())["query_styles"]
            by_style: dict[str, list[float]] = {}
            for row in result["query_results"]:
                by_style.setdefault(styles[row["query_id"]], []).append(row["reciprocal_rank"])
            report[name]["mrr_by_style"] = {
                style: round(sum(v) / len(v), 4) for style, v in sorted(by_style.items())
            }
    return report


def run_longmemeval(args: argparse.Namespace, embedder: Any) -> dict[str, Any]:
    dataset = {str(x["question_id"]): x for x in json.loads(args.dataset.read_text())}
    ids = [str(q) for q in json.loads(args.manifest.read_text())["question_ids"]]
    bridge = MemoryBenchBridge(args.stores, embedder, context_policy=RANKED_CONTEXT_POLICY)
    gap = RelevanceFilter.relative(0.20).maximum_semantic_score_gap
    per_variant: dict[str, dict[str, list[dict[str, Any]]]] = {v: {} for v in VARIANTS}
    with tempfile.TemporaryDirectory() as scratch:
        for qid in ids:
            tag = resolve_container(bridge, qid)
            copy = Path(scratch) / "store.sqlite3"
            copy_store(bridge._database_path(tag), copy)
            strip_benchmark_header(copy)
            with MemoryStore(copy, embedder, default_turn_ttl_days=None) as store:
                f = extract(store, dataset[qid]["question"], bridge._scope(tag), (), 10)
                meta = {
                    int(r["id"]): json.loads(r["metadata_json"])
                    for r in store.connection.execute("SELECT id, metadata_json FROM memories")
                }
            for name, variant in VARIANTS.items():
                ranked = apply_filter(variant(f), f, gap)[:10]
                per_variant[name][qid] = [{"metadata": meta[d]} for d in ranked]
            for leftover in Path(scratch).iterdir():
                leftover.unlink()
    report = {}
    for name in VARIANTS:
        s = evidence_score(dataset, per_variant[name], ids)
        report[name] = {
            "complete_evidence": s["complete_evidence"],
            "scored": s["scored_questions"],
            "evidence_recall": s["evidence_recall"],
            "categories": {k: v["complete_evidence"] for k, v in s["categories"].items()},
        }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("dataset", "manifest", "stores", "cache-dir", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--synthetic", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=list(VARIANTS),
        help="evaluate only these variants (held-out runs use only the frozen arms)",
    )
    args = parser.parse_args()
    if args.variants:
        for name in [v for v in VARIANTS if v not in args.variants]:
            del VARIANTS[name]
    embedder = FastEmbedder(cache_dir=str(args.cache_dir), local_files_only=True)
    report = {
        "synthetic": {p.stem: run_synthetic(p, embedder) for p in args.synthetic},
        "longmemeval_tuning": run_longmemeval(args, embedder),
    }
    args.output.write_text(json.dumps(report, indent=2))
    lme = report["longmemeval_tuning"]
    print(
        f"{'variant':20s} {'LME complete':>12s} {'recall':>7s} | "
        + " | ".join(f"{s}: pass R@k MRR leak" for s in report["synthetic"])
    )
    for name in VARIANTS:
        row = f"{name:20s} {lme[name]['complete_evidence']:>5d}/{lme[name]['scored']:<6d} {lme[name]['evidence_recall']:>7.3f} | "
        row += " | ".join(
            f"{s}: {'Y' if r[name]['passed'] else 'n'} {r[name]['recall_at_k']:.3f} {r[name]['mrr']:.3f} {r[name]['distractor_leak_rate']:.3f}"
            for s, r in report["synthetic"].items()
        )
        print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
