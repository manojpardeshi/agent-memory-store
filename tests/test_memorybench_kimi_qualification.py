from __future__ import annotations

import json

import pytest

from scripts.run_memorybench_kimi_qualification import (
    QualificationError,
    build_kimi_request,
    run_qualification,
    worst_case_cost_usd,
)


def test_answer_request_freezes_exact_model_and_effort() -> None:
    body = build_kimi_request(
        "Question",
        system_prompt="System",
        reasoning_effort="high",
        max_completion_tokens=4096,
        judge=False,
    )
    payload = json.loads(body)

    assert payload["model"] == "kimi-k3"
    assert payload["reasoning_effort"] == "high"
    assert payload["max_completion_tokens"] == 4096
    assert "response_format" not in payload


def test_judge_request_uses_strict_schema() -> None:
    body = build_kimi_request(
        "Judge",
        system_prompt="System",
        reasoning_effort="low",
        max_completion_tokens=1024,
        judge=True,
    )
    payload = json.loads(body)

    schema = payload["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False


def test_worst_case_cost_bounds_uncached_input_and_output() -> None:
    body = b"x" * 1_000

    assert worst_case_cost_usd(body, 100) == pytest.approx(0.007572)


def test_unknown_context_mode_fails_before_loading_source(tmp_path) -> None:
    with pytest.raises(QualificationError, match="unsupported context mode"):
        run_qualification(
            root=tmp_path,
            run_id="unused",
            output=tmp_path / "unused.json",
            api_key="unused",
            question_ids=("unused",),
            selection_sha256=None,
            answer_repeats=1,
            judge_repeats=1,
            max_call_usd=0.5,
            max_total_usd=1.0,
            timeout_seconds=1,
            context_mode="ground-truth",
        )
