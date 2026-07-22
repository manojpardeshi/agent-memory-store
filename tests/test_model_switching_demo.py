from __future__ import annotations

import json
import sys

from demo.model_switching import CommandModel, run_demo, slot_accuracy


def test_offline_model_switching_demo_is_measurable_and_passes(tmp_path) -> None:
    report = run_demo(
        mode="offline",
        artifacts_dir=tmp_path,
        seed="0123456789abcdef0123456789abcdef",
    )

    assert report["acceptance"]["passed"] is True
    assert report["acceptance"]["gating"] is True
    assert report["models"]["switch_sequence"] == [
        "offline-model-a",
        "offline-model-b",
        "offline-model-a",
    ]
    assert report["metrics"] == {
        "capture_accuracy": 1.0,
        "baseline_accuracy": 0.0,
        "memory_accuracy": 1.0,
        "memory_lift": 1.0,
        "correction_accuracy": 1.0,
        "shared_recall_hit_rate": 1.0,
        "stale_value_leaks": 0,
        "private_isolation_violations": 0,
        "private_control_hit_rate": 1.0,
    }
    first_transfer, return_transfer = report["context_transfers"]
    assert first_transfer["from_model"] == "offline-model-a"
    assert first_transfer["to_model"] == "offline-model-b"
    assert first_transfer["memory_item_count"] == 3
    assert first_transfer["memory_character_count"] > 0
    assert first_transfer["memory_utf8_byte_count"] == first_transfer["memory_character_count"]
    assert first_transfer["estimated_memory_tokens"] > 0
    assert first_transfer["prompt_character_count"] > first_transfer["memory_character_count"]
    assert first_transfer["truncated"] is False
    assert return_transfer["from_model"] == "offline-model-b"
    assert return_transfer["to_model"] == "offline-model-a"
    assert return_transfer["memory_item_count"] >= 1
    assert report["schema_version"] == 2
    run_directory = next(path for path in tmp_path.iterdir() if path.is_dir())
    saved = json.loads((run_directory / "report.json").read_text())
    assert saved["run_id"] == report["run_id"]
    assert (run_directory / "memory.sqlite3").exists()
    assert (run_directory / "report.json").stat().st_mode & 0o777 == 0o600


def test_slot_accuracy_requires_correct_json_key_binding() -> None:
    expected = {
        "project_code": "PROJECT-AAAAAA",
        "editor_preference": "EDITOR-BBBBBB",
        "locale_preference": "LOCALE-CCCCCC",
    }
    wrong_keys = json.dumps(
        {
            "project_code": "EDITOR-BBBBBB",
            "editor_preference": "LOCALE-CCCCCC",
            "locale_preference": "PROJECT-AAAAAA",
        }
    )

    assert slot_accuracy(wrong_keys, expected) == 0.0
    assert slot_accuracy("not json PROJECT-AAAAAA EDITOR-BBBBBB LOCALE-CCCCCC", expected) == 0.0


def test_command_model_does_not_forward_unrelated_environment_secrets(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_UNRELATED_SECRET", "must-not-reach-model")
    model = CommandModel(
        "environment-probe",
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('DEMO_UNRELATED_SECRET', 'ABSENT'))",
        ],
    )

    response = model.invoke("environment", "ignored")

    assert response.error is None
    assert response.text == "ABSENT"
