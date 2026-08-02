from __future__ import annotations

import json

import pytest

from scripts.run_memorybench_claude_pilot import (
    PilotError,
    build_answer_prompt,
    build_judge_prompt,
    load_selection,
    parse_judge_response,
)


def test_answer_prompt_matches_memorybench_shape() -> None:
    prompt = build_answer_prompt(
        "What is the synthetic code?",
        [{"memory": "The code is cobalt-731.", "score": 0.9}],
    )

    assert "Question: What is the synthetic code?" in prompt
    assert "Question Date: Not specified" in prompt
    assert json.dumps(
        [{"memory": "The code is cobalt-731.", "score": 0.9}],
        indent=2,
    ) in prompt
    assert prompt.endswith("Answer:")


def test_judge_prompt_uses_preference_rubric_label() -> None:
    prompt = build_judge_prompt(
        "What should I bake?",
        "Use the remembered lemon preference.",
        "Bake a lemon cake.",
        "single-session-preference",
    )

    assert "Rubric: Use the remembered lemon preference." in prompt
    assert "Ground Truth Answer:" not in prompt


def test_parse_judge_response_is_strict() -> None:
    result = parse_judge_response(
        'Prefix {"score": 1, "label": "correct", "explanation": "Equivalent."}'
    )
    assert result == {
        "score": 1,
        "label": "correct",
        "explanation": "Equivalent.",
    }

    with pytest.raises(PilotError, match="disagree"):
        parse_judge_response(
            '{"score": 0, "label": "correct", "explanation": "Inconsistent."}'
        )

    with pytest.raises(PilotError, match="did not contain"):
        parse_judge_response("correct")


def test_load_selection_validates_unique_question_ids(tmp_path) -> None:
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"question_ids": ["question-a", "question-b"]}),
        encoding="utf-8",
    )
    question_ids, digest = load_selection(selection)
    assert question_ids == ("question-a", "question-b")
    assert isinstance(digest, str) and len(digest) == 64

    selection.write_text(
        json.dumps({"question_ids": ["question-a", "question-a"]}),
        encoding="utf-8",
    )
    with pytest.raises(PilotError, match="unique"):
        load_selection(selection)
