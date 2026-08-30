"""Regression tests for question-date resolution in the answering path.

The retrieval-only phase list this project runs leaves MemoryBench's `questionDate`
unset, so the answering prompt rendered "Question Date: Not specified" for all 60
questions of the stratified diagnostic. Temporal questions of the form "how many days
ago ..." are unanswerable without a reference date.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_memorybench_claude_pilot import build_answer_prompt, load_question_dates


def _dataset(tmp_path: Path) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            [
                {"question_id": "q1", "question_date": "2023/05/30 (Tue) 23:40"},
                {"question_id": "q2", "question_date": "2023/06/01 (Thu) 09:00"},
                {"question_id": "q3"},
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_load_question_dates_maps_ids_and_skips_missing(tmp_path: Path) -> None:
    dates = load_question_dates(_dataset(tmp_path))
    assert dates == {
        "q1": "2023/05/30 (Tue) 23:40",
        "q2": "2023/06/01 (Thu) 09:00",
    }
    assert "q3" not in dates


def test_load_question_dates_without_dataset_is_empty() -> None:
    assert load_question_dates(None) == {}


def test_answer_prompt_carries_the_date_when_resolved() -> None:
    resolved = build_answer_prompt("How many days ago?", [], "2023/05/30 (Tue) 23:40")
    assert "2023/05/30 (Tue) 23:40" in resolved
    assert "Not specified" not in resolved


def test_answer_prompt_falls_back_to_not_specified() -> None:
    """The prior behaviour, retained so its effect stays visible rather than silent."""
    assert "Not specified" in build_answer_prompt("How many days ago?", [], None)
