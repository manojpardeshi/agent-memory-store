from __future__ import annotations

from scripts.prepare_kimi_paired_human_audit import build_packet
from tests.test_analyze_kimi_paired_answer_run import paired_inputs


def _checkpoint(report: dict) -> dict:
    return {
        "status": "completed",
        "questions": {
            question_id: {
                "questionType": report["answers"][question_id]["baseline"]["question_type"],
                "question": f"Question {question_id}?",
                "groundTruth": f"Rubric {question_id}",
            }
            for question_id in report["question_ids"]
        },
    }


def test_build_packet_blinds_four_flagged_questions_and_adds_duplicate() -> None:
    report, contract = paired_inputs()
    contract["human_gates"] = {"minimum_audit_question_count": 4}

    packet, key = build_packet(
        report,
        _checkpoint(report),
        contract,
        checkpoint_sha256="baseline-source",
    )

    assert packet["status"] == "awaiting-human-scores"
    assert packet["unique_questions"] == 4
    assert packet["conclusive_sample_size_possible"] is True
    assert packet["reliability_duplicate_items"] == 1
    assert len(packet["items"]) == 5
    assert len(key["items"]) == 5
    assert all("question_id" not in item for item in packet["items"])
    assert all("left_arm" not in item and "right_arm" not in item for item in packet["items"])
    assert all(item["left_human_score"] is None for item in packet["items"])
    assert all(item["right_human_score"] is None for item in packet["items"])
    assert {item["left_arm"] for item in key["items"]} == {
        "baseline",
        "candidate",
    }

    duplicate = next(item for item in key["items"] if item["duplicate_of_source_id"])
    original = next(
        item for item in key["items"] if item["source_id"] == duplicate["duplicate_of_source_id"]
    )
    packet_duplicate = next(
        item for item in packet["items"] if item["audit_id"] == duplicate["audit_id"]
    )
    packet_original = next(
        item for item in packet["items"] if item["audit_id"] == original["audit_id"]
    )
    comparable_fields = {
        key: value
        for key, value in packet_duplicate.items()
        if key not in {"audit_id", "left_human_score", "right_human_score"}
    }
    assert comparable_fields == {
        key: value
        for key, value in packet_original.items()
        if key not in {"audit_id", "left_human_score", "right_human_score"}
    }


def test_build_packet_marks_three_question_audit_inconclusive() -> None:
    report, contract = paired_inputs()
    contract["human_gates"] = {"minimum_audit_question_count": 4}
    # Remove one non-unanimous trigger without changing its majority.
    for judgment in report["judgments"]["q38"]["baseline"].values():
        judgment["score"] = 0

    packet, _ = build_packet(
        report,
        _checkpoint(report),
        contract,
        checkpoint_sha256="baseline-source",
    )

    assert packet["unique_questions"] == 3
    assert packet["conclusive_sample_size_possible"] is False
