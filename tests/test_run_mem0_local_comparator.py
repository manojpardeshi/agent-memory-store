"""Offline watchdog checks for the local Mem0 comparator runner."""

from __future__ import annotations

import json
import signal
import sys

import pytest

from scripts import run_mem0_local_comparator as runner


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="SIGALRM is Unix-only")
def test_question_deadline_raises_and_restores_signal_handler() -> None:
    previous = signal.getsignal(signal.SIGALRM)
    with pytest.raises(runner.QuestionDeadlineExceeded), runner.question_deadline(5):
        signal.raise_signal(signal.SIGALRM)
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.alarm(0) == 0


@pytest.mark.skipif(not hasattr(signal, "SIGALRM"), reason="SIGALRM is Unix-only")
def test_deadline_is_checkpointed_without_mem0_or_ollama(tmp_path, monkeypatch) -> None:
    dataset = tmp_path / "dataset.json"
    selection = tmp_path / "selection.json"
    output = tmp_path / "checkpoint.json"
    dataset.write_text(json.dumps([{"question_id": "q1"}]))
    selection.write_text(json.dumps({"question_ids": ["q1"]}))
    output.write_text(json.dumps({"status": "in-progress", "questions": {}, "run": {}}))
    monkeypatch.setattr(
        runner,
        "run_question",
        lambda *args, **kwargs: (_ for _ in ()).throw(runner.QuestionDeadlineExceeded()),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_mem0_local_comparator.py",
            "--dataset", str(dataset),
            "--selection", str(selection),
            "--output", str(output),
            "--work", str(tmp_path / "work"),
            "--question-deadline-seconds", "5",
        ],
    )

    assert runner.main() == 0
    checkpoint = json.loads(output.read_text())
    assert checkpoint["status"] == "in-progress"
    assert "exceeded 5s" in checkpoint["questions"]["q1"]["error"]
    assert signal.alarm(0) == 0


def test_session_failure_handler_does_not_swallow_deadline(tmp_path, monkeypatch) -> None:
    class TimedOutMemory:
        def add(self, *args, **kwargs):
            raise runner.QuestionDeadlineExceeded()

    monkeypatch.setattr(runner, "_build_memory", lambda *args: TimedOutMemory())
    item = {
        "question_id": "q1",
        "question": "test",
        "haystack_sessions": [[{"role": "user", "content": "hello"}]],
    }
    with pytest.raises(runner.QuestionDeadlineExceeded):
        runner.run_question(
            item,
            work_root=tmp_path,
            ollama_url="http://127.0.0.1:11434",
            model="test",
        )
