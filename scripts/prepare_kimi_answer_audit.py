#!/usr/bin/env python3
"""Prepare a blind human audit packet from frozen Kimi-generated answers."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class AnswerAuditPreparationError(RuntimeError):
    """Raised when frozen Kimi answer evidence cannot produce the audit packet."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_packet(
    kimi: dict[str, Any], checkpoint: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if kimi.get("status") != "completed" or checkpoint.get("status") != "completed":
        raise AnswerAuditPreparationError("audit inputs must be completed runs")
    if kimi.get("model") != "kimi-k3":
        raise AnswerAuditPreparationError("answer source must use exact model kimi-k3")
    question_ids = kimi.get("question_ids")
    if not isinstance(question_ids, list) or len(question_ids) != 20:
        raise AnswerAuditPreparationError("expected 20 frozen Kimi qualification questions")
    questions = checkpoint.get("questions", {})
    items: list[dict[str, Any]] = []
    key_items: list[dict[str, str]] = []
    for index, question_id in enumerate(question_ids, start=1):
        audit_id = f"K{index:02d}"
        try:
            answer = kimi["answers"][question_id]["0"]["answer"]
            question = questions[question_id]
        except (KeyError, TypeError) as error:
            raise AnswerAuditPreparationError(
                f"missing frozen Kimi answer or question for {question_id}"
            ) from error
        items.append(
            {
                "audit_id": audit_id,
                "candidate_answer_model": "kimi-k3",
                "question_type": question["questionType"],
                "question": question["question"],
                "reference_answer_or_rubric": question["groundTruth"],
                "candidate_answer": answer,
                "human_score": None,
                "human_notes": "",
            }
        )
        key_items.append({"audit_id": audit_id, "question_id": question_id})
    packet = {
        "schema_version": 1,
        "status": "awaiting-human-scores",
        "candidate_answer_model": "kimi-k3",
        "answer_repeat": 0,
        "instructions": (
            "Set human_score to 1 only when the Kimi candidate answer satisfies the "
            "reference answer or personalization rubric; otherwise set it to 0."
        ),
        "items": items,
    }
    key = {
        "schema_version": 1,
        "candidate_answer_model": "kimi-k3",
        "answer_repeat": 0,
        "items": key_items,
    }
    return packet, key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kimi", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    kimi = json.loads(args.kimi.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    packet, key = build_packet(kimi, checkpoint)
    key["source_sha256"] = {
        "kimi": _sha256(args.kimi),
        "checkpoint": _sha256(args.checkpoint),
    }
    for path, value in ((args.packet, packet), (args.key, key)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print("prepared 20 frozen Kimi answer-audit items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
