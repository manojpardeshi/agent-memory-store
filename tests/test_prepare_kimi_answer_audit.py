from __future__ import annotations

from scripts.prepare_kimi_answer_audit import build_packet


def test_packet_contains_only_frozen_kimi_first_answers() -> None:
    question_ids = [f"q{index:02d}" for index in range(20)]
    kimi = {
        "status": "completed",
        "model": "kimi-k3",
        "question_ids": question_ids,
        "answers": {
            qid: {
                "0": {"answer": f"first-{qid}"},
                "1": {"answer": f"second-{qid}"},
            }
            for qid in question_ids
        },
    }
    checkpoint = {
        "status": "completed",
        "questions": {
            qid: {
                "question": f"question-{qid}",
                "groundTruth": f"truth-{qid}",
                "questionType": "multi-session",
            }
            for qid in question_ids
        },
    }

    packet, key = build_packet(kimi, checkpoint)

    assert len(packet["items"]) == 20
    assert packet["candidate_answer_model"] == "kimi-k3"
    assert all(item["candidate_answer"].startswith("first-") for item in packet["items"])
    assert all(item["human_score"] is None for item in packet["items"])
    assert len(key["items"]) == 20
