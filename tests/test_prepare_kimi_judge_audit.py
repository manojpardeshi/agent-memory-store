from __future__ import annotations

from scripts.prepare_kimi_judge_audit import build_packet


def test_packet_hides_model_scores_and_includes_all_misses() -> None:
    question_ids = [f"q{index:02d}" for index in range(30)]
    evaluator = {
        "status": "completed",
        "question_ids": question_ids,
        "answers": {
            qid: {"answer": f"answer-{qid}"} for qid in question_ids
        },
        "judgments": {
            qid: {"score": int(index >= 13)}
            for index, qid in enumerate(question_ids)
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

    packet, key = build_packet(evaluator, checkpoint)

    assert len(packet["items"]) == 30
    assert all("question_id" not in item for item in packet["items"])
    assert all("frozen_claude_judge_score" not in item for item in packet["items"])
    assert sum(item["frozen_claude_judge_score"] == 0 for item in key["items"]) == 13
