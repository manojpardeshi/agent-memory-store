#!/usr/bin/env python3
"""Evaluation-only prototype: re-rank vector recall's top-K with a local cross-encoder.

Tuning data only (docs/architecture/held-out-renewal-plan.md): the LongMemEval-S development 180
(benchmark header stripped from scratch copies, as in `evaluate_hybrid_recall.py`) and the
retrieval_v1 / v2 / v3 synthetic suites. Held-out data is never read. Free and local; the only
network use is FastEmbed's one-time cross-encoder download into the cache directory. The product
is unchanged.

Each question's 50 vector candidates are scored once per model; depth variants K reorder the first
K candidates by cross-encoder score (ties keep vector order) and keep ten.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from fastembed.rerank.cross_encoder import TextCrossEncoder

from llm_memory_store import FastEmbedder, MemoryStore
from llm_memory_store.evaluation import (
    _is_accessible,
    load_evaluation_dataset,
    score_evaluation_rankings,
)
from scripts.analyze_evidence_recall import evidence_turns
from scripts.analyze_evidence_recall import score as evidence_score
from scripts.evaluate_hybrid_recall import copy_store, strip_benchmark_header
from scripts.memorybench_bridge import RANKED_CONTEXT_POLICY, MemoryBenchBridge
from scripts.run_within_session_expansion_stage1 import resolve_container

MODELS = (
    "Xenova/ms-marco-MiniLM-L-6-v2",
    "Xenova/ms-marco-MiniLM-L-12-v2",
    "jinaai/jina-reranker-v1-tiny-en",
    "jinaai/jina-reranker-v1-turbo-en",
    "BAAI/bge-reranker-base",
)
DEPTHS = (20, 30, 50)
POOL = max(DEPTHS)


def reorder(scores: list[float], depth: int) -> list[int]:
    """Indices of the first `depth` vector candidates, best cross-encoder score first."""
    return sorted(range(min(depth, len(scores))), key=lambda i: (-scores[i], i))


def arm_name(model: str, chars: int) -> str:
    """Model plus its document truncation; `chars` 0 means the full stored content."""
    return model if not chars else f"{model}/c{chars}"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def model_size_mb(cache_dir: Path, model: str) -> float:
    root = cache_dir / ("models--" + model.replace("/", "--"))
    total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink())
    return round(total / 1e6, 1)


def collect_longmemeval(args: argparse.Namespace, embedder: Any) -> tuple[dict, dict, list[str]]:
    dataset = {str(x["question_id"]): x for x in json.loads(args.dataset.read_text())}
    ids = [str(q) for q in json.loads(args.manifest.read_text())["question_ids"]]
    bridge = MemoryBenchBridge(args.stores, embedder, context_policy=RANKED_CONTEXT_POLICY)
    candidates: dict[str, list[dict[str, Any]]] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for qid in ids:
            item = dataset[qid]
            if not evidence_turns(item):
                continue
            tag = resolve_container(bridge, qid)
            copy = Path(scratch) / "store.sqlite3"
            copy_store(bridge._database_path(tag), copy)
            strip_benchmark_header(copy)
            with MemoryStore(copy, embedder, default_turn_ttl_days=None) as store:
                results = store.recall(
                    item["question"], bridge._scope(tag), limit=POOL, relevance_filter=None
                )
            candidates[qid] = [
                {"content": r.memory.content, "metadata": r.memory.metadata} for r in results
            ]
            for leftover in Path(scratch).iterdir():
                leftover.unlink()
    scored_ids = [qid for qid in ids if qid in candidates]
    return dataset, candidates, scored_ids


def collect_synthetic(path: Path, embedder: Any) -> dict[str, Any]:
    """Vector pools (fixture id, content, semantic score) per query and depth, plus the gap."""
    dataset, _ = load_evaluation_dataset(path)
    pools: dict[str, dict[int | str, Any]] = {}
    with tempfile.TemporaryDirectory() as directory:
        store = MemoryStore(Path(directory) / "s.sqlite3", embedder)
        fixture_of: dict[str, str] = {}
        content_of: dict[str, str] = {}
        for memory in dataset.memories:
            record = store.remember(memory.kind, memory.content, memory.scope, role=memory.role)
            fixture_of[record.memory_id] = memory.fixture_id
            content_of[record.memory_id] = memory.content
        gap = store.default_relevance_filter.maximum_semantic_score_gap
        for query in dataset.queries:
            accessible = sum(_is_accessible(m, query) for m in dataset.memories)
            entry: dict[int | str, Any] = {"accessible": accessible}
            for depth in (0, *DEPTHS):  # 0 = baseline limit (accessible count)
                results = store.recall(
                    query.query,
                    query.private_scope,
                    shared_pools=query.shared_pools,
                    limit=accessible if depth == 0 else min(depth, accessible),
                    relevance_filter=None,
                )
                entry[depth] = [
                    {
                        "fixture": fixture_of[r.memory.memory_id],
                        "content": content_of[r.memory.memory_id],
                        "semantic": r.semantic_score,
                    }
                    for r in results
                ]
            pools[query.query_id] = entry
        store.close()
    return {"dataset": dataset, "pools": pools, "gap": gap, "path": path}


def filtered(pool: list[dict[str, Any]], order: list[int], gap: float, limit: int) -> list[str]:
    """Certified default filter, anchored on the top vector candidate (pool order = vector)."""
    if not pool:
        return []
    anchor = pool[0]["semantic"]
    return [pool[i]["fixture"] for i in order if pool[i]["semantic"] >= anchor - gap][:limit]


def score_synthetic(
    suite: dict[str, Any], variants: list[tuple[str, int, int]], encoders: dict[str, Any]
) -> dict[str, Any]:
    dataset, pools, gap, path = suite["dataset"], suite["pools"], suite["gap"], suite["path"]
    styles_path = path.with_name(f"{path.stem}_styles.json")
    styles = json.loads(styles_path.read_text())["query_styles"] if styles_path.exists() else None
    report: dict[str, Any] = {}
    for model, chars, depth in [("baseline", 0, 0), *variants]:
        name = "baseline" if model == "baseline" else f"{arm_name(model, chars)}@{depth}"
        rankings = {}
        for qid, entry in pools.items():
            pool = entry[depth]
            if model == "baseline":
                order = list(range(len(pool)))
            else:
                query = dataset_query(dataset, qid)
                docs = [truncate(p["content"], chars) for p in pool]
                scores = list(encoders[model].rerank(query, docs))
                order = reorder(scores, len(pool))
            rankings[qid] = filtered(pool, order, gap, entry["accessible"])
        result = score_evaluation_rankings(dataset, rankings, runtime_seconds=0.0)
        report[name] = {
            "passed": result["passed"],
            **{
                k: round(result["metrics"][k], 4)
                for k in ("recall_at_k", "mrr", "distractor_leak_rate")
            },
            "scope_violations": result["metrics"]["scope_violation_count"],
        }
        if styles is not None:
            by_style: dict[str, list[float]] = {}
            for row in result["query_results"]:
                by_style.setdefault(styles[row["query_id"]], []).append(row["reciprocal_rank"])
            report[name]["mrr_by_style"] = {
                s: round(sum(v) / len(v), 4) for s, v in sorted(by_style.items())
            }
    return report


def truncate(text: str, chars: int) -> str:
    """Reranker input only; the stored memory is unchanged. 0 keeps the full content."""
    return text[:chars] if chars else text


def dataset_query(dataset: Any, query_id: str) -> str:
    return next(q.query for q in dataset.queries if q.query_id == query_id)


def summarize(dataset: dict, results: dict, scored_ids: list[str]) -> dict[str, Any]:
    s = evidence_score(dataset, results, scored_ids)
    return {
        "complete_evidence": s["complete_evidence"],
        "scored": s["scored_questions"],
        "evidence_recall": s["evidence_recall"],
        "categories": {
            k: {
                "complete": v["complete_evidence"],
                "n": v["n"],
                "evidence_recall": v["evidence_recall"],
            }
            for k, v in s["categories"].items()
        },
    }


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
    parser.add_argument(
        "--output", type=Path, default=Path("demo-artifacts/rerank-tuning-dev180.json")
    )
    parser.add_argument(
        "--synthetic",
        type=Path,
        nargs="+",
        default=[Path(f"evaluation/retrieval_v{i}.json") for i in (1, 2, 3)],
    )
    parser.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    parser.add_argument(
        "--truncate-chars",
        type=int,
        nargs="+",
        default=[0],
        help="rerank on the first C characters of each candidate; 0 means no truncation",
    )
    parser.add_argument(
        "--synthetic-top",
        type=int,
        default=3,
        help="synthetic suites for the baseline and this many best variants; 0 means all",
    )
    parser.add_argument("--limit-questions", type=int, default=0, help="smoke test only")
    args = parser.parse_args()

    embedder = FastEmbedder(cache_dir=str(args.cache_dir), local_files_only=True)
    dataset, candidates, scored_ids = collect_longmemeval(args, embedder)
    if args.limit_questions:
        scored_ids = scored_ids[: args.limit_questions]
    print(f"collected vector candidates for {len(scored_ids)} questions", flush=True)
    suites = {p.stem: collect_synthetic(p, embedder) for p in args.synthetic}

    baseline_results = {
        q: [{"metadata": c["metadata"]} for c in candidates[q][:10]] for q in scored_ids
    }
    lme: dict[str, Any] = {"baseline": summarize(dataset, baseline_results, scored_ids)}
    latency: dict[str, Any] = {}
    sizes: dict[str, float] = {}
    encoders: dict[str, Any] = {}
    variant_keys: dict[str, tuple[str, int, int]] = {}
    for model in args.models:
        started = time.perf_counter()
        encoder = TextCrossEncoder(model_name=model, cache_dir=str(args.cache_dir))
        list(encoder.rerank("warm up", ["warm up document"]))
        load_seconds = time.perf_counter() - started
        encoders[model] = encoder
        sizes[model] = model_size_mb(args.cache_dir, model)
        for chars in args.truncate_chars:
            arm = arm_name(model, chars)
            scores: dict[str, list[float]] = {}
            timings: dict[int, list[float]] = {d: [] for d in DEPTHS}
            for qid in scored_ids:
                docs = [truncate(c["content"], chars) for c in candidates[qid]]
                query = dataset[qid]["question"]
                for depth in DEPTHS:  # measured scoring time for exactly K candidates
                    started = time.perf_counter()
                    out = list(encoder.rerank(query, docs[:depth]))
                    timings[depth].append((time.perf_counter() - started) * 1000)
                    if depth == POOL:
                        scores[qid] = [float(x) for x in out]
            latency[arm] = {
                str(d): {
                    "median_ms": round(statistics.median(t), 1),
                    "p95_ms": round(percentile(t, 0.95), 1),
                }
                for d, t in timings.items()
            }
            latency[arm]["load_and_warmup_seconds"] = round(load_seconds, 1)
            for depth in DEPTHS:
                results = {}
                for qid in scored_ids:
                    order = reorder(scores[qid], depth)[:10]
                    results[qid] = [{"metadata": candidates[qid][i]["metadata"]} for i in order]
                lme[f"{arm}@{depth}"] = summarize(dataset, results, scored_ids)
                variant_keys[f"{arm}@{depth}"] = (model, chars, depth)
            print(f"{arm}: done ({latency[arm]['30']})", flush=True)

    ranked = sorted(
        (n for n in lme if n != "baseline"),
        key=lambda n: (-lme[n]["complete_evidence"], -lme[n]["evidence_recall"]),
    )
    chosen = ranked[: args.synthetic_top] if args.synthetic_top else ranked
    synthetic = {
        stem: score_synthetic(suite, [variant_keys[n] for n in chosen], encoders)
        for stem, suite in suites.items()
    }
    report = {
        "scope": "LongMemEval-S development 180 (tuning) + synthetic suites; no held-out data",
        "scored_questions": len(scored_ids),
        "model_download_mb": sizes,
        "rerank_latency_ms": latency,
        "longmemeval_tuning": lme,
        "synthetic_variants_by_complete_evidence": chosen,
        "synthetic": synthetic,
    }
    args.output.write_text(json.dumps(report, indent=2))

    def cat(name: str, category: str) -> str:
        c = lme[name]["categories"].get(category)
        return f"{c['complete']}/{c['n']}" if c else "-"

    print(f"{'variant':40s} {'complete':>9s} {'recall':>7s} {'multi':>7s} {'temporal':>9s}")
    for name, row in lme.items():
        print(
            f"{name:40s} {row['complete_evidence']:>4d}/{row['scored']:<4d} "
            f"{row['evidence_recall']:>7.3f} {cat(name, 'multi-session'):>7s} "
            f"{cat(name, 'temporal-reasoning'):>9s}"
        )
    for arm, lat in latency.items():
        for depth in DEPTHS:
            t = lat[str(depth)]
            print(f"{arm} K={depth}: median {t['median_ms']} ms p95 {t['p95_ms']} ms")
    print(json.dumps(synthetic, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
