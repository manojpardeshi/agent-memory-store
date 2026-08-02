from __future__ import annotations

import copy

import pytest

from scripts.analyze_kimi_answer_audit import (
    AnswerAuditAnalysisError,
    build_evidence,
)


def _inputs() -> tuple[dict, dict, dict, dict]:
    question_ids = [f"q{index:02d}" for index in range(20)]
    scores = [1] * 17 + [0] * 3
    packet_items = []
    key_items = []
    answers = {}
    for index, (question_id, score) in enumerate(
        zip(question_ids, scores, strict=True), start=1
    ):
        audit_id = f"K{index:02d}"
        answer = f"answer-{question_id}"
        packet_items.append(
            {
                "audit_id": audit_id,
                "candidate_answer_model": "kimi-k3",
                "candidate_answer": answer,
                "question_type": "temporal-reasoning",
                "human_score": score,
            }
        )
        key_items.append({"audit_id": audit_id, "question_id": question_id})
        answers[question_id] = {
            "0": {
                "answer": answer,
                "question_type": "temporal-reasoning",
            }
        }
    packet = {
        "status": "human-scored",
        "candidate_answer_model": "kimi-k3",
        "answer_repeat": 0,
        "items": packet_items,
    }
    key = {
        "candidate_answer_model": "kimi-k3",
        "answer_repeat": 0,
        "items": key_items,
    }
    kimi = {
        "status": "completed",
        "model": "kimi-k3",
        "question_ids": question_ids,
        "answers": answers,
    }
    gates = {
        "status": "frozen-before-human-answer-audit",
        "candidate_answer_model": "kimi-k3",
        "answer_repeat": 0,
        "unique_questions": 20,
        "minimum_human_correct": 14,
        "minimum_human_accuracy": 0.7,
        "failure_policy": "do-not-use-kimi-k3-as-the-sealed-benchmark-answerer",
    }
    return packet, key, kimi, gates


def test_build_evidence_passes_17_of_20_exact_kimi_answers() -> None:
    evidence = build_evidence(*_inputs())

    assert evidence["status"] == "passed"
    assert evidence["human_correct"] == 17
    assert evidence["human_accuracy"] == 0.85
    assert evidence["provenance"]["exact_answer_matches"] == 20
    assert evidence["all_gates_passed"] is True


def test_build_evidence_rejects_answer_not_found_in_raw_kimi_run() -> None:
    packet, key, kimi, gates = _inputs()
    changed_packet = copy.deepcopy(packet)
    changed_packet["items"][0]["candidate_answer"] = "different answer"

    with pytest.raises(AnswerAuditAnalysisError, match="does not match"):
        build_evidence(changed_packet, key, kimi, gates)
