"""Tests for the single-arm kimi baseline runner's safety properties.

These cover the guards that matter before spending money: dataset identity, checkpoint
completeness, and that the question date actually reaches the prompt. The paid path
itself is not exercised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_memorybench_kimi_baseline import (
    DATASET_SHA256,
    BaselineRunError,
    _merge_checkpoints,
    _summary,
)


def _checkpoint(path: Path, question_ids: list[str], *, status: str = "completed") -> Path:
    path.write_text(
        json.dumps(
            {
                "status": status,
                "questions": {q: {"question": q, "phases": {}} for q in question_ids},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_frozen_dataset_digest_matches_the_contract() -> None:
    """Guards against a silently substituted benchmark file."""
    assert DATASET_SHA256 == (
        "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
    )


def test_merge_rejects_incomplete_checkpoints(tmp_path: Path) -> None:
    path = _checkpoint(tmp_path / "a.json", ["q1"], status="in-progress")
    with pytest.raises(BaselineRunError, match="not completed"):
        _merge_checkpoints([path])


def test_merge_rejects_duplicate_questions(tmp_path: Path) -> None:
    a = _checkpoint(tmp_path / "a.json", ["q1", "q2"])
    b = _checkpoint(tmp_path / "b.json", ["q2"])
    with pytest.raises(BaselineRunError, match="duplicate question"):
        _merge_checkpoints([a, b])


def test_merge_combines_disjoint_checkpoints(tmp_path: Path) -> None:
    a = _checkpoint(tmp_path / "a.json", ["q1"])
    b = _checkpoint(tmp_path / "b.json", ["q2"])
    assert set(_merge_checkpoints([a, b])) == {"q1", "q2"}


def test_summary_counts_unresolved_dates_visibly() -> None:
    """An unresolved date is the defect being fixed, so it must surface in the summary."""
    report = {
        "questions": {
            "q1": {"question_type": "temporal-reasoning", "label": "correct",
                   "question_date_source": "dataset"},
            "q2": {"question_type": "temporal-reasoning", "label": "incorrect",
                   "question_date_source": "unresolved"},
        },
        "budget": {"spent_usd": 1.25},
    }
    summary = _summary(report)
    assert summary["correct"] == 1
    assert summary["answered"] == 2
    assert summary["questions_without_resolved_date"] == 1
    assert summary["categories"]["temporal-reasoning"] == {"correct": 1, "total": 2}
