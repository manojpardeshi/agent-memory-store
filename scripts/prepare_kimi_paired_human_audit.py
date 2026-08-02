#!/usr/bin/env python3
"""Prepare a blinded human audit for discordant or non-unanimous paired answers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

ARMS = ("baseline", "candidate")
SEED_SUFFIX = "human-audit-v1"


class PairedAuditPreparationError(RuntimeError):
    """Raised when paired evidence cannot produce a valid blind audit."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rank(experiment_id: str, value: str, purpose: str) -> str:
    return hashlib.sha256(f"{experiment_id}:{value}:{SEED_SUFFIX}:{purpose}".encode()).hexdigest()


def _majority_votes(raw: dict[str, Any], question_id: str, arm: str) -> list[int]:
    try:
        judgments = raw["judgments"][question_id][arm]
    except (KeyError, TypeError) as exc:
        raise PairedAuditPreparationError(f"missing judgments for {question_id}/{arm}") from exc
    if not isinstance(judgments, dict) or len(judgments) != 3:
        raise PairedAuditPreparationError("every answer must have three judge repeats")
    votes: list[int] = []
    for repeat in sorted(judgments, key=int):
        try:
            score = int(judgments[repeat]["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PairedAuditPreparationError("judge score is missing") from exc
        if score not in (0, 1):
            raise PairedAuditPreparationError("judge score must be zero or one")
        votes.append(score)
    return votes


def _answer_text(raw: dict[str, Any], question_id: str, arm: str) -> str:
    try:
        answer = raw["answers"][question_id][arm]["answer"]
    except (KeyError, TypeError) as exc:
        raise PairedAuditPreparationError(f"missing answer for {question_id}/{arm}") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise PairedAuditPreparationError("candidate answer must be non-empty text")
    return answer


def _flagged_questions(raw: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    question_ids = raw.get("question_ids")
    if not isinstance(question_ids, list) or not question_ids:
        raise PairedAuditPreparationError("paired run has no questions")
    reasons: dict[str, Any] = {}
    selected: list[str] = []
    for question_id in question_ids:
        votes = {arm: _majority_votes(raw, question_id, arm) for arm in ARMS}
        majorities = {arm: int(sum(votes[arm]) >= 2) for arm in ARMS}
        discordant = majorities[ARMS[0]] != majorities[ARMS[1]]
        nonunanimous_arms = [arm for arm in ARMS if len(set(votes[arm])) != 1]
        if discordant or nonunanimous_arms:
            selected.append(question_id)
            reasons[question_id] = {
                "discordant_arm_majorities": discordant,
                "nonunanimous_arms": nonunanimous_arms,
                "model_judge_votes": votes,
                "model_judge_majority": majorities,
            }
    return selected, reasons


def _checkpoint_questions(checkpoint: dict[str, Any]) -> dict[str, Any]:
    questions = checkpoint.get("questions")
    if not isinstance(questions, dict):
        raise PairedAuditPreparationError("checkpoint lacks questions")
    return questions


def build_packet(
    raw: dict[str, Any],
    checkpoint: dict[str, Any],
    contract: dict[str, Any],
    *,
    checkpoint_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if raw.get("status") != "completed" or checkpoint.get("status") != "completed":
        raise PairedAuditPreparationError("audit inputs must be completed")
    if raw.get("model") != "kimi-k3":
        raise PairedAuditPreparationError("paired run must use exact model kimi-k3")
    if raw.get("arm_order") != list(ARMS):
        raise PairedAuditPreparationError("paired run arm order is invalid")
    experiment_id = str(raw.get("experiment_id", ""))
    if not experiment_id or experiment_id != contract.get("experiment_id"):
        raise PairedAuditPreparationError("experiment id differs from frozen contract")
    expected_checkpoint_hashes = raw.get("input_identity", {}).get("baseline_checkpoint_sha256")
    if expected_checkpoint_hashes is not None:
        if checkpoint_sha256 is None:
            raise PairedAuditPreparationError("checkpoint SHA-256 is required for provenance")
        if checkpoint_sha256 not in expected_checkpoint_hashes:
            raise PairedAuditPreparationError(
                "checkpoint differs from paired-run source provenance"
            )
    selected, reasons = _flagged_questions(raw)
    human_contract = contract.get(
        "human_gates",
        contract.get("human_adjudication", contract.get("human_audit", {})),
    )
    minimum = int(
        human_contract.get(
            "minimum_audit_question_count",
            human_contract.get("minimum_unique_audit_questions", 4),
        )
    )
    questions = _checkpoint_questions(checkpoint)
    missing = set(raw["question_ids"]) - set(questions)
    if missing:
        raise PairedAuditPreparationError("checkpoint is missing paired-run questions")
    target_ids = checkpoint.get("targetQuestionIds")
    if target_ids is not None and target_ids != raw["question_ids"]:
        raise PairedAuditPreparationError("checkpoint question order differs from paired-run order")

    base_records: list[dict[str, Any]] = []
    key_records: list[dict[str, Any]] = []
    left_assignment = {
        question_id: ARMS[index % 2]
        for index, question_id in enumerate(
            sorted(
                selected,
                key=lambda value: _rank(experiment_id, value, "left-arm"),
            )
        )
    }
    for question_id in selected:
        question = questions[question_id]
        left_arm = left_assignment[question_id]
        right_arm = ARMS[1] if left_arm == ARMS[0] else ARMS[0]
        base_records.append(
            {
                "source_id": question_id,
                "question_type": question["questionType"],
                "question": question["question"],
                "reference_answer_or_rubric": question["groundTruth"],
                "left_candidate_answer": _answer_text(raw, question_id, left_arm),
                "right_candidate_answer": _answer_text(raw, question_id, right_arm),
            }
        )
        key_records.append(
            {
                "source_id": question_id,
                "question_id": question_id,
                "left_arm": left_arm,
                "right_arm": right_arm,
                "selection_reason": reasons[question_id],
                "duplicate_of_source_id": None,
            }
        )

    replicate_fraction = float(human_contract.get("replicate_fraction", 0.20))
    duplicate_count = math.ceil(len(base_records) * replicate_fraction) if base_records else 0
    duplicate_sources = sorted(
        (record["source_id"] for record in base_records),
        key=lambda source_id: _rank(experiment_id, source_id, "reliability-sample"),
    )[:duplicate_count]
    by_source = {record["source_id"]: record for record in base_records}
    key_by_source = {record["source_id"]: record for record in key_records}
    records = list(base_records)
    keys = list(key_records)
    for duplicate_index, source_id in enumerate(duplicate_sources, start=1):
        duplicate_id = f"{source_id}#duplicate-{duplicate_index}"
        duplicate = {**by_source[source_id], "source_id": duplicate_id}
        records.append(duplicate)
        keys.append(
            {
                **key_by_source[source_id],
                "source_id": duplicate_id,
                "duplicate_of_source_id": source_id,
            }
        )

    ordered_ids = sorted(
        (record["source_id"] for record in records),
        key=lambda source_id: _rank(experiment_id, source_id, "packet-order"),
    )
    records_by_id = {record["source_id"]: record for record in records}
    keys_by_id = {record["source_id"]: record for record in keys}
    packet_items: list[dict[str, Any]] = []
    key_items: list[dict[str, Any]] = []
    for index, source_id in enumerate(ordered_ids, start=1):
        audit_id = f"P{index:03d}"
        record = records_by_id[source_id]
        packet_items.append(
            {
                "audit_id": audit_id,
                "question_type": record["question_type"],
                "question": record["question"],
                "reference_answer_or_rubric": record["reference_answer_or_rubric"],
                "left_candidate_answer": record["left_candidate_answer"],
                "left_human_score": None,
                "left_human_notes": "",
                "right_candidate_answer": record["right_candidate_answer"],
                "right_human_score": None,
                "right_human_notes": "",
            }
        )
        key_items.append({"audit_id": audit_id, **keys_by_id[source_id]})

    packet = {
        "schema_version": 1,
        "status": ("awaiting-human-scores" if selected else "not-required-no-flagged-questions"),
        "candidate_answer_model": "kimi-k3",
        "blinded_arms": True,
        "instructions": (
            "Score the left and right answers independently against the reference. "
            "Set each human_score to 1 only when that answer satisfies the reference "
            "answer or personalization rubric; otherwise set it to 0. Do not infer, "
            "compare, or record a preferred arm, and do not inspect the separate key."
        ),
        "unique_questions": len(selected),
        "minimum_questions_for_conclusive_audit": minimum,
        "conclusive_sample_size_possible": len(selected) >= minimum,
        "reliability_duplicate_items": duplicate_count,
        "items": packet_items,
    }
    key = {
        "schema_version": 1,
        "seed": f"{experiment_id}:{SEED_SUFFIX}",
        "candidate_answer_model": "kimi-k3",
        "unique_questions": len(selected),
        "reliability_duplicate_items": duplicate_count,
        "selection_rule": (
            "all questions with discordant 2-of-3 arm majorities or a non-unanimous "
            "three-vote judge set in either arm"
        ),
        "items": key_items,
    }
    return packet, key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    packet, key = build_packet(
        raw,
        checkpoint,
        contract,
        checkpoint_sha256=_sha256(args.checkpoint),
    )
    key["source_sha256"] = {
        "raw": _sha256(args.raw),
        "checkpoint": _sha256(args.checkpoint),
        "contract": _sha256(args.contract),
    }
    for path, value in ((args.packet, packet), (args.key, key)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(
        f"prepared {packet['unique_questions']} unique paired questions and "
        f"{packet['reliability_duplicate_items']} reliability duplicates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
