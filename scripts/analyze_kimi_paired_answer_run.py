#!/usr/bin/env python3
"""Analyze the frozen paired Kimi answer-quality experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

ARMS = ("baseline", "candidate")


class PairedAnalysisError(RuntimeError):
    """Raised when paired evidence is incomplete or violates the frozen contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mean(values: list[float]) -> float:
    if not values:
        raise PairedAnalysisError("cannot aggregate an empty metric")
    return sum(values) / len(values)


def _p95(values: list[float]) -> float:
    if not values:
        raise PairedAnalysisError("cannot aggregate an empty metric")
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _usage_cost(record: dict[str, Any]) -> float:
    usage = record.get("usage")
    if not isinstance(usage, dict):
        raise PairedAnalysisError("call record lacks usage")
    try:
        return float(usage["calculated_cost_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PairedAnalysisError("call record lacks calculated cost") from exc


def _call_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    token_fields = (
        "prompt_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "completion_tokens",
        "reasoning_tokens",
    )
    durations = [float(record.get("duration_ms", 0)) for record in records]
    return {
        "calls": len(records),
        "cost_usd": round(sum(_usage_cost(record) for record in records), 9),
        "tokens": {
            field: sum(int(record["usage"].get(field, 0)) for record in records)
            for field in token_fields
        },
        "latency_ms": {
            "mean": round(_mean(durations), 3),
            "p95": _p95(durations),
            "max": max(durations),
        },
    }


def _contract_questions(contract: dict[str, Any]) -> int:
    sample = contract.get("sample", contract.get("selection", {}))
    for value in (
        contract.get("question_count"),
        sample.get("questions") if isinstance(sample, dict) else None,
        contract.get("questions"),
    ):
        if value is not None:
            return int(value)
    return 60


def _contract_gates(contract: dict[str, Any]) -> dict[str, Any]:
    gates = contract.get("automated_gates", contract.get("gates", {}))
    if not isinstance(gates, dict):
        raise PairedAnalysisError("contract gates must be an object")
    return gates


def _assert_expected_subset(actual: Any, expected: Any, location: str) -> None:
    """Require every frozen expected value while permitting runtime-only fields."""

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise PairedAnalysisError(f"{location} is not an object")
        for key, value in expected.items():
            if key not in actual:
                raise PairedAnalysisError(f"{location} lacks frozen field {key}")
            _assert_expected_subset(actual[key], value, f"{location}.{key}")
        return
    if actual != expected:
        raise PairedAnalysisError(f"{location} differs from the frozen contract")


def _validate_contract_identity(report: dict[str, Any], contract: dict[str, Any]) -> None:
    if not str(contract.get("status", "")).startswith("frozen-before"):
        raise PairedAnalysisError("contract was not frozen before execution")
    if contract.get("experiment_id") not in (None, report.get("experiment_id")):
        raise PairedAnalysisError("experiment id differs from the frozen contract")
    sample = contract.get("sample", {})
    frozen_ids = contract.get("question_ids")
    if frozen_ids is None and isinstance(sample, dict):
        frozen_ids = sample.get("question_ids")
    if frozen_ids is not None and report.get("question_ids") != frozen_ids:
        raise PairedAnalysisError("question order differs from the frozen contract")
    selection = contract["selection"]
    sources = contract["sources"]
    identity = report.get("input_identity", {})
    expected_identity = {
        "selection_sha256": selection["sha256"],
        "development_manifest_sha256": selection["development_manifest_sha256"],
        "candidate_replay_sha256": sources["session_diverse_raw_sha256"],
        "baseline_checkpoint_sha256": [sources["baseline_checkpoint_sha256"]],
    }
    _assert_expected_subset(identity, expected_identity, "input_identity")
    identity_without_combined = {
        key: value for key, value in identity.items() if key != "combined_sha256"
    }
    if identity.get("combined_sha256") != _canonical_sha256(identity_without_combined):
        raise PairedAnalysisError("combined input identity hash is invalid")
    if selection.get("validation_overlap") != 0 or selection.get("reserve_overlap") != 0:
        raise PairedAnalysisError("frozen selection overlaps a forbidden split")
    if report.get("split_guard") != {
        "role": "development",
        "sealed": False,
        "sealed_validation_opened": False,
        "sealed_competitor_reserve_opened": False,
    }:
        raise PairedAnalysisError("paired run did not preserve the development split guard")

    if report.get("arms") != contract["arms"]:
        raise PairedAnalysisError("arm identities differ from the frozen contract")

    frozen_protocol = contract["model_protocol"]
    protocols = report.get("protocols", {})
    if protocols.get("model_protocol") != frozen_protocol:
        raise PairedAnalysisError("model protocol differs from the frozen contract")
    if protocols.get("budget") != contract["budget"]:
        raise PairedAnalysisError("protocol budget differs from the frozen contract")
    expected_execution = {
        "fresh_answers": True,
        "answer_calls": len(report.get("question_ids", [])) * 2,
        "judge_calls": len(report.get("question_ids", [])) * 2 * 3,
        "question_paired_and_arm_interleaved": True,
    }
    if protocols.get("execution") != expected_execution:
        raise PairedAnalysisError("execution protocol differs from the frozen contract")
    if report.get("context_metrics") != contract["preflight_context_json_bytes"]:
        raise PairedAnalysisError("paired contexts differ from frozen preflight metrics")
    if contract["automated_gates"].get("exact_response_model_required") is not True:
        raise PairedAnalysisError("contract does not require exact response model identity")
    budget = report.get("budget", {})
    if float(budget.get("max_total_usd", -1)) != float(
        contract["budget"]["maximum_total_cost_usd"]
    ):
        raise PairedAnalysisError("run budget differs from the frozen contract")
    if budget.get("unreconciled_reservations_usd") != 0 or report.get("unreconciled_calls"):
        raise PairedAnalysisError("paired run has unreconciled API calls")


def evaluate_gates(
    *,
    report: dict[str, Any],
    arm_metrics: dict[str, dict[str, Any]],
    paired: dict[str, Any],
    cost: dict[str, Any],
    gates: dict[str, Any],
) -> dict[str, bool]:
    """Evaluate the preregistered automated gates."""

    baseline = arm_metrics["baseline"]
    candidate = arm_metrics["candidate"]
    maximum_overall_loss = int(gates["overall_noninferiority_maximum_correct_loss"])
    maximum_category_loss = int(gates["per_category_maximum_correct_loss"])
    targets = set(gates["target_categories"])
    categories = set(baseline["category_accuracy"])
    if not targets or not targets.issubset(categories):
        raise PairedAnalysisError("contract target categories differ from run categories")
    target_gain = sum(
        candidate["category_accuracy"][category]["correct"]
        - baseline["category_accuracy"][category]["correct"]
        for category in targets
    )
    untargeted_loss = sum(
        max(
            0,
            baseline["category_accuracy"][category]["correct"]
            - candidate["category_accuracy"][category]["correct"],
        )
        for category in categories - targets
    )
    minimum_unanimity = float(gates["minimum_vote_unanimity_rate_each_arm"])
    maximum_unanimity_difference = float(gates["maximum_vote_unanimity_rate_difference"])
    exact_model = "kimi-k3"
    failed_calls = sum(
        int(report.get("summary", {}).get(key, 0))
        for key in ("failed_answer_calls", "failed_judge_calls")
    )
    baseline_context = baseline["context_json_bytes"]
    candidate_context = candidate["context_json_bytes"]
    results = {
        "exact_model": report.get("model") == exact_model,
        "overall_noninferiority": (
            candidate["majority_correct"] >= baseline["majority_correct"] - maximum_overall_loss
        ),
        "minimum_candidate_correct": candidate["majority_correct"]
        >= int(gates["minimum_candidate_correct"]),
        "target_category_combined_gain": target_gain
        >= int(gates["target_combined_minimum_correct_gain"]),
        "untargeted_category_combined_noninferiority": untargeted_loss
        <= int(gates["untargeted_combined_maximum_correct_loss"]),
        "per_category_noninferiority": all(
            candidate["category_accuracy"][category]["correct"]
            >= baseline["category_accuracy"][category]["correct"] - maximum_category_loss
            for category in categories
        ),
        "minimum_vote_unanimity_rate": all(
            arm_metrics[arm]["judge_vote_unanimity"] >= minimum_unanimity for arm in ARMS
        ),
        "vote_unanimity_rate_balance": abs(
            baseline["judge_vote_unanimity"] - candidate["judge_vote_unanimity"]
        )
        <= maximum_unanimity_difference,
        "context_mean": candidate_context["mean"]
        <= baseline_context["mean"] * float(gates["context_mean_maximum_ratio"]),
        "context_p95": candidate_context["p95"]
        <= baseline_context["p95"] * float(gates["context_p95_maximum_ratio"]),
        "failed_calls": failed_calls <= int(gates["maximum_failed_calls"]),
        "cost_ceiling": cost["computed_total_usd"] <= float(report["budget"]["max_total_usd"]),
    }
    return results


def analyze_report(report: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    _validate_contract_identity(report, contract)
    if report.get("status") != "completed":
        raise PairedAnalysisError("paired run is not complete")
    if report.get("arm_order") != list(ARMS):
        raise PairedAnalysisError("paired run arms differ from the frozen order")
    question_ids = report.get("question_ids")
    if not isinstance(question_ids, list) or len(question_ids) != _contract_questions(contract):
        raise PairedAnalysisError("paired run has the wrong question count")
    if len(set(question_ids)) != len(question_ids):
        raise PairedAnalysisError("paired run contains duplicate question ids")
    experiment_id = str(report.get("experiment_id", ""))
    expected_arm_order = {}
    for question_id in question_ids:
        digest = hashlib.sha256(f"{experiment_id}{question_id}".encode()).digest()
        expected_arm_order[question_id] = list(ARMS) if digest[0] % 2 == 0 else list(reversed(ARMS))
    if report.get("arm_order_by_question") != expected_arm_order:
        raise PairedAnalysisError("per-question arm order violates the frozen hash rule")

    answers = report.get("answers")
    judgments = report.get("judgments")
    if not isinstance(answers, dict) or set(answers) != set(question_ids):
        raise PairedAnalysisError("answer set differs from question ids")
    if not isinstance(judgments, dict) or set(judgments) != set(question_ids):
        raise PairedAnalysisError("judgment set differs from question ids")

    scores: dict[str, dict[str, int]] = {arm: {} for arm in ARMS}
    votes_by_question: dict[str, dict[str, list[int]]] = {}
    category_scores: dict[str, defaultdict[str, list[int]]] = {
        arm: defaultdict(list) for arm in ARMS
    }
    answer_records: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    judge_records: dict[str, list[dict[str, Any]]] = {arm: [] for arm in ARMS}
    context_bytes: dict[str, list[float]] = {arm: [] for arm in ARMS}

    for question_id in question_ids:
        if set(answers[question_id]) != set(ARMS):
            raise PairedAnalysisError(f"incomplete answers for {question_id}")
        if set(judgments[question_id]) != set(ARMS):
            raise PairedAnalysisError(f"incomplete judgments for {question_id}")
        votes_by_question[question_id] = {}
        categories: set[str] = set()
        for arm in ARMS:
            answer = answers[question_id][arm]
            answer_records[arm].append(answer)
            category = str(answer.get("question_type", ""))
            if not category:
                raise PairedAnalysisError(f"answer lacks question type for {question_id}")
            categories.add(category)
            try:
                context_bytes[arm].append(float(answer["context_json_bytes"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise PairedAnalysisError(
                    f"answer lacks context bytes for {question_id}/{arm}"
                ) from exc
            arm_judgments = judgments[question_id][arm]
            if not isinstance(arm_judgments, dict) or len(arm_judgments) != 3:
                raise PairedAnalysisError(f"expected three judge repeats for {question_id}/{arm}")
            votes: list[int] = []
            for repeat in sorted(arm_judgments, key=int):
                judgment = arm_judgments[repeat]
                try:
                    score = int(judgment["score"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise PairedAnalysisError("judgment lacks a binary score") from exc
                if score not in (0, 1):
                    raise PairedAnalysisError("judgment score must be zero or one")
                votes.append(score)
                judge_records[arm].append(judgment)
            majority = int(sum(votes) >= 2)
            scores[arm][question_id] = majority
            votes_by_question[question_id][arm] = votes
            category_scores[arm][category].append(majority)
        if len(categories) != 1:
            raise PairedAnalysisError(f"question type differs between arms for {question_id}")

    arm_metrics: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        arm_scores = list(scores[arm].values())
        unanimous_sets = sum(len(set(votes_by_question[qid][arm])) == 1 for qid in question_ids)
        arm_metrics[arm] = {
            "majority_correct": sum(arm_scores),
            "questions": len(arm_scores),
            "majority_accuracy": sum(arm_scores) / len(arm_scores),
            "category_accuracy": {
                category: {
                    "correct": sum(values),
                    "questions": len(values),
                    "accuracy": sum(values) / len(values),
                }
                for category, values in sorted(category_scores[arm].items())
            },
            "judge_vote_unanimity": unanimous_sets / len(question_ids),
            "nonunanimous_question_ids": [
                qid for qid in question_ids if len(set(votes_by_question[qid][arm])) != 1
            ],
            "context_json_bytes": {
                "mean": _mean(context_bytes[arm]),
                "p95": _p95(context_bytes[arm]),
                "max": max(context_bytes[arm]),
            },
            "answer_calls": _call_metrics(answer_records[arm]),
            "judge_calls": _call_metrics(judge_records[arm]),
        }

    if set(arm_metrics["baseline"]["category_accuracy"]) != set(
        arm_metrics["candidate"]["category_accuracy"]
    ):
        raise PairedAnalysisError("category sets differ between arms")
    expected_per_category = contract.get("selection", {}).get("questions_per_category")
    if expected_per_category is not None and any(
        category["questions"] != int(expected_per_category)
        for category in arm_metrics["baseline"]["category_accuracy"].values()
    ):
        raise PairedAnalysisError("category counts differ from frozen selection")

    discordant = [
        qid for qid in question_ids if scores["baseline"][qid] != scores["candidate"][qid]
    ]
    nonunanimous = [
        qid
        for qid in question_ids
        if any(len(set(votes_by_question[qid][arm])) != 1 for arm in ARMS)
    ]
    paired = {
        "accuracy_delta": (
            arm_metrics["candidate"]["majority_accuracy"]
            - arm_metrics["baseline"]["majority_accuracy"]
        ),
        "discordant_question_ids": discordant,
        "discordant_questions": len(discordant),
        "nonunanimous_question_ids": nonunanimous,
        "nonunanimous_questions": len(nonunanimous),
        "audit_question_ids": [
            qid for qid in question_ids if qid in set(discordant) | set(nonunanimous)
        ],
        "wins": sum(scores["candidate"][qid] > scores["baseline"][qid] for qid in question_ids),
        "losses": sum(scores["candidate"][qid] < scores["baseline"][qid] for qid in question_ids),
        "ties": sum(scores["candidate"][qid] == scores["baseline"][qid] for qid in question_ids),
    }
    computed_cost = round(
        sum(
            arm_metrics[arm][kind]["cost_usd"]
            for arm in ARMS
            for kind in ("answer_calls", "judge_calls")
        ),
        9,
    )
    try:
        reported_cost = float(report["budget"]["spent_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PairedAnalysisError("paired run lacks reported spend") from exc
    if not math.isclose(computed_cost, reported_cost, abs_tol=1e-8):
        raise PairedAnalysisError("computed call cost differs from reported spend")
    cost = {
        "computed_total_usd": computed_cost,
        "reported_total_usd": reported_cost,
    }
    gate_results = evaluate_gates(
        report=report,
        arm_metrics=arm_metrics,
        paired=paired,
        cost=cost,
        gates=_contract_gates(contract),
    )
    human_required = bool(paired["audit_question_ids"])
    minimum_audit = int(contract.get("human_audit", {}).get("minimum_unique_audit_questions", 4))
    automated_passed = all(gate_results.values())
    audit_sample_conclusive = (
        not human_required or len(paired["audit_question_ids"]) >= minimum_audit
    )
    if not automated_passed:
        status = "failed"
    elif human_required and not audit_sample_conclusive:
        status = "inconclusive-insufficient-audit-sample"
    elif human_required:
        status = "awaiting-blind-human-audit"
    else:
        status = "passed"
    return {
        "schema_version": 1,
        "status": status,
        "experiment_id": report.get("experiment_id"),
        "model": report.get("model"),
        "question_count": len(question_ids),
        "judge_repeats": 3,
        "arms": arm_metrics,
        "paired": paired,
        "cost": cost,
        "gate_results": gate_results,
        "automated_gates_passed": automated_passed,
        "all_gates_passed": automated_passed and not human_required,
        "human_audit_required": human_required,
        "minimum_unique_audit_questions": minimum_audit,
        "audit_sample_conclusive": audit_sample_conclusive,
    }


def build_evidence(raw_path: Path, contract_path: Path) -> dict[str, Any]:
    report = json.loads(raw_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    evidence = analyze_report(report, contract)
    if report.get("input_identity", {}).get("contract_sha256") != _sha256(contract_path):
        raise PairedAnalysisError("raw run identifies a different frozen contract")
    repository_root = contract_path.resolve().parents[2]
    source_paths = {
        "prompt_builder_source_sha256": repository_root
        / "scripts"
        / "run_memorybench_claude_pilot.py",
        "request_builder_source_sha256": repository_root
        / "scripts"
        / "run_memorybench_kimi_qualification.py",
    }
    for contract_key, source_path in source_paths.items():
        if _sha256(source_path) != contract["model_protocol"][contract_key]:
            raise PairedAnalysisError(f"{contract_key} differs from frozen source")
    evidence["source_sha256"] = {
        "raw": _sha256(raw_path),
        "contract": _sha256(contract_path),
    }
    evidence["input_identity"] = report.get("input_identity")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = build_evidence(args.raw, args.contract)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["automated_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
