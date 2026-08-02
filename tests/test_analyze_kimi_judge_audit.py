from __future__ import annotations

from scripts.analyze_kimi_judge_audit import build_evidence


def test_build_evidence_applies_all_frozen_gates() -> None:
    audit_ids = [f"A{index:02d}" for index in range(1, 31)]
    human_scores = [0] * 13 + [1] * 17
    packet = {
        "status": "human-scored",
        "items": [
            {"audit_id": audit_id, "human_score": score}
            for audit_id, score in zip(audit_ids, human_scores, strict=True)
        ],
    }
    key = {
        "items": [
            {"audit_id": audit_id, "frozen_claude_judge_score": score}
            for audit_id, score in zip(audit_ids, human_scores, strict=True)
        ]
    }
    kimi = {
        "status": "completed",
        "model": "kimi-k3",
        "audit_ids": audit_ids,
        "judge_repeats": 3,
        "budget": {"spent_usd": 0.3},
        "judgments": {
            audit_id: {
                "0": {"score": score},
                "1": {"score": score},
                "2": {"score": score},
            }
            for audit_id, score in zip(audit_ids, human_scores, strict=True)
        },
    }
    gate_contract = {
        "status": "frozen-before-kimi-audit-judgments",
        "gates": {
            "minimum_overall_agreement": 27,
            "minimum_human_positive_agreement": 15,
            "minimum_human_negative_agreement": 11,
            "maximum_absolute_positive_count_drift": 3,
            "minimum_unanimous_three_vote_items": 27,
        },
    }

    result = build_evidence(packet, key, kimi, gate_contract)

    assert result["status"] == "passed"
    assert result["all_gates_passed"] is True
    assert result["kimi_vs_human"]["overall_agreement"] == 30
