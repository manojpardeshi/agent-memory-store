"""Evidence-level recall: exact answer-bearing turns, not merely the right session."""

from __future__ import annotations

from scripts.analyze_evidence_recall import evidence_turns, retrieved_turns, score


def _item(qtype: str, sessions: list[list[bool]]) -> dict:
    return {
        "question_type": qtype,
        "haystack_sessions": [
            [{"content": "x", "has_answer": flag} for flag in session] for session in sessions
        ],
    }


def _result(qid: str, session: int, message: int) -> dict:
    return {"metadata": {"session_id": f"{qid}-session-{session}", "message_index": message}}


def test_evidence_turns_reads_has_answer_flags() -> None:
    assert evidence_turns(_item("t", [[False, True], [True]])) == {(0, 1), (1, 0)}


def test_right_session_wrong_message_is_not_evidence() -> None:
    """The exact gap session-level Hit@10 cannot see."""
    item = _item("multi-session", [[False, False, True]])
    results = {"q": [_result("q", 0, 0), _result("q", 0, 1)]}
    report = score({"q": item}, results, ["q"])
    assert report["complete_evidence"] == 0 and report["any_evidence"] == 0


def test_partial_and_complete_evidence_and_cutoff() -> None:
    item = _item("temporal-reasoning", [[True], [True]])
    full = {"q": [_result("q", 0, 0), _result("q", 1, 0)]}
    assert score({"q": item}, full, ["q"])["complete_evidence"] == 1
    assert score({"q": item}, full, ["q"], k=1)["evidence_recall"] == 0.5


def test_questions_without_labels_are_excluded_and_counted() -> None:
    report = score({"q": _item("abs", [[False]])}, {"q": []}, ["q"])
    assert report["scored_questions"] == 0
    assert report["questions_without_labelled_evidence"] == 1


def test_other_questions_results_never_count() -> None:
    found = retrieved_turns("q1", [_result("q2", 0, 0)], 10)
    assert found == set()
