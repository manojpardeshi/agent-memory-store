from __future__ import annotations

import copy

import pytest

from scripts.run_kimi_judge_audit import (
    JudgeAuditError,
    build_audit_judge_prompt,
    validate_packet,
)


def _packet() -> dict[str, object]:
    return {
        "status": "human-scored",
        "items": [
            {
                "audit_id": f"A{index:02d}",
                "question": f"question {index}",
                "reference_answer_or_rubric": f"truth {index}",
                "candidate_answer": f"answer {index}",
                "question_type": "multi-session",
                "human_score": index % 2,
                "human_notes": "private note",
            }
            for index in range(1, 31)
        ],
    }


def test_packet_validation_and_prompt_exclude_human_fields() -> None:
    packet = _packet()
    items = validate_packet(packet)

    prompt = build_audit_judge_prompt(items[0])

    assert "human_score" not in prompt
    assert "private note" not in prompt
    assert "question 1" in prompt


def test_packet_rejects_missing_score() -> None:
    packet = copy.deepcopy(_packet())
    packet["items"][0]["human_score"] = None

    with pytest.raises(JudgeAuditError, match="invalid human score"):
        validate_packet(packet)


def test_packet_accepts_numeric_reference_answer() -> None:
    packet = _packet()
    packet["items"][0]["reference_answer_or_rubric"] = 4

    items = validate_packet(packet)

    assert "Ground Truth Answer: 4" in build_audit_judge_prompt(items[0])
