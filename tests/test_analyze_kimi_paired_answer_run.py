from __future__ import annotations

import copy
import hashlib
import json
import sys

import pytest

from scripts.analyze_kimi_paired_answer_run import (
    PairedAnalysisError,
    _canonical_sha256,
    analyze_report,
    main,
)

CATEGORIES = (
    "multi-session",
    "temporal-reasoning",
    "knowledge-update",
    "single-session-assistant",
    "single-session-preference",
    "single-session-user",
)


def _call(cost: float, **extra: object) -> dict:
    return {
        "answer": "answer",
        "duration_ms": 10,
        "usage": {
            "calculated_cost_usd": cost,
            "prompt_tokens": 10,
            "completion_tokens": 2,
        },
        **extra,
    }


def paired_inputs() -> tuple[dict, dict]:
    question_ids = [f"q{index:02d}" for index in range(60)]
    answers: dict[str, dict] = {}
    judgments: dict[str, dict] = {}
    for index, question_id in enumerate(question_ids):
        category = CATEGORIES[index // 10]
        offset = index % 10
        baseline_score = int(offset < 7)
        candidate_score = baseline_score
        if category in {"multi-session", "temporal-reasoning"} and offset == 7:
            candidate_score = 1
        answers[question_id] = {
            "baseline": _call(
                0.001,
                answer=f"baseline {question_id}",
                question_type=category,
                context_json_bytes=1000,
            ),
            "candidate": _call(
                0.001,
                answer=f"candidate {question_id}",
                question_type=category,
                context_json_bytes=900,
            ),
        }
        judgments[question_id] = {}
        for arm, score in (
            ("baseline", baseline_score),
            ("candidate", candidate_score),
        ):
            votes = [score, score, score]
            if question_id in {"q28", "q38"} and arm == "baseline":
                votes[-1] = 1 - score
            judgments[question_id][arm] = {
                str(repeat): _call(0.0001, score=vote) for repeat, vote in enumerate(votes)
            }
    report = {
        "schema_version": 1,
        "status": "completed",
        "experiment_id": "paired-v1",
        "model": "kimi-k3",
        "question_ids": question_ids,
        "arm_order": ["baseline", "candidate"],
        "answers": answers,
        "judgments": judgments,
        "summary": {"failed_answer_calls": 0, "failed_judge_calls": 0},
        "budget": {
            "max_total_usd": 5.0,
            "spent_usd": 0.156,
            "unreconciled_reservations_usd": 0.0,
        },
    }
    candidate_policy = {"policy_id": "session-diverse-v1"}
    model_protocol = {
        "exact_model": "kimi-k3",
        "answer_repeats": 1,
        "judge_repeats": 3,
    }
    frozen_budget = {
        "maximum_total_cost_usd": 5.0,
        "maximum_answer_call_cost_usd": 0.25,
        "maximum_judge_call_cost_usd": 0.05,
    }
    preflight = {
        "baseline_mean": 1000.0,
        "candidate_mean": 900.0,
        "mean_ratio": 0.9,
        "baseline_p95": 1000,
        "candidate_p95": 900,
        "p95_ratio": 0.9,
    }
    contract = {
        "status": "frozen-before-paid-run",
        "experiment_id": "paired-v1",
        "selection": {
            "questions": 60,
            "sha256": "selection",
            "development_manifest_sha256": "development",
            "validation_overlap": 0,
            "reserve_overlap": 0,
        },
        "sources": {
            "baseline_checkpoint_sha256": "baseline-source",
            "session_diverse_raw_sha256": "candidate-source",
        },
        "arms": {
            "baseline": "released-ranked-top-10",
            "candidate": "session-diverse-v1",
        },
        "candidate_policy": candidate_policy,
        "preflight_context_json_bytes": preflight,
        "model_protocol": model_protocol,
        "budget": frozen_budget,
        "automated_gates": {
            "minimum_candidate_correct": 42,
            "overall_noninferiority_maximum_correct_loss": 1,
            "target_categories": ["multi-session", "temporal-reasoning"],
            "target_combined_minimum_correct_gain": 2,
            "untargeted_combined_maximum_correct_loss": 1,
            "per_category_maximum_correct_loss": 1,
            "minimum_vote_unanimity_rate_each_arm": 0.85,
            "maximum_vote_unanimity_rate_difference": 0.10,
            "context_mean_maximum_ratio": 1.0,
            "context_p95_maximum_ratio": 1.10,
            "maximum_failed_calls": 0,
            "exact_response_model_required": True,
        },
    }
    identity = {
        "contract_sha256": "contract",
        "selection_sha256": "selection",
        "development_manifest_sha256": "development",
        "candidate_replay_sha256": "candidate-source",
        "baseline_checkpoint_sha256": ["baseline-source"],
    }
    report.update(
        {
            "arms": contract["arms"],
            "input_identity": {
                **identity,
                "combined_sha256": _canonical_sha256(identity),
            },
            "split_guard": {
                "role": "development",
                "sealed": False,
                "sealed_validation_opened": False,
                "sealed_competitor_reserve_opened": False,
            },
            "protocols": {
                "model_protocol": model_protocol,
                "budget": frozen_budget,
                "execution": {
                    "fresh_answers": True,
                    "answer_calls": 120,
                    "judge_calls": 360,
                    "question_paired_and_arm_interleaved": True,
                },
            },
            "context_metrics": preflight,
            "unreconciled_calls": [],
            "arm_order_by_question": {
                question_id: (
                    ["baseline", "candidate"]
                    if hashlib.sha256(f"paired-v1{question_id}".encode()).digest()[0] % 2 == 0
                    else ["candidate", "baseline"]
                )
                for question_id in question_ids
            },
        }
    )
    return report, contract


def test_analyze_report_applies_paired_majority_and_frozen_gates() -> None:
    report, contract = paired_inputs()

    evidence = analyze_report(report, contract)

    assert evidence["status"] == "awaiting-blind-human-audit"
    assert evidence["arms"]["baseline"]["majority_correct"] == 42
    assert evidence["arms"]["candidate"]["majority_correct"] == 44
    assert evidence["paired"]["accuracy_delta"] == pytest.approx(2 / 60)
    assert evidence["paired"]["wins"] == 2
    assert evidence["paired"]["losses"] == 0
    assert evidence["paired"]["discordant_questions"] == 2
    assert evidence["paired"]["nonunanimous_questions"] == 2
    assert len(evidence["paired"]["audit_question_ids"]) == 4
    assert evidence["arms"]["baseline"]["judge_vote_unanimity"] == pytest.approx(58 / 60)
    assert evidence["cost"]["computed_total_usd"] == pytest.approx(0.156)
    assert evidence["automated_gates_passed"] is True
    assert evidence["all_gates_passed"] is False


def test_analyze_report_rejects_missing_judge_repeat() -> None:
    report, contract = paired_inputs()
    changed = copy.deepcopy(report)
    del changed["judgments"]["q00"]["baseline"]["2"]

    with pytest.raises(PairedAnalysisError, match="three judge repeats"):
        analyze_report(changed, contract)


def test_analyze_report_fails_target_gain_gate() -> None:
    report, contract = paired_inputs()
    for repeat in report["judgments"]["q07"]["candidate"].values():
        repeat["score"] = 0

    evidence = analyze_report(report, contract)

    assert evidence["gate_results"]["target_category_combined_gain"] is False
    assert evidence["status"] == "failed"


def test_main_returns_failure_when_automated_gates_fail(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_path = tmp_path / "raw.json"
    contract_path = tmp_path / "contract.json"
    output_path = tmp_path / "evidence.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analyze_kimi_paired_answer_run.py",
            "--raw",
            str(raw_path),
            "--contract",
            str(contract_path),
            "--output",
            str(output_path),
        ],
    )
    monkeypatch.setattr(
        "scripts.analyze_kimi_paired_answer_run.build_evidence",
        lambda raw, contract: {"status": "failed", "automated_gates_passed": False},
    )

    assert main() == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "failed"
