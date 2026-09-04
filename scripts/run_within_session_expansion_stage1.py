#!/usr/bin/env python3
"""Stage 1 (API-free) gate for within-session-expansion-v1.1 over the 180 development questions.

Runs the ranked baseline and the candidate policy against the on-disk MemoryBench stores,
computes every Stage 1 measure named in the frozen contract, and emits a pass/fail report
per gate. No model is called; the only inference is the local FastEmbed query embedding
the product already performs on recall.

Coverage is computed exactly as in the error analysis: for each answer session the
baseline retrieved at all, the share of that session's messages present in the context.
Both arms use the same denominator so the delta measures the mechanism, not selection.
"""

from __future__ import annotations

import argparse
import faulthandler
import hashlib
import signal
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

if __package__:
    from scripts.memorybench_bridge import (
        RANKED_CONTEXT_POLICY,
        WITHIN_SESSION_EXPANSION_CONTEXT_POLICY,
        MemoryBenchBridge,
    )
    from scripts.score_content_answer_presence import answer_present, normalize
    from scripts.within_session_expansion import context_json_bytes, split_header
else:  # pragma: no cover
    from memorybench_bridge import (
        RANKED_CONTEXT_POLICY,
        WITHIN_SESSION_EXPANSION_CONTEXT_POLICY,
        MemoryBenchBridge,
    )
    from score_content_answer_presence import answer_present, normalize
    from within_session_expansion import context_json_bytes, split_header

from llm_memory_store import FastEmbedder

EXPERIMENT_ID = "within-session-expansion-v1.1"
PER_QUESTION_DEADLINE_S = 120


class _Deadline(RuntimeError):
    """Raised by the per-question watchdog."""


def _on_alarm(signum: int, frame: object) -> None:  # noqa: ARG001
    raise _Deadline()


RUN_IDS = (
    "llm-memory-store-longmemeval-stratified60-v1",
    "llm-memory-store-longmemeval-kimi-complement440-v1",
    "llm-memory-store-longmemeval-smoke-v1",
)
EXTRACTIVE = {"single-session-user", "single-session-assistant", "knowledge-update"}
SESSION_RE = re.compile(r"^(?P<qid>.+)-session-(?P<idx>\d+)$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]


def _sessions(results: list[dict[str, Any]]) -> set[str]:
    return {r["metadata"]["session_id"] for r in results if r.get("metadata")}


def _context_text(results: list[dict[str, Any]]) -> str:
    return normalize(" ".join(split_header(r.get("content", ""))[1] for r in results[:10]))


def _coverage(
    item: dict[str, Any],
    question_id: str,
    results: list[dict[str, Any]],
    denominator_sessions: set[int],
) -> list[float]:
    """Share of each answer session's messages present, for sessions in the denominator."""
    per_session_indices: dict[int, set[int]] = {}
    for r in results:
        meta = r.get("metadata") or {}
        m = SESSION_RE.match(str(meta.get("session_id", "")))
        if m and m.group("qid") == question_id:
            per_session_indices.setdefault(int(m.group("idx")), set()).add(
                int(meta["message_index"])
            )
    out = []
    for idx in denominator_sessions:
        total = len(item["haystack_sessions"][idx])
        out.append(len(per_session_indices.get(idx, set())) / total if total else 0.0)
    return out


def resolve_container(bridge: MemoryBenchBridge, question_id: str) -> str | None:
    for run_id in RUN_IDS:
        tag = f"{question_id}-{run_id}"
        if bridge._database_path(tag).is_file():
            return tag
    return None


def run_stage1(
    *,
    dataset: Path,
    dev_manifest: Path,
    stratified: Path,
    gold: Path,
    gates_file: Path,
    stores: Path,
    cache_dir: Path,
    output: Path,
    limit: int,
) -> dict[str, Any]:
    faulthandler.enable()
    signal.signal(signal.SIGALRM, _on_alarm)
    items = {str(x["question_id"]): x for x in json.loads(dataset.read_text(encoding="utf-8"))}
    dev_ids = [str(q) for q in json.loads(dev_manifest.read_text())["question_ids"]]
    strat_ids = set(str(q) for q in json.loads(stratified.read_text())["question_ids"])
    gold_map = json.loads(gold.read_text())
    gates = json.loads(gates_file.read_text())["stage_1_local"]["gates"]

    embedder = FastEmbedder(cache_dir=str(cache_dir), local_files_only=True)
    ranked = MemoryBenchBridge(stores, embedder, context_policy=RANKED_CONTEXT_POLICY)
    candidate = MemoryBenchBridge(
        stores, embedder, context_policy=WITHIN_SESSION_EXPANSION_CONTEXT_POLICY
    )

    report: dict[str, Any] = (
        json.loads(output.read_text())
        if output.exists()
        else {
            "schema_version": 1,
            "experiment_id": EXPERIMENT_ID,
            "stage": 1,
            "paid": False,
            "status": "in-progress",
            "limit": limit,
            "input_identity": {
                "dataset_sha256": _sha256(dataset),
                "dev_manifest_sha256": _sha256(dev_manifest),
                "gates_sha256": _sha256(gates_file),
            },
            "questions": {},
        }
    )
    pending = [q for q in dev_ids if q not in report["questions"]]
    print(f"{len(pending)} of {len(dev_ids)} pending", flush=True)

    for n, qid in enumerate(pending, 1):
        item = items[qid]
        tag = resolve_container(ranked, qid)
        if tag is None:
            report["questions"][qid] = {"error": "no store on disk"}
            continue
        query = str(item["question"])
        try:
            signal.alarm(PER_QUESTION_DEADLINE_S)
            base, bdiag = ranked.search_with_diagnostics(tag, query, limit)
            cand, cdiag = candidate.search_with_diagnostics(tag, query, limit)
        except _Deadline:
            report["questions"][qid] = {
                "error": f"exceeded {PER_QUESTION_DEADLINE_S}s per-question deadline"
            }
            print(f"[{n}/{len(pending)}] {qid} DEADLINE", flush=True)
            continue
        finally:
            signal.alarm(0)

        answer_ids = set(item["answer_session_ids"])
        required = {i for i, s in enumerate(item["haystack_session_ids"]) if s in answer_ids}
        base_retrieved_required = {
            int(SESSION_RE.match(s).group("idx"))
            for s in _sessions(base)
            if SESSION_RE.match(s) and SESSION_RE.match(s).group("qid") == qid
        } & required
        row: dict[str, Any] = {
            "question_type": item["question_type"],
            "container_tag": tag,
            "prefix_ok": [m["memory_id"] for m in cand[: len(base)]]
            == [m["memory_id"] for m in base],
            "new_sessions": sorted(_sessions(cand) - _sessions(base)),
            "baseline_bytes": context_json_bytes(base),
            "candidate_bytes": context_json_bytes(cand),
            "baseline_count": len(base),
            "candidate_count": len(cand),
            "expansions_admitted": cdiag.get("expansions_admitted", 0),
            "baseline_selection_ms": bdiag["selection_duration_ms"],
            "candidate_selection_ms": cdiag["selection_duration_ms"],
            "baseline_search_ms": bdiag["total_duration_ms"],
            "candidate_search_ms": cdiag["total_duration_ms"],
            "required_sessions": sorted(required),
            "coverage_denominator_sessions": sorted(base_retrieved_required),
            "baseline_coverage": _coverage(item, qid, base, base_retrieved_required),
            "candidate_coverage": _coverage(item, qid, cand, base_retrieved_required),
        }
        if qid in strat_ids and item["question_type"] in EXTRACTIVE:
            g = gold_map[qid]["answer"]
            row["answer_presence"] = {
                "baseline": answer_present(g, _context_text(base)),
                "candidate": answer_present(g, _context_text(cand)),
            }
        report["questions"][qid] = row
        tmp = output.with_suffix(".tmp")
        tmp.write_text(json.dumps(report, indent=2))
        tmp.replace(output)
        if n % 20 == 0 or n == len(pending):
            print(
                f"[{n}/{len(pending)}] {qid} "
                f"bytes {row['baseline_bytes']}->{row['candidate_bytes']} "
                f"exp={row['expansions_admitted']}",
                flush=True,
            )

    rows = [r for r in report["questions"].values() if "error" not in r]
    bc = [c for r in rows for c in r["baseline_coverage"]]
    cc = [c for r in rows for c in r["candidate_coverage"]]
    by_cat: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        d = by_cat.setdefault(r["question_type"], {"b": [], "c": []})
        d["b"] += r["baseline_coverage"]
        d["c"] += r["candidate_coverage"]
    cat_cov = {
        k: {
            "baseline": statistics.mean(v["b"]) if v["b"] else 0.0,
            "candidate": statistics.mean(v["c"]) if v["c"] else 0.0,
        }
        for k, v in by_cat.items()
    }
    ratios = [r["candidate_bytes"] / r["baseline_bytes"] for r in rows if r["baseline_bytes"]]
    ap = [r["answer_presence"] for r in rows if "answer_presence" in r]
    ap_b = sum(1 for a in ap if a["baseline"])
    ap_c = sum(1 for a in ap if a["candidate"])
    mean_b = statistics.mean(bc) if bc else 0.0
    mean_c = statistics.mean(cc) if cc else 0.0
    measures = {
        "questions_complete": len(rows),
        "prefix_ok_all": all(r["prefix_ok"] for r in rows),
        "new_sessions_total": sum(len(r["new_sessions"]) for r in rows),
        "coverage_mean_baseline": mean_b,
        "coverage_mean_candidate": mean_c,
        "coverage_delta_points": (mean_c - mean_b) * 100,
        "coverage_by_category": cat_cov,
        "bytes_mean_ratio": statistics.mean(ratios) if ratios else 0.0,
        "bytes_p95_ratio": _p95(ratios),
        "candidate_selection_p95_ms": _p95([r["candidate_selection_ms"] for r in rows]),
        "candidate_search_p95_ms": _p95([r["candidate_search_ms"] for r in rows]),
        "answer_presence_stratified_extractive": {
            "n": len(ap),
            "baseline": ap_b,
            "candidate": ap_c,
        },
        "expansions_admitted_mean": statistics.mean([r["expansions_admitted"] for r in rows])
        if rows
        else 0.0,
        "errors": [q for q, r in report["questions"].items() if "error" in r],
    }
    checks = {
        "questions_complete": measures["questions_complete"] == gates["questions_complete"],
        "baseline_top_ten_all_present": measures["prefix_ok_all"],
        "new_sessions_introduced": measures["new_sessions_total"] == 0,
        "coverage_min_absolute": mean_c >= gates["within_session_coverage_mean_min"],
        "coverage_min_points_above_baseline": (mean_c - mean_b) * 100
        >= gates["within_session_coverage_min_points_above_baseline_on_same_180"],
        "no_category_coverage_regression": all(
            v["candidate"] >= v["baseline"] for v in cat_cov.values()
        ),
        "bytes_mean_ratio": measures["bytes_mean_ratio"] <= gates["context_bytes_mean_max_ratio"],
        "bytes_p95_ratio": measures["bytes_p95_ratio"] <= gates["context_bytes_p95_max_ratio"],
        "selection_p95_ms": measures["candidate_selection_p95_ms"] <= gates["selection_p95_ms_max"],
        "search_p95_ms": measures["candidate_search_p95_ms"] <= gates["search_p95_ms_max"],
        "answer_presence_not_fallen": ap_c >= ap_b,
        "zero_errors": not measures["errors"],
    }
    report["measures"] = measures
    report["gates"] = checks
    report["status"] = "passed" if all(checks.values()) else "failed"
    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    tmp = output.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2))
    tmp.replace(output)
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--dev-manifest", type=Path, required=True)
    ap.add_argument("--stratified", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--gates", type=Path, required=True)
    ap.add_argument("--stores", type=Path, required=True)
    ap.add_argument("--cache-dir", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args()
    report = run_stage1(
        dataset=a.dataset,
        dev_manifest=a.dev_manifest,
        stratified=a.stratified,
        gold=a.gold,
        gates_file=a.gates,
        stores=a.stores,
        cache_dir=a.cache_dir,
        output=a.output,
        limit=a.limit,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "gates": report["gates"],
                "coverage": [
                    report["measures"]["coverage_mean_baseline"],
                    report["measures"]["coverage_mean_candidate"],
                ],
                "bytes_mean_ratio": report["measures"]["bytes_mean_ratio"],
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
