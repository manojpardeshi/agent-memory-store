#!/usr/bin/env python3
"""Stage 1 (API-free) gate for event-date-annotation-v1 over the 180 development questions.

Runs the ranked baseline and the annotation policy on the on-disk stores, checks that the
context is unchanged apart from the added field, measures how many temporal questions receive
an annotation on labelled answer-session evidence, and saves the candidate context in the
checkpoint shape the kimi runner reads.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from llm_memory_store import FastEmbedder
from scripts.memorybench_bridge import (
    EVENT_DATE_CONTEXT_POLICY,
    RANKED_CONTEXT_POLICY,
    MemoryBenchBridge,
)
from scripts.run_within_session_expansion_stage1 import SESSION_RE, _p95, resolve_container
from scripts.within_session_expansion import context_json_bytes

VOLATILE = {"event_dates", "score", "recency_score"}


def _stable(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in item.items() if k not in VOLATILE} for item in items]


def main() -> int:
    ap = argparse.ArgumentParser()
    for name in (
        "dataset",
        "dev-manifest",
        "gates",
        "stores",
        "cache-dir",
        "output",
        "candidate-checkpoint",
    ):
        ap.add_argument(f"--{name}", type=Path, required=True)
    a = ap.parse_args()

    items = {str(x["question_id"]): x for x in json.loads(a.dataset.read_text())}
    dev_ids = [str(q) for q in json.loads(a.dev_manifest.read_text())["question_ids"]]
    gates = json.loads(a.gates.read_text())["stage_1_local"]["gates"]
    embedder = FastEmbedder(cache_dir=str(a.cache_dir), local_files_only=True)
    ranked = MemoryBenchBridge(a.stores, embedder, context_policy=RANKED_CONTEXT_POLICY)
    candidate = MemoryBenchBridge(a.stores, embedder, context_policy=EVENT_DATE_CONTEXT_POLICY)

    rows: dict[str, dict[str, Any]] = {}
    cand_cp: dict[str, Any] = {
        "status": "in-progress",
        "policy": EVENT_DATE_CONTEXT_POLICY,
        "targetQuestionIds": dev_ids,
        "questions": {},
    }
    for n, qid in enumerate(dev_ids, 1):
        item = items[qid]
        tag = resolve_container(ranked, qid)
        if tag is None:
            rows[qid] = {"error": "no store on disk"}
            continue
        query = str(item["question"])
        base, bdiag = ranked.search_with_diagnostics(tag, query, 10)
        cand, cdiag = candidate.search_with_diagnostics(tag, query, 10)
        answer_ids = set(item["answer_session_ids"])
        required = {i for i, s in enumerate(item["haystack_session_ids"]) if s in answer_ids}
        on_answer_session = 0
        for r in cand:
            m = SESSION_RE.match(str((r.get("metadata") or {}).get("session_id", "")))
            if (
                "event_dates" in r
                and m
                and m.group("qid") == qid
                and int(m.group("idx")) in required
            ):
                on_answer_session += 1
        rows[qid] = {
            "question_type": item["question_type"],
            "unchanged_except_annotation": _stable(base) == _stable(cand),
            "annotated_items": cdiag.get("annotated_items", 0),
            "annotated_answer_session_items": on_answer_session,
            "baseline_bytes": context_json_bytes(base),
            "candidate_bytes": context_json_bytes(cand),
            "candidate_selection_ms": cdiag["selection_duration_ms"],
            "candidate_search_ms": cdiag["total_duration_ms"],
        }
        cand_cp["questions"][qid] = {
            "questionId": qid,
            "question": query,
            "groundTruth": str(item["answer"]),
            "questionType": item["question_type"],
            "phases": {"search": {"status": "completed", "results": cand}},
        }
        if n % 30 == 0:
            print(f"[{n}/{len(dev_ids)}]", flush=True)

    ok = [r for r in rows.values() if "error" not in r]
    temporal = [r for r in ok if r["question_type"] == "temporal-reasoning"]
    ratios = [r["candidate_bytes"] / r["baseline_bytes"] for r in ok if r["baseline_bytes"]]
    measures = {
        "questions_complete": len(ok),
        "errors": [q for q, r in rows.items() if "error" in r],
        "all_unchanged_except_annotation": all(r["unchanged_except_annotation"] for r in ok),
        "questions_with_any_annotation": sum(1 for r in ok if r["annotated_items"]),
        "temporal_questions": len(temporal),
        "temporal_with_answer_session_annotation": sum(
            1 for r in temporal if r["annotated_answer_session_items"]
        ),
        "annotated_items_total": sum(r["annotated_items"] for r in ok),
        "bytes_mean_ratio": statistics.mean(ratios),
        "bytes_p95_ratio": _p95(ratios),
        "selection_p95_ms": _p95([r["candidate_selection_ms"] for r in ok]),
        "search_p95_ms": _p95([r["candidate_search_ms"] for r in ok]),
    }
    checks = {
        "questions_complete": measures["questions_complete"] == gates["questions_complete"],
        "zero_errors": not measures["errors"],
        "unchanged_except_annotation": measures["all_unchanged_except_annotation"],
        "temporal_reach": measures["temporal_with_answer_session_annotation"]
        >= gates["min_temporal_questions_with_answer_session_annotation"],
        "bytes_mean_ratio": measures["bytes_mean_ratio"] <= gates["context_bytes_mean_max_ratio"],
        "bytes_p95_ratio": measures["bytes_p95_ratio"] <= gates["context_bytes_p95_max_ratio"],
        "selection_p95_ms": measures["selection_p95_ms"] <= gates["selection_p95_ms_max"],
        "search_p95_ms": measures["search_p95_ms"] <= gates["search_p95_ms_max"],
    }
    report = {
        "schema_version": 1,
        "experiment_id": "event-date-annotation-v1",
        "stage": 1,
        "paid": False,
        "status": "passed" if all(checks.values()) else "failed",
        "measures": measures,
        "gates": checks,
        "questions": rows,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    a.output.write_text(json.dumps(report, indent=2))
    cand_cp["status"] = "completed" if len(cand_cp["questions"]) == len(dev_ids) else "in-progress"
    a.candidate_checkpoint.write_text(json.dumps(cand_cp))
    print(json.dumps({"status": report["status"], "gates": checks, "measures": measures}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
