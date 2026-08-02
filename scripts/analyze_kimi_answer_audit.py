#!/usr/bin/env python3
"""Validate a human audit of frozen Kimi-generated answers."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class AnswerAuditAnalysisError(RuntimeError):
    """Raised when answer-audit evidence is incomplete or incompatible."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_evidence(
    packet: dict[str, Any],
    key: dict[str, Any],
    kimi: dict[str, Any],
    gate_contract: dict[str, Any],
) -> dict[str, Any]:
    if packet.get("status") != "human-scored":
        raise AnswerAuditAnalysisError("human answer-audit packet is not complete")
    if kimi.get("status") != "completed":
        raise AnswerAuditAnalysisError("Kimi qualification run is not complete")
    if gate_contract.get("status") != "frozen-before-human-answer-audit":
        raise AnswerAuditAnalysisError("answer-audit gate was not frozen before scoring")

    expected_model = gate_contract.get("candidate_answer_model")
    expected_repeat = int(gate_contract.get("answer_repeat", -1))
    expected_questions = int(gate_contract.get("unique_questions", 0))
    for source_name, source in (("packet", packet), ("key", key)):
        if source.get("candidate_answer_model") != expected_model:
            raise AnswerAuditAnalysisError(
                f"{source_name} candidate model differs from the frozen gate"
            )
        if int(source.get("answer_repeat", -1)) != expected_repeat:
            raise AnswerAuditAnalysisError(
                f"{source_name} answer repeat differs from the frozen gate"
            )
    if kimi.get("model") != expected_model:
        raise AnswerAuditAnalysisError("raw answer source model differs from the frozen gate")

    packet_items = packet.get("items")
    key_items = key.get("items")
    if not isinstance(packet_items, list) or not isinstance(key_items, list):
        raise AnswerAuditAnalysisError("packet and key must contain item lists")
    if len(packet_items) != expected_questions or len(key_items) != expected_questions:
        raise AnswerAuditAnalysisError("packet or key has the wrong question count")
    packet_by_id = {item["audit_id"]: item for item in packet_items}
    key_by_id = {item["audit_id"]: item for item in key_items}
    if len(packet_by_id) != expected_questions or len(key_by_id) != expected_questions:
        raise AnswerAuditAnalysisError("audit IDs must be unique")
    if set(packet_by_id) != set(key_by_id):
        raise AnswerAuditAnalysisError("audit IDs differ between packet and key")

    question_ids = [str(item["question_id"]) for item in key_items]
    if len(set(question_ids)) != expected_questions:
        raise AnswerAuditAnalysisError("question IDs must be unique")
    if set(question_ids) - set(kimi.get("question_ids", [])):
        raise AnswerAuditAnalysisError("key includes questions outside the raw Kimi run")

    rows: list[dict[str, Any]] = []
    category_scores: defaultdict[str, list[int]] = defaultdict(list)
    for audit_id in packet_by_id:
        item = packet_by_id[audit_id]
        question_id = str(key_by_id[audit_id]["question_id"])
        score = item.get("human_score")
        if isinstance(score, bool) or not isinstance(score, int) or score not in (0, 1):
            raise AnswerAuditAnalysisError(f"invalid human score for {audit_id}")
        if item.get("candidate_answer_model") != expected_model:
            raise AnswerAuditAnalysisError(f"wrong candidate model for {audit_id}")
        try:
            raw_answer = kimi["answers"][question_id][str(expected_repeat)]
        except (KeyError, TypeError) as error:
            raise AnswerAuditAnalysisError(
                f"missing raw Kimi answer for {audit_id}"
            ) from error
        if item.get("candidate_answer") != raw_answer.get("answer"):
            raise AnswerAuditAnalysisError(
                f"candidate answer does not match raw Kimi output for {audit_id}"
            )
        category = str(item.get("question_type"))
        if category != raw_answer.get("question_type"):
            raise AnswerAuditAnalysisError(f"question type mismatch for {audit_id}")
        category_scores[category].append(score)
        rows.append(
            {
                "audit_id": audit_id,
                "question_id": question_id,
                "question_type": category,
                "human_score": score,
            }
        )

    correct = sum(row["human_score"] for row in rows)
    accuracy = correct / len(rows)
    gate_results = {
        "exact_model": expected_model == "kimi-k3",
        "answer_repeat_is_zero": expected_repeat == 0,
        "unique_question_count": len(rows) == expected_questions,
        "minimum_human_correct": correct
        >= int(gate_contract["minimum_human_correct"]),
        "minimum_human_accuracy": accuracy
        >= float(gate_contract["minimum_human_accuracy"]),
        "exact_raw_answer_provenance": True,
    }
    return {
        "schema_version": 1,
        "status": "passed" if all(gate_results.values()) else "failed",
        "audit_scope": "kimi-k3-answer-quality",
        "candidate_answer_model": expected_model,
        "answer_repeat": expected_repeat,
        "questions": len(rows),
        "human_correct": correct,
        "human_incorrect": len(rows) - correct,
        "human_accuracy": accuracy,
        "missed_audit_ids": [
            row["audit_id"] for row in rows if row["human_score"] == 0
        ],
        "category_accuracy": {
            category: {
                "correct": sum(scores),
                "questions": len(scores),
                "accuracy": sum(scores) / len(scores),
            }
            for category, scores in sorted(category_scores.items())
        },
        "provenance": {
            "raw_model": kimi.get("model"),
            "raw_answer_repeat": expected_repeat,
            "exact_answer_matches": len(rows),
            "unique_question_ids": len(set(question_ids)),
        },
        "gate_thresholds": {
            "minimum_human_correct": int(gate_contract["minimum_human_correct"]),
            "minimum_human_accuracy": float(
                gate_contract["minimum_human_accuracy"]
            ),
        },
        "gate_results": gate_results,
        "all_gates_passed": all(gate_results.values()),
        "failure_policy": gate_contract.get("failure_policy"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--kimi", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = {
        "packet": args.packet,
        "key": args.key,
        "kimi": args.kimi,
        "gates": args.gates,
    }
    loaded = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in inputs.items()
    }
    declared_kimi_hash = loaded["key"].get("source_sha256", {}).get("kimi")
    actual_kimi_hash = _sha256(args.kimi)
    if declared_kimi_hash != actual_kimi_hash:
        raise AnswerAuditAnalysisError("key does not identify the supplied raw Kimi run")
    declared_checkpoint_hash = loaded["key"].get("source_sha256", {}).get(
        "checkpoint"
    )
    if declared_checkpoint_hash != loaded["kimi"].get("source_checkpoint_sha256"):
        raise AnswerAuditAnalysisError(
            "key and raw Kimi run identify different source checkpoints"
        )
    evidence = build_evidence(
        loaded["packet"], loaded["key"], loaded["kimi"], loaded["gates"]
    )
    evidence["source_sha256"] = {
        name: _sha256(path) for name, path in inputs.items()
    }
    evidence["declared_checkpoint_sha256"] = declared_checkpoint_hash
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["all_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
