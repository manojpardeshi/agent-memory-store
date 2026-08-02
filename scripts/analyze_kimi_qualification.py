#!/usr/bin/env python3
"""Aggregate raw Kimi qualification runs without copying benchmark answers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


class AnalysisError(RuntimeError):
    """Raised when raw qualification evidence is incomplete or incompatible."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _majority(values: list[int]) -> int:
    if not values or len(values) % 2 == 0:
        raise AnalysisError("majority votes must contain a positive odd count")
    return int(sum(values) > len(values) // 2)


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def _call_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    token_names = (
        "prompt_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "completion_tokens",
        "reasoning_tokens",
    )
    durations = [int(record["duration_ms"]) for record in records]
    return {
        "calls": len(records),
        "cost_usd": round(
            sum(float(record["usage"]["calculated_cost_usd"]) for record in records),
            9,
        ),
        "tokens": {
            name: sum(int(record["usage"].get(name, 0)) for record in records)
            for name in token_names
        },
        "latency_ms": {
            "mean": round(sum(durations) / len(durations), 3) if durations else 0,
            "p95": _p95(durations),
            "max": max(durations, default=0),
        },
    }


def analyze_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("status") != "completed":
        raise AnalysisError("qualification report is not complete")
    question_ids = report.get("question_ids")
    if not isinstance(question_ids, list) or not question_ids:
        raise AnalysisError("qualification report has no questions")

    question_scores: dict[str, int] = {}
    category_scores: dict[str, list[int]] = defaultdict(list)
    answer_records: list[dict[str, Any]] = []
    judge_records: list[dict[str, Any]] = []
    answer_run_scores: defaultdict[str, list[int]] = defaultdict(list)
    unanimous_judge_sets = 0
    answer_repeat_agreements = 0
    answer_repeat_pairs = 0
    stable_questions = 0

    for question_id in question_ids:
        answers = report.get("answers", {}).get(question_id, {})
        judgments = report.get("judgments", {}).get(question_id, {})
        if not answers or set(answers) != set(judgments):
            raise AnalysisError(f"incomplete answer/judgment set for {question_id}")
        majority_by_answer: list[int] = []
        category: str | None = None
        for answer_key in sorted(answers, key=int):
            answer = answers[answer_key]
            answer_records.append(answer)
            category = str(answer["question_type"])
            votes_by_key = judgments[answer_key]
            votes = [
                int(votes_by_key[key]["score"])
                for key in sorted(votes_by_key, key=int)
            ]
            judge_records.extend(votes_by_key.values())
            majority_score = _majority(votes)
            majority_by_answer.append(majority_score)
            answer_run_scores[answer_key].append(majority_score)
            unanimous_judge_sets += int(len(set(votes)) == 1)
        if category is None:
            raise AnalysisError(f"missing category for {question_id}")
        question_score = _majority(majority_by_answer)
        question_scores[question_id] = question_score
        category_scores[category].append(question_score)
        stable_questions += int(len(set(majority_by_answer)) == 1)
        for left in range(len(majority_by_answer)):
            for right in range(left + 1, len(majority_by_answer)):
                answer_repeat_pairs += 1
                answer_repeat_agreements += int(
                    majority_by_answer[left] == majority_by_answer[right]
                )

    answer_count = len(answer_records)
    correct = sum(question_scores.values())
    answer_repeat_accuracy = {
        key: sum(scores) / len(scores) for key, scores in answer_run_scores.items()
    }
    return {
        "model": report.get("model"),
        "context_mode": report.get("context_protocol", {}).get("mode", "retrieved"),
        "question_count": len(question_ids),
        "answer_repeats": len(answer_run_scores),
        "judge_repeats": len(judge_records) // answer_count,
        "majority_correct": correct,
        "majority_accuracy": correct / len(question_ids),
        "category_accuracy": {
            category: {
                "correct": sum(scores),
                "questions": len(scores),
                "accuracy": sum(scores) / len(scores),
            }
            for category, scores in sorted(category_scores.items())
        },
        "answer_repeat_accuracy": answer_repeat_accuracy,
        "judge_vote_unanimity": unanimous_judge_sets / answer_count,
        "stable_question_rate": stable_questions / len(question_ids),
        "answer_repeat_pairwise_agreement": (
            answer_repeat_agreements / answer_repeat_pairs
            if answer_repeat_pairs
            else None
        ),
        "answer_calls": _call_metrics(answer_records),
        "judge_calls": _call_metrics(judge_records),
        "reported_total_cost_usd": float(report["budget"]["spent_usd"]),
    }


def build_evidence(
    retrieved_path: Path,
    control_path: Path,
    human_audit_path: Path | None = None,
    answer_human_audit_path: Path | None = None,
) -> dict[str, Any]:
    retrieved_raw = json.loads(retrieved_path.read_text(encoding="utf-8"))
    control_raw = json.loads(control_path.read_text(encoding="utf-8"))
    if retrieved_raw.get("question_ids") != control_raw.get("question_ids"):
        raise AnalysisError("retrieved and control runs use different questions")
    if retrieved_raw.get("model") != control_raw.get("model"):
        raise AnalysisError("retrieved and control runs use different models")
    retrieved = analyze_report(retrieved_raw)
    control = analyze_report(control_raw)
    if retrieved["context_mode"] != "retrieved" or control["context_mode"] != "empty":
        raise AnalysisError("expected retrieved evidence followed by empty-context control")
    total_cost = retrieved["reported_total_cost_usd"] + control["reported_total_cost_usd"]
    evidence = {
        "schema_version": 1,
        "status": "answerer-mechanics-passed-judge-human-audit-pending",
        "model": retrieved["model"],
        "selection_sha256": retrieved_raw.get("selection_sha256"),
        "source_checkpoint_sha256": retrieved_raw.get("source_checkpoint_sha256"),
        "raw_evidence": {
            "retrieved_sha256": _sha256(retrieved_path),
            "empty_context_sha256": _sha256(control_path),
        },
        "retrieved_context": retrieved,
        "empty_context_control": control,
        "memory_attributable_accuracy_uplift": (
            retrieved["majority_accuracy"] - control["majority_accuracy"]
        ),
        "total_cost_usd": round(total_cost, 9),
        "qualification_gates": {
            "exact_model": retrieved["model"] == "kimi-k3",
            "retrieved_accuracy_at_least_0_70": retrieved["majority_accuracy"] >= 0.70,
            "judge_vote_unanimity_at_least_0_95": (
                retrieved["judge_vote_unanimity"] >= 0.95
            ),
            "answer_repeat_pairwise_agreement_at_least_0_90": (
                (retrieved["answer_repeat_pairwise_agreement"] or 0) >= 0.90
            ),
            "empty_context_accuracy_at_most_0_10": control["majority_accuracy"] <= 0.10,
            "human_judge_audit_complete": False,
            "human_answer_audit_complete": False,
        },
    }
    if human_audit_path is not None:
        human_audit = json.loads(human_audit_path.read_text(encoding="utf-8"))
        if human_audit.get("status") != "passed" or not human_audit.get(
            "all_gates_passed"
        ):
            raise AnalysisError("human judge audit did not pass every frozen gate")
        evidence["status"] = "judge-qualified-answerer-human-audit-pending"
        evidence["qualification_gates"]["human_judge_audit_complete"] = True
        evidence["human_judge_audit"] = human_audit
        evidence["raw_evidence"]["human_audit_sha256"] = _sha256(human_audit_path)
        evidence["total_cost_usd"] = round(
            float(evidence["total_cost_usd"]) + float(human_audit["cost_usd"]), 9
        )
    if answer_human_audit_path is not None:
        answer_human_audit = json.loads(
            answer_human_audit_path.read_text(encoding="utf-8")
        )
        if answer_human_audit.get("status") != "passed" or not answer_human_audit.get(
            "all_gates_passed"
        ):
            raise AnalysisError("human answer audit did not pass every frozen gate")
        if answer_human_audit.get("candidate_answer_model") != retrieved["model"]:
            raise AnalysisError("human answer audit used a different candidate model")
        evidence["qualification_gates"]["human_answer_audit_complete"] = True
        evidence["human_answer_audit"] = answer_human_audit
        evidence["raw_evidence"]["answer_human_audit_sha256"] = _sha256(
            answer_human_audit_path
        )
        evidence["status"] = (
            "answerer-and-judge-qualified"
            if evidence["qualification_gates"]["human_judge_audit_complete"]
            else "answerer-qualified-judge-human-audit-pending"
        )
    if (
        evidence["qualification_gates"]["human_judge_audit_complete"]
        and evidence["qualification_gates"]["human_answer_audit_complete"]
    ):
        evidence["status"] = (
            "answerer-and-judge-qualified"
            if all(evidence["qualification_gates"].values())
            else "qualification-failed"
        )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieved", type=Path, required=True)
    parser.add_argument("--empty-context", type=Path, required=True)
    parser.add_argument("--human-audit", type=Path)
    parser.add_argument("--answer-human-audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = build_evidence(
        args.retrieved,
        args.empty_context,
        args.human_audit,
        args.answer_human_audit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
