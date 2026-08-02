#!/usr/bin/env python3
"""Prepare a deterministic blind human-audit packet from frozen Claude answers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SEED = "kimi-k3-judge-human-audit-v1"


class AuditPreparationError(RuntimeError):
    """Raised when frozen audit inputs do not satisfy the audit contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rank(question_id: str, purpose: str) -> str:
    return hashlib.sha256(f"{SEED}:{purpose}:{question_id}".encode()).hexdigest()


def build_packet(
    evaluator: dict[str, Any], checkpoint: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if evaluator.get("status") != "completed" or checkpoint.get("status") != "completed":
        raise AuditPreparationError("audit inputs must be completed runs")
    question_ids = evaluator.get("question_ids", [])
    judgments = evaluator.get("judgments", {})
    incorrect = [qid for qid in question_ids if judgments[qid]["score"] == 0]
    correct = [qid for qid in question_ids if judgments[qid]["score"] == 1]
    if len(incorrect) != 13 or len(correct) < 17:
        raise AuditPreparationError("expected frozen Claude run to contain 13 misses")
    selected = incorrect + sorted(correct, key=lambda qid: _rank(qid, "correct"))[:17]
    ordered = sorted(selected, key=lambda qid: _rank(qid, "shuffle"))

    items: list[dict[str, Any]] = []
    key_items: list[dict[str, Any]] = []
    questions = checkpoint["questions"]
    for index, question_id in enumerate(ordered, start=1):
        audit_id = f"A{index:02d}"
        question = questions[question_id]
        answer = evaluator["answers"][question_id]
        items.append(
            {
                "audit_id": audit_id,
                "question_type": question["questionType"],
                "question": question["question"],
                "reference_answer_or_rubric": question["groundTruth"],
                "candidate_answer": answer["answer"],
                "human_score": None,
                "human_notes": "",
            }
        )
        key_items.append(
            {
                "audit_id": audit_id,
                "question_id": question_id,
                "frozen_claude_judge_score": int(judgments[question_id]["score"]),
            }
        )
    packet = {
        "schema_version": 1,
        "status": "awaiting-human-scores",
        "instructions": (
            "For each item, set human_score to 1 only when the candidate satisfies "
            "the reference answer or personalization rubric; otherwise set it to 0. "
            "Do not inspect the separate key or any model-judge output before scoring."
        ),
        "items": items,
    }
    key = {
        "schema_version": 1,
        "seed": SEED,
        "sample": {
            "questions": len(items),
            "all_frozen_claude_misses": len(incorrect),
            "deterministic_frozen_claude_correct": 17,
        },
        "items": key_items,
    }
    return packet, key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    evaluator = json.loads(args.evaluator.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    packet, key = build_packet(evaluator, checkpoint)
    key["source_sha256"] = {
        "evaluator": _sha256(args.evaluator),
        "checkpoint": _sha256(args.checkpoint),
    }
    for path, value in ((args.packet, packet), (args.key, key)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(f"prepared {len(packet['items'])} blind audit items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
