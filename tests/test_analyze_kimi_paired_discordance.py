from __future__ import annotations

import copy

import pytest

from scripts.analyze_kimi_paired_discordance import (
    DiscordanceAnalysisError,
    build_evidence,
    render_markdown,
)


def _result(memory_id: str, session_id: str) -> dict:
    return {"memory_id": memory_id, "metadata": {"session_id": session_id}}


def _votes(score: int) -> dict:
    return {str(index): {"score": score} for index in range(3)}


def _inputs() -> tuple[dict, dict, dict, list[dict], dict]:
    question_ids = ["q0", "q1", "q2"]
    raw = {
        "question_ids": question_ids,
        "answers": {
            "q0": {
                "baseline": {"context_json_bytes": 100},
                "candidate": {"context_json_bytes": 80},
            },
            "q1": {
                "baseline": {"context_json_bytes": 100},
                "candidate": {"context_json_bytes": 90},
            },
            "q2": {
                "baseline": {"context_json_bytes": 100},
                "candidate": {"context_json_bytes": 100},
            },
        },
        "judgments": {
            "q0": {"baseline": _votes(1), "candidate": _votes(0)},
            "q1": {"baseline": _votes(0), "candidate": _votes(1)},
            "q2": {"baseline": _votes(1), "candidate": _votes(1)},
        },
    }
    baseline_results = {
        "q0": [
            _result("q0-a", "q0-session-0"),
            _result("q0-b", "q0-session-0"),
            _result("q0-c", "q0-session-0"),
        ],
        "q1": [
            _result("q1-a", "q1-session-0"),
            _result("q1-u1", "q1-session-1"),
            _result("q1-u2", "q1-session-2"),
        ],
        "q2": [_result("q2-a", "q2-session-0")],
    }
    candidate_results = {
        "q0": [
            _result("q0-a", "q0-session-0"),
            _result("q0-u1", "q0-session-1"),
            _result("q0-u2", "q0-session-2"),
        ],
        "q1": [
            _result("q1-a", "q1-session-0"),
            _result("q1-b", "q1-session-0"),
            _result("q1-u2", "q1-session-2"),
        ],
        "q2": [_result("q2-a", "q2-session-0")],
    }
    baseline = {
        "targetQuestionIds": question_ids,
        "questions": {
            question_id: {"phases": {"search": {"results": baseline_results[question_id]}}}
            for question_id in question_ids
        },
    }
    candidate = {
        "questions": {
            question_id: {"results": candidate_results[question_id]} for question_id in question_ids
        }
    }
    dataset = [
        {
            "question_id": "q0",
            "question_type": "single-session-user",
            "haystack_session_ids": ["source-q0"],
            "answer_session_ids": ["source-q0"],
        },
        {
            "question_id": "q1",
            "question_type": "multi-session",
            "haystack_session_ids": ["source-q1"],
            "answer_session_ids": ["source-q1"],
        },
        {
            "question_id": "q2",
            "question_type": "knowledge-update",
            "haystack_session_ids": ["source-q2"],
            "answer_session_ids": ["source-q2"],
        },
    ]
    labels = {
        "items": {
            "q0": {
                "pattern": "direct-answer-bearing-message-pruned",
                "evidence": "fact removed",
            },
            "q1": {
                "pattern": "direct-useful-message-added",
                "evidence": "fact added",
            },
        }
    }
    return raw, baseline, candidate, dataset, labels


def test_build_evidence_quantifies_discordant_context_changes() -> None:
    evidence = build_evidence(
        raw=_inputs()[0],
        baseline=_inputs()[1],
        candidate=_inputs()[2],
        dataset=_inputs()[3],
        labels=_inputs()[4],
    )

    assert evidence["discordant_questions"] == 2
    assert evidence["baseline_wins"] == 1
    assert evidence["candidate_wins"] == 1
    assert evidence["aggregate"]["distinct_sessions"] == {
        "baseline": 4,
        "candidate": 5,
        "mean_gain": 0.5,
    }
    assert evidence["aggregate"]["answer_session_messages"] == {
        "baseline": 4,
        "candidate": 3,
        "removed": 2,
        "added": 1,
    }
    assert evidence["aggregate"]["full_answer_session_coverage"] == {
        "baseline": 2,
        "candidate": 2,
    }
    assert evidence["aggregate"]["context_json_bytes"]["ratio"] == pytest.approx(0.85)
    assert evidence["aggregate"]["fully_unanimous_pairs"] == 2


def test_build_evidence_rejects_labels_not_equal_to_discordant_set() -> None:
    raw, baseline, candidate, dataset, labels = _inputs()
    changed = copy.deepcopy(labels)
    del changed["items"]["q1"]

    with pytest.raises(DiscordanceAnalysisError, match="exactly the discordances"):
        build_evidence(
            raw=raw,
            baseline=baseline,
            candidate=candidate,
            dataset=dataset,
            labels=changed,
        )


def test_render_markdown_discloses_non_tuning_scope() -> None:
    raw, baseline, candidate, dataset, labels = _inputs()
    evidence = build_evidence(
        raw=raw,
        baseline=baseline,
        candidate=candidate,
        dataset=dataset,
        labels=labels,
    )

    markdown = render_markdown(evidence)

    assert "label-aware, non-tuning diagnostic" in markdown
    assert "accepts no human-audit key" in markdown
    assert "90.0%" not in markdown
