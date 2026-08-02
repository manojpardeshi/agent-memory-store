#!/usr/bin/env python3
"""Analyze the frozen session-diverse development replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

if __package__:
    from scripts.analyze_longmemeval_retrieval import (
        analyze_retrieval,
        merge_checkpoints,
    )
else:
    from analyze_longmemeval_retrieval import analyze_retrieval, merge_checkpoints


class SessionDiverseAnalysisError(RuntimeError):
    """Raised when candidate evidence differs from the frozen experiment."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _p(values: list[float], quantile: float) -> float:
    if not values:
        raise SessionDiverseAnalysisError("cannot aggregate an empty metric")
    return sorted(values)[math.ceil(quantile * len(values)) - 1]


def _mean(values: list[float]) -> float:
    if not values:
        raise SessionDiverseAnalysisError("cannot aggregate an empty metric")
    return sum(values) / len(values)


def _distinct_sessions(results: list[dict[str, Any]]) -> int:
    sessions: set[str] = set()
    for result in results:
        metadata = result.get("metadata")
        session_id = metadata.get("session_id") if isinstance(metadata, dict) else None
        if not isinstance(session_id, str) or not session_id:
            raise SessionDiverseAnalysisError("result lacks provenance session_id")
        sessions.add(session_id)
    return len(sessions)


def evaluate_gates(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    operational: dict[str, Any],
    gates: dict[str, Any],
) -> dict[str, bool]:
    multi_base = baseline["categories"]["multi-session"][
        "answer_session_recall_at_10"
    ]
    multi_candidate = candidate["categories"]["multi-session"][
        "answer_session_recall_at_10"
    ]
    temporal_base = baseline["categories"]["temporal-reasoning"][
        "answer_session_recall_at_10"
    ]
    temporal_candidate = candidate["categories"]["temporal-reasoning"][
        "answer_session_recall_at_10"
    ]
    target_improved = (
        multi_candidate >= float(gates["multi_session_recall_minimum"])
        and temporal_candidate >= temporal_base
    ) or (
        temporal_candidate >= float(gates["temporal_reasoning_recall_minimum"])
        and multi_candidate >= multi_base
    )
    maximum_category_drop = float(gates["maximum_category_recall_drop"])
    return {
        "target_category_improvement": target_improved,
        "overall_recall": candidate["overall"]["answer_session_recall_at_10"]
        >= float(gates["overall_recall_minimum"]),
        "overall_mrr": candidate["overall"]["mrr_at_10"]
        >= float(gates["overall_mrr_minimum"]),
        "context_bytes_mean": operational["context_json_bytes"]["mean_ratio"]
        <= float(gates["context_json_bytes_mean_maximum_ratio"]),
        "context_bytes_p95": operational["context_json_bytes"]["p95_ratio"]
        <= float(gates["context_json_bytes_p95_maximum_ratio"]),
        "selection_latency_p50": operational["selection_latency_ms"]["p50"]
        <= float(gates["selection_latency_ms_p50_maximum"]),
        "selection_latency_p95": operational["selection_latency_ms"]["p95"]
        <= float(gates["selection_latency_ms_p95_maximum"]),
        "search_latency_p95": operational["search_latency_ms"]["p95"]
        <= float(gates["search_latency_ms_p95_maximum"]),
        "category_recall_noninferiority": all(
            candidate["categories"][category]["answer_session_recall_at_10"]
            >= baseline["categories"][category]["answer_session_recall_at_10"]
            - maximum_category_drop
            for category in baseline["categories"]
        ),
        "question_recall_losses": operational["questions_with_recall_loss"]
        <= int(gates["maximum_questions_with_recall_loss"]),
        "distinct_session_gain": operational["distinct_sessions"]["mean_gain"]
        >= float(gates["minimum_distinct_sessions_mean_gain"]),
        "result_count_unchanged": operational["questions_with_result_count_change"]
        == 0,
        "ranked_prefix_reproduced": operational[
            "questions_with_ranked_prefix_mismatch"
        ]
        == 0,
    }


def build_evidence(
    *,
    dataset: list[dict[str, Any]],
    manifest: dict[str, Any],
    baseline_checkpoints: list[dict[str, Any]],
    candidate_raw: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    if candidate_raw.get("status") != "completed":
        raise SessionDiverseAnalysisError("candidate replay is incomplete")
    if manifest.get("role") != "development" or manifest.get("sealed") is not False:
        raise SessionDiverseAnalysisError("analysis requires the unsealed development split")
    question_ids = manifest.get("question_ids")
    if not isinstance(question_ids, list) or len(question_ids) != 180:
        raise SessionDiverseAnalysisError("development manifest must contain 180 questions")
    if candidate_raw.get("question_ids") != question_ids:
        raise SessionDiverseAnalysisError("candidate question order differs from the manifest")
    if set(candidate_raw.get("questions", {})) != set(question_ids):
        raise SessionDiverseAnalysisError("candidate question results are incomplete")
    if candidate_raw.get("context_policy") != contract.get("candidate_policy"):
        raise SessionDiverseAnalysisError("candidate policy differs from the frozen contract")

    merged = merge_checkpoints(baseline_checkpoints)
    baseline_checkpoint = {
        "status": "completed",
        "targetQuestionIds": question_ids,
        "questions": {
            question_id: merged["questions"][question_id]
            for question_id in question_ids
        },
    }
    candidate_checkpoint = {
        "status": "completed",
        "targetQuestionIds": question_ids,
        "questions": {
            question_id: {
                "phases": {
                    "search": {
                        "results": candidate_raw["questions"][question_id]["results"]
                    }
                }
            }
            for question_id in question_ids
        },
    }
    baseline = analyze_retrieval(dataset, baseline_checkpoint)
    candidate = analyze_retrieval(dataset, candidate_checkpoint)

    baseline_by_id = {row["question_id"]: row for row in baseline["questions"]}
    candidate_by_id = {row["question_id"]: row for row in candidate["questions"]}
    context_bytes = [
        float(candidate_raw["questions"][question_id]["context_json_bytes"])
        for question_id in question_ids
    ]
    selection_latency = [
        float(
            candidate_raw["questions"][question_id]["diagnostics"][
                "selection_duration_ms"
            ]
        )
        for question_id in question_ids
    ]
    search_latency = [
        float(
            candidate_raw["questions"][question_id]["diagnostics"][
                "total_duration_ms"
            ]
        )
        for question_id in question_ids
    ]
    baseline_distinct = [
        _distinct_sessions(
            baseline_checkpoint["questions"][question_id]["phases"]["search"][
                "results"
            ]
        )
        for question_id in question_ids
    ]
    candidate_distinct = [
        _distinct_sessions(candidate_raw["questions"][question_id]["results"])
        for question_id in question_ids
    ]
    baseline_context_bytes = [
        float(
            len(
                json.dumps(
                    baseline_checkpoint["questions"][question_id]["phases"][
                        "search"
                    ]["results"],
                    indent=2,
                    ensure_ascii=False,
                ).encode("utf-8")
            )
        )
        for question_id in question_ids
    ]
    baseline_context = contract["development_baseline"]
    if not math.isclose(
        _mean(baseline_context_bytes),
        float(baseline_context["context_json_bytes_mean"]),
    ) or _p(baseline_context_bytes, 0.95) != float(
        baseline_context["context_json_bytes_p95"]
    ):
        raise SessionDiverseAnalysisError(
            "frozen baseline context metrics differ from source checkpoints"
        )
    candidate_context_mean = _mean(context_bytes)
    candidate_context_p95 = _p(context_bytes, 0.95)
    operational = {
        "context_json_bytes": {
            "baseline_mean": baseline_context["context_json_bytes_mean"],
            "candidate_mean": candidate_context_mean,
            "mean_ratio": candidate_context_mean
            / float(baseline_context["context_json_bytes_mean"]),
            "baseline_p95": baseline_context["context_json_bytes_p95"],
            "candidate_p95": candidate_context_p95,
            "p95_ratio": candidate_context_p95
            / float(baseline_context["context_json_bytes_p95"]),
        },
        "selection_latency_ms": {
            "mean": _mean(selection_latency),
            "p50": _p(selection_latency, 0.5),
            "p95": _p(selection_latency, 0.95),
            "max": max(selection_latency),
        },
        "search_latency_ms": {
            "mean": _mean(search_latency),
            "p50": _p(search_latency, 0.5),
            "p95": _p(search_latency, 0.95),
            "max": max(search_latency),
        },
        "distinct_sessions": {
            "baseline_mean": _mean([float(value) for value in baseline_distinct]),
            "candidate_mean": _mean([float(value) for value in candidate_distinct]),
            "mean_gain": _mean([float(value) for value in candidate_distinct])
            - _mean([float(value) for value in baseline_distinct]),
        },
        "questions_with_recall_loss": sum(
            candidate_by_id[question_id]["answer_session_recall_at_10"]
            < baseline_by_id[question_id]["answer_session_recall_at_10"]
            for question_id in question_ids
        ),
        "questions_with_result_count_change": sum(
            len(candidate_raw["questions"][question_id]["results"])
            != len(
                baseline_checkpoint["questions"][question_id]["phases"]["search"][
                    "results"
                ]
            )
            for question_id in question_ids
        ),
        "questions_with_ranked_prefix_mismatch": sum(
            candidate_raw["questions"][question_id]["diagnostics"][
                "ranked_pool_top_10_memory_ids"
            ][: len(baseline_checkpoint["questions"][question_id]["phases"]["search"]["results"])]
            != [
                item["memory_id"]
                for item in baseline_checkpoint["questions"][question_id]["phases"][
                    "search"
                ]["results"]
            ]
            for question_id in question_ids
        ),
    }
    del baseline["questions"]
    del candidate["questions"]
    gate_results = evaluate_gates(baseline, candidate, operational, contract["gates"])
    return {
        "schema_version": 1,
        "status": "passed" if all(gate_results.values()) else "failed",
        "experiment_id": contract["experiment_id"],
        "scope": contract["scope"],
        "candidate_policy": contract["candidate_policy"],
        "questions": len(question_ids),
        "baseline": baseline,
        "candidate": candidate,
        "operational": operational,
        "gate_thresholds": contract["gates"],
        "gate_results": gate_results,
        "all_gates_passed": all(gate_results.values()),
        "authorization_on_pass": contract["authorization_on_pass"],
        "sealed_validation_opened": False,
        "reserve_opened": False,
        "hosted_api_cost_usd": 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--baseline-checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {
        "dataset": args.dataset,
        "manifest": args.manifest,
        "candidate": args.candidate,
        "gates": args.gates,
    }
    loaded = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in paths.items()
    }
    manifest_hash = _sha256(args.manifest)
    if loaded["gates"].get("development_manifest", {}).get("sha256") != manifest_hash:
        raise SessionDiverseAnalysisError("frozen gate identifies a different manifest")
    if loaded["candidate"].get("manifest_sha256") != manifest_hash:
        raise SessionDiverseAnalysisError("candidate identifies a different manifest")
    if loaded["manifest"].get("dataset_sha256") != _sha256(args.dataset):
        raise SessionDiverseAnalysisError("manifest identifies a different dataset")
    checkpoint_hashes = sorted(_sha256(path) for path in args.baseline_checkpoint)
    if loaded["candidate"].get("source_checkpoint_sha256") != checkpoint_hashes:
        raise SessionDiverseAnalysisError("candidate identifies different source checkpoints")
    if loaded["candidate"].get("gate_sha256") != _sha256(args.gates):
        raise SessionDiverseAnalysisError("candidate identifies a different frozen gate")
    evidence = build_evidence(
        dataset=loaded["dataset"],
        manifest=loaded["manifest"],
        baseline_checkpoints=[
            json.loads(path.read_text(encoding="utf-8"))
            for path in args.baseline_checkpoint
        ],
        candidate_raw=loaded["candidate"],
        contract=loaded["gates"],
    )
    evidence["source_sha256"] = {
        **{name: _sha256(path) for name, path in paths.items()},
        "baseline_checkpoints": checkpoint_hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["all_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
