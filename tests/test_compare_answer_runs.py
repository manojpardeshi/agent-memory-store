"""compare_answer_runs: paired counts, sign test, and design-blind suppression."""

from __future__ import annotations

from scripts.compare_answer_runs import compare, sign_test_p


def _report(labels: dict[str, tuple[str, str]]) -> dict:
    return {"questions": {q: {"question_type": t, "label": lab} for q, (t, lab) in labels.items()}}


def test_paired_counts_and_category_totals() -> None:
    a = _report({"q1": ("ms", "correct"), "q2": ("ms", "incorrect"), "q3": ("tr", "correct")})
    b = _report({"q1": ("ms", "correct"), "q2": ("ms", "correct"), "q3": ("tr", "incorrect")})
    r = compare(a, b)
    assert r["paired"] == {"both": 1, "only_b": 1, "only_a": 1}
    assert r["categories"]["ms"]["a"] == 1 and r["categories"]["ms"]["b"] == 2
    assert (r["arm_a_correct"], r["arm_b_correct"]) == (2, 2)


def test_design_blind_questions_are_counted_but_never_listed() -> None:
    a = _report({"seen": ("ms", "incorrect"), "blind": ("ms", "incorrect")})
    b = _report({"seen": ("ms", "correct"), "blind": ("ms", "correct")})
    r = compare(a, b, design_blind={"blind"})
    listed = {d["question_id"] for d in r["visible_discordant"]}
    assert listed == {"seen"}
    assert r["design_blind_discordant_count_only"] == 1
    assert r["paired"]["only_b"] == 2  # blind question still counted in aggregates


def test_only_restricts_to_a_subset() -> None:
    a = _report({"q1": ("ms", "correct"), "q2": ("ms", "correct")})
    b = _report({"q1": ("ms", "correct"), "q2": ("ms", "incorrect")})
    assert compare(a, b, only={"q1"})["shared_questions"] == 1


def test_sign_test_matches_known_values() -> None:
    assert sign_test_p(0, 0) == 1.0
    assert abs(sign_test_p(0, 6) - 0.03125) < 1e-12  # 2 * (1/64)
    assert abs(sign_test_p(1, 7) - 0.0703125) < 1e-12  # 2 * 9/256
    assert sign_test_p(3, 3) == 1.0
