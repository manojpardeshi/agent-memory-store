from __future__ import annotations

from scripts.analyze_kimi_qualification import analyze_report


def _record(score: int | None = None) -> dict[str, object]:
    record: dict[str, object] = {
        "duration_ms": 10,
        "usage": {
            "calculated_cost_usd": 0.01,
            "prompt_tokens": 10,
            "cached_input_tokens": 2,
            "uncached_input_tokens": 8,
            "completion_tokens": 3,
            "reasoning_tokens": 1,
        },
    }
    if score is not None:
        record["score"] = score
    return record


def test_analyze_report_computes_nested_repeat_stability() -> None:
    answers = {
        answer_key: {**_record(), "question_type": "multi-session"}
        for answer_key in ("0", "1", "2")
    }
    report = {
        "status": "completed",
        "model": "kimi-k3",
        "question_ids": ["q1"],
        "context_protocol": {"mode": "retrieved"},
        "answers": {"q1": answers},
        "judgments": {
            "q1": {
                "0": {"0": _record(1), "1": _record(1), "2": _record(1)},
                "1": {"0": _record(1), "1": _record(1), "2": _record(0)},
                "2": {"0": _record(1), "1": _record(1), "2": _record(1)},
            }
        },
        "budget": {"spent_usd": 0.12},
    }

    result = analyze_report(report)

    assert result["majority_accuracy"] == 1.0
    assert result["judge_vote_unanimity"] == 2 / 3
    assert result["stable_question_rate"] == 1.0
    assert result["answer_repeat_pairwise_agreement"] == 1.0
    assert result["answer_calls"]["calls"] == 3
    assert result["judge_calls"]["calls"] == 9
