from __future__ import annotations

import pytest

from scripts.analyze_longmemeval_retrieval import analyze_retrieval, merge_checkpoints


def _result(question_id: str, session_index: int) -> dict[str, object]:
    return {"metadata": {"session_id": f"{question_id}-session-{session_index}"}}


def test_analyze_retrieval_uses_distinct_answer_sessions_for_recall() -> None:
    question_id = "question-a"
    dataset = [
        {
            "question_id": question_id,
            "question_type": "multi-session",
            "answer_session_ids": ["answer-1", "answer-2"],
            "haystack_session_ids": ["other", "answer-1", "answer-2"],
        }
    ]
    retrieved = [1, 1, 0, 0, 0, 2, 2, 0, 0, 0]
    checkpoint = {
        "targetQuestionIds": [question_id],
        "questions": {
            question_id: {
                "phases": {
                    "search": {
                        "results": [_result(question_id, index) for index in retrieved],
                    }
                }
            }
        },
    }

    result = analyze_retrieval(dataset, checkpoint)
    question = result["questions"][0]

    assert question["answer_session_recall_at_5"] == 0.5
    assert question["answer_session_recall_at_10"] == 1.0
    assert question["result_precision_at_10"] == 0.4
    assert result["overall"]["hit_at_5"] == 1.0
    assert result["overall"]["mrr_at_10"] == 1.0


def test_analyze_retrieval_rejects_unmatched_answer_session() -> None:
    dataset = [
        {
            "question_id": "question-a",
            "question_type": "single-session-user",
            "answer_session_ids": ["missing"],
            "haystack_session_ids": ["other"],
        }
    ]
    checkpoint = {
        "targetQuestionIds": ["question-a"],
        "questions": {"question-a": {"phases": {"search": {"results": []}}}},
    }

    with pytest.raises(ValueError, match="unmatched"):
        analyze_retrieval(dataset, checkpoint)


def test_merge_checkpoints_requires_disjoint_completed_questions() -> None:
    first = {
        "status": "completed",
        "targetQuestionIds": ["q1"],
        "questions": {"q1": {"value": 1}},
    }
    second = {
        "status": "completed",
        "targetQuestionIds": ["q2"],
        "questions": {"q2": {"value": 2}},
    }

    merged = merge_checkpoints([first, second])

    assert merged["targetQuestionIds"] == ["q1", "q2"]
    with pytest.raises(ValueError, match="duplicate question"):
        merge_checkpoints([first, first])
