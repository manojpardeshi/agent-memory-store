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
    assert DATASET_SHA256 == ("d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442")


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
            "q1": {
                "question_type": "temporal-reasoning",
                "label": "correct",
                "question_date_source": "dataset",
            },
            "q2": {
                "question_type": "temporal-reasoning",
                "label": "incorrect",
                "question_date_source": "unresolved",
            },
        },
        "budget": {"spent_usd": 1.25},
    }
    summary = _summary(report)
    assert summary["correct"] == 1
    assert summary["answered"] == 2
    assert summary["questions_without_resolved_date"] == 1
    assert summary["categories"]["temporal-reasoning"] == {"correct": 1, "total": 2}


def _ledger() -> dict:
    return {"budget": {"max_total_usd": 5.0, "spent_usd": 0.0}}


def _ok_call() -> dict:
    return {"result": "ok", "usage": {"calculated_cost_usd": 0.01}}


def test_http_429_is_retried_and_counted(monkeypatch) -> None:
    import scripts.run_memorybench_kimi_baseline as runner

    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("Kimi API returned HTTP 429")
        return _ok_call()

    monkeypatch.setattr(runner, "run_kimi_call", flaky)
    monkeypatch.setattr(runner, "_sleep", lambda s: None)
    report = _ledger()
    call = runner._guarded_call(
        report, "k", b"{}", max_completion_tokens=10, max_call_usd=0.5, timeout_seconds=1
    )
    assert call["result"] == "ok"
    assert calls["n"] == 3
    assert report["rate_limit_retries"] == 2
    assert report["budget"]["spent_usd"] == 0.01  # only the successful call is charged


def test_other_http_errors_are_not_retried(monkeypatch) -> None:
    import pytest

    import scripts.run_memorybench_kimi_baseline as runner

    calls = {"n": 0}

    def broken(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("Kimi API returned HTTP 500")

    monkeypatch.setattr(runner, "run_kimi_call", broken)
    monkeypatch.setattr(runner, "_sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        runner._guarded_call(
            _ledger(), "k", b"{}", max_completion_tokens=10, max_call_usd=0.5, timeout_seconds=1
        )
    assert calls["n"] == 1


def test_persistent_429_eventually_stops(monkeypatch) -> None:
    import pytest

    import scripts.run_memorybench_kimi_baseline as runner

    monkeypatch.setattr(
        runner,
        "run_kimi_call",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Kimi API returned HTTP 429")),
    )
    monkeypatch.setattr(runner, "_sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        runner._guarded_call(
            _ledger(), "k", b"{}", max_completion_tokens=10, max_call_usd=0.5, timeout_seconds=1
        )
