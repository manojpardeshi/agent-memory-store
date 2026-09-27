from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts import run_memorybench_kimi_paired_development as paired


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_files(tmp_path: Path) -> dict[str, Path]:
    question_ids = [f"q{index:03d}" for index in range(180)]
    selected = question_ids[:60]
    categories = [
        "single-session-preference",
        "single-session-user",
        "multi-session",
        "temporal-reasoning",
        "knowledge-update",
        "single-session-assistant",
    ]
    selection = {
        "question_ids": selected,
        "question_type_counts": {category: 10 for category in categories},
    }
    selection_path = tmp_path / "selection.json"
    _write(selection_path, selection)

    development = {
        "role": "development",
        "sealed": False,
        "question_count": 180,
        "observed_selection_sha256": _sha256(selection_path),
        "question_ids": question_ids,
    }
    development_path = tmp_path / "development.json"
    _write(development_path, development)

    baseline_questions: dict[str, Any] = {}
    candidate_questions: dict[str, Any] = {}
    for index, question_id in enumerate(question_ids):
        question_type = categories[(index // 10) % len(categories)]
        baseline_results = [{"memory_id": f"base-{question_id}", "content": "base context"}]
        candidate_results = [
            {"memory_id": f"candidate-{question_id}", "content": "candidate context"}
        ]
        candidate_questions[question_id] = {
            "question_type": question_type,
            "results": candidate_results,
            "context_json_bytes": paired._context_json_bytes(candidate_results),
            "diagnostics": {
                "ranked_pool_top_10_memory_ids": [f"base-{question_id}"]
            },
        }
        if question_id in selected:
            baseline_questions[question_id] = {
                "question": f"Question {question_id}?",
                "questionType": question_type,
                "groundTruth": "answer",
                "phases": {"search": {"results": baseline_results}},
            }
    baseline = {
        "status": "completed",
        "targetQuestionIds": selected,
        "questions": baseline_questions,
    }
    baseline_path = tmp_path / "baseline.json"
    _write(baseline_path, baseline)

    policy = {
        "policy_id": "session-diverse-v1",
        "ranked_candidate_pool": 50,
        "output_slots": 10,
    }
    retrieval_gate_sha256 = "a" * 64
    candidate = {
        "status": "completed",
        "manifest_sha256": _sha256(development_path),
        "question_ids": question_ids,
        "source_checkpoint_sha256": [_sha256(baseline_path)],
        "gate_sha256": retrieval_gate_sha256,
        "context_policy": policy,
        "questions": candidate_questions,
    }
    candidate_path = tmp_path / "candidate.json"
    _write(candidate_path, candidate)

    script_dir = Path(paired.__file__).resolve().parent
    contract = {
        "status": "frozen-before-paid-run",
        "experiment_id": paired.EXPERIMENT_ID,
        "selection": {
            "sha256": _sha256(selection_path),
            "development_manifest_sha256": _sha256(development_path),
            "questions": 60,
        },
        "sources": {
            "baseline_checkpoint_sha256": _sha256(baseline_path),
            "session_diverse_raw_sha256": _sha256(candidate_path),
            "session_diverse_retrieval_gates_sha256": retrieval_gate_sha256,
        },
        "arms": {
            "baseline": "released-ranked-top-10",
            "candidate": "session-diverse-v1",
        },
        "candidate_policy": policy,
        "preflight_context_json_bytes": {
            "baseline_mean": 1.0,
            "candidate_mean": 1.0,
        },
        "model_protocol": {
            "exact_model": "kimi-k3",
            "answer_repeats": 1,
            "judge_repeats": 3,
            "answer_reasoning_effort": paired.ANSWER_EFFORT,
            "answer_max_completion_tokens": paired.ANSWER_MAX_COMPLETION_TOKENS,
            "answer_system_prompt_sha256": paired._sha256_text(
                paired.ANSWER_SYSTEM_PROMPT
            ),
            "judge_reasoning_effort": paired.JUDGE_EFFORT,
            "judge_max_completion_tokens": paired.JUDGE_MAX_COMPLETION_TOKENS,
            "judge_system_prompt_sha256": paired._sha256_text(
                paired.JUDGE_SYSTEM_PROMPT
            ),
            "prompt_builder_source_sha256": _sha256(
                script_dir / "run_memorybench_claude_pilot.py"
            ),
            "request_builder_source_sha256": _sha256(
                script_dir / "run_memorybench_kimi_qualification.py"
            ),
            "arm_order": "sha256-experiment-id-and-question-id",
        },
        "budget": {
            "maximum_total_cost_usd": 5.0,
            "maximum_answer_call_cost_usd": 0.25,
            "maximum_judge_call_cost_usd": 0.05,
            "single_shared_ledger": True,
            "pre_call_worst_case_reservation_required": True,
        },
    }
    contract_path = tmp_path / "contract.json"
    _write(contract_path, contract)
    return {
        "selection": selection_path,
        "development": development_path,
        "baseline": baseline_path,
        "candidate": candidate_path,
        "contract": contract_path,
        "output": tmp_path / "output.json",
    }


def test_arm_order_is_balanced_and_bound_to_experiment_id() -> None:
    orders = [paired.arm_order_for_question(f"q{index}") for index in range(100)]

    assert set(orders) == {
        ("baseline", "candidate"),
        ("candidate", "baseline"),
    }
    expected_first = (
        paired.ARMS
        if hashlib.sha256(f"{paired.EXPERIMENT_ID}q0".encode()).digest()[0] % 2 == 0
        else tuple(reversed(paired.ARMS))
    )
    assert orders[0] == expected_first


def test_keychain_key_is_stripped_and_never_taken_from_environment(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.append(command)
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(command, 0, stdout="secret-key\n", stderr="")

    monkeypatch.setattr(paired.subprocess, "run", fake_run)

    assert paired.load_api_key(
        keychain_service="agent-memory-store-kimi-api",
        environment={"MOONSHOT_API_KEY": "wrong"},
    ) == "secret-key"
    assert captured == [
        [
            "security",
            "find-generic-password",
            "-s",
            "agent-memory-store-kimi-api",
            "-w",
        ]
    ]


def test_missing_api_key_is_rejected() -> None:
    with pytest.raises(paired.PairedDevelopmentError, match="MOONSHOT_API_KEY"):
        paired.load_api_key(keychain_service=None, environment={})


def test_full_interleaved_run_is_resumable_and_blind(tmp_path, monkeypatch) -> None:
    paths = _fixture_files(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_call(
        api_key: str,
        body: bytes,
        *,
        max_completion_tokens: int,
        max_call_usd: float,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        assert api_key == "secret"
        payload = json.loads(body)
        prompt = payload["messages"][1]["content"]
        assert "released-ranked-top-10" not in prompt
        assert "session-diverse-v1" not in prompt
        judge = "response_format" in payload
        calls.append(
            {
                "judge": judge,
                "max_call_usd": max_call_usd,
                "max_completion_tokens": max_completion_tokens,
                "timeout_seconds": timeout_seconds,
            }
        )
        result = (
            '{"score":1,"label":"correct","explanation":"matches"}'
            if judge
            else "answer"
        )
        return {
            "result": result,
            "duration_ms": 1,
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "usage": {
                "calculated_cost_usd": 0.001,
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "reasoning_tokens": 0,
            },
        }

    monkeypatch.setattr(paired, "run_kimi_call", fake_call)
    kwargs = {
        "selection_path": paths["selection"],
        "development_manifest_path": paths["development"],
        "contract_path": paths["contract"],
        "baseline_checkpoint_paths": [paths["baseline"]],
        "candidate_path": paths["candidate"],
        "output": paths["output"],
        "api_key": "secret",
        "timeout_seconds": 9,
    }

    report = paired.run_paired_development(**kwargs)

    assert report["status"] == "completed"
    assert report["model"] == "kimi-k3"
    assert report["arms"] == {
        "baseline": "released-ranked-top-10",
        "candidate": "session-diverse-v1",
    }
    assert report["summary"]["answers_completed"] == 120
    assert report["summary"]["judge_calls_completed"] == 360
    assert report["budget"]["spent_usd"] == pytest.approx(0.48)
    assert len(calls) == 480
    assert sum(not call["judge"] for call in calls) == 120
    assert sum(call["judge"] for call in calls) == 360
    assert {call["max_call_usd"] for call in calls if not call["judge"]} == {0.25}
    assert {call["max_call_usd"] for call in calls if call["judge"]} == {0.05}
    assert report["input_identity"]["contract_sha256"] == _sha256(paths["contract"])
    assert report["split_guard"]["sealed_validation_opened"] is False
    assert report["split_guard"]["sealed_competitor_reserve_opened"] is False

    calls.clear()
    resumed = paired.run_paired_development(**kwargs)
    assert resumed["status"] == "completed"
    assert calls == []


def test_resume_rejects_output_identity_tampering(tmp_path, monkeypatch) -> None:
    paths = _fixture_files(tmp_path)
    selection = json.loads(paths["selection"].read_text(encoding="utf-8"))
    contract = json.loads(paths["contract"].read_text(encoding="utf-8"))
    identity = paired._input_identity(
        selection_sha256=_sha256(paths["selection"]),
        development_sha256=_sha256(paths["development"]),
        candidate_sha256=_sha256(paths["candidate"]),
        baseline_sha256=[_sha256(paths["baseline"])],
        contract_sha256=_sha256(paths["contract"]),
    )
    report = paired._new_report(
        question_ids=tuple(selection["question_ids"]),
        identity=identity,
        contract=contract,
    )
    report["model"] = "another-model"
    _write(paths["output"], report)
    monkeypatch.setattr(
        paired,
        "run_kimi_call",
        lambda *args, **kwargs: pytest.fail("must fail before an API call"),
    )

    with pytest.raises(paired.PairedDevelopmentError, match="model"):
        paired.run_paired_development(
            selection_path=paths["selection"],
            development_manifest_path=paths["development"],
            contract_path=paths["contract"],
            baseline_checkpoint_paths=[paths["baseline"]],
            candidate_path=paths["candidate"],
            output=paths["output"],
            api_key="secret",
            timeout_seconds=9,
        )


def test_known_http_429_recovery_records_one_no_charge_identical_retry(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"
    report = {
        "in_flight": {
            "slot": "judge:q001:baseline:0",
            "request_sha256": "a" * 64,
            "reserved_usd": 0.05,
        },
        "retry_events": [],
    }
    _write(output, report)

    paired._recover_known_http_429(report, output)

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["in_flight"] is None
    assert saved["retry_events"] == [
        {
            "slot": "judge:q001:baseline:0",
            "request_sha256": "a" * 64,
            "reason": "HTTP 429 before a response or usage record",
            "charged_usd": 0.0,
            "identical_request_reissue": True,
            "recorded_at": saved["retry_events"][0]["recorded_at"],
        }
    ]
    with pytest.raises(paired.PairedDevelopmentError, match="only one"):
        report["in_flight"] = {
            "slot": "judge:q002:baseline:0",
            "request_sha256": "b" * 64,
            "reserved_usd": 0.05,
        }
        paired._recover_known_http_429(report, output)


def _prompt_recording_call(prompts: list[str]):
    def fake_call(api_key, body, *, max_completion_tokens, max_call_usd, timeout_seconds):
        payload = json.loads(body)
        judge = "response_format" in payload
        if not judge:
            prompts.append(payload["messages"][1]["content"])
        result = '{"score":1,"label":"correct","explanation":"matches"}' if judge else "answer"
        return {
            "result": result,
            "duration_ms": 1,
            "request_sha256": hashlib.sha256(body).hexdigest(),
            "usage": {
                "calculated_cost_usd": 0.001,
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "reasoning_tokens": 0,
            },
        }

    return fake_call


def _paired_kwargs(paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "selection_path": paths["selection"],
        "development_manifest_path": paths["development"],
        "contract_path": paths["contract"],
        "baseline_checkpoint_paths": [paths["baseline"]],
        "candidate_path": paths["candidate"],
        "output": paths["output"],
        "api_key": "secret",
        "timeout_seconds": 9,
    }


def test_without_dataset_prompts_reproduce_recorded_behaviour(tmp_path, monkeypatch) -> None:
    """Omitting --dataset must keep recorded paired evidence reproducible."""
    paths = _fixture_files(tmp_path)
    prompts: list[str] = []
    monkeypatch.setattr(paired, "run_kimi_call", _prompt_recording_call(prompts))
    report = paired.run_paired_development(**_paired_kwargs(paths))
    assert report["question_dates_supplied"] is False
    assert prompts and all("Question Date: Not specified" in p for p in prompts)


def test_with_dataset_prompts_carry_the_question_date(tmp_path, monkeypatch) -> None:
    paths = _fixture_files(tmp_path)
    ids = json.loads(paths["selection"].read_text(encoding="utf-8"))["question_ids"]
    dates = {qid: "2023/05/30 (Tue) 23:40" for qid in ids}
    prompts: list[str] = []
    monkeypatch.setattr(paired, "run_kimi_call", _prompt_recording_call(prompts))
    report = paired.run_paired_development(**_paired_kwargs(paths), question_dates=dates)
    assert report["question_dates_supplied"] is True
    assert prompts and all("2023/05/30 (Tue) 23:40" in p for p in prompts)
    assert not any("Not specified" in p for p in prompts)

    prompts.clear()
    resumed = paired.run_paired_development(**_paired_kwargs(paths), question_dates=dates)
    assert resumed["status"] == "completed"
    assert prompts == []


def test_resume_refuses_to_mix_dated_and_undated_prompts(tmp_path, monkeypatch) -> None:
    paths = _fixture_files(tmp_path)
    ids = json.loads(paths["selection"].read_text(encoding="utf-8"))["question_ids"]
    monkeypatch.setattr(paired, "run_kimi_call", _prompt_recording_call([]))
    paired.run_paired_development(**_paired_kwargs(paths))
    with pytest.raises(paired.PairedDevelopmentError, match="mix prompts"):
        paired.run_paired_development(
            **_paired_kwargs(paths), question_dates={qid: "2023/05/30" for qid in ids}
        )
