from __future__ import annotations

from scripts.analyze_session_diverse_development import evaluate_gates


def test_evaluate_gates_requires_target_improvement_and_all_guardrails() -> None:
    baseline = {
        "overall": {"answer_session_recall_at_10": 0.928, "mrr_at_10": 0.897},
        "categories": {
            "multi-session": {"answer_session_recall_at_10": 0.893},
            "temporal-reasoning": {"answer_session_recall_at_10": 0.835},
            "single-session-user": {"answer_session_recall_at_10": 1.0},
        },
    }
    candidate = {
        "overall": {"answer_session_recall_at_10": 0.957, "mrr_at_10": 0.903},
        "categories": {
            "multi-session": {"answer_session_recall_at_10": 0.93},
            "temporal-reasoning": {"answer_session_recall_at_10": 0.907},
            "single-session-user": {"answer_session_recall_at_10": 1.0},
        },
    }
    operational = {
        "context_json_bytes": {"mean_ratio": 0.9, "p95_ratio": 0.9},
        "selection_latency_ms": {"p50": 0.1, "p95": 0.2},
        "search_latency_ms": {"p95": 30},
        "questions_with_recall_loss": 0,
        "questions_with_result_count_change": 0,
        "questions_with_ranked_prefix_mismatch": 0,
        "distinct_sessions": {"mean_gain": 2.0},
    }
    gates = {
        "multi_session_recall_minimum": 0.913,
        "temporal_reasoning_recall_minimum": 0.855,
        "overall_recall_minimum": 0.923,
        "overall_mrr_minimum": 0.892,
        "context_json_bytes_mean_maximum_ratio": 1.05,
        "context_json_bytes_p95_maximum_ratio": 1.1,
        "selection_latency_ms_p50_maximum": 5,
        "selection_latency_ms_p95_maximum": 15,
        "search_latency_ms_p95_maximum": 225,
        "maximum_category_recall_drop": 0.01,
        "maximum_questions_with_recall_loss": 3,
        "minimum_distinct_sessions_mean_gain": 1.0,
    }

    assert all(evaluate_gates(baseline, candidate, operational, gates).values())

    candidate["categories"]["multi-session"]["answer_session_recall_at_10"] = 0.89
    candidate["categories"]["temporal-reasoning"]["answer_session_recall_at_10"] = 0.84
    assert (
        evaluate_gates(baseline, candidate, operational, gates)[
            "target_category_improvement"
        ]
        is False
    )
