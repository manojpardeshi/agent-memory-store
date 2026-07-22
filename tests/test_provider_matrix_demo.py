from __future__ import annotations

import json
import sys
from unittest.mock import patch

from demo.provider_matrix import (
    CodexJsonModel,
    OllamaHttpModel,
    run_provider_matrix,
    validate_loopback_endpoint,
)


def test_offline_provider_matrix_covers_claude_gpt_and_local(tmp_path) -> None:
    report = run_provider_matrix(
        mode="offline",
        artifacts_dir=tmp_path,
        seed="0123456789abcdef0123456789abcdef",
    )

    assert report["schema_version"] == 3
    assert report["acceptance"]["passed"] is True
    assert report["acceptance"]["gating"] is True
    assert report["metrics"]["consumer_count"] == 3
    assert report["models"]["consumers"] == [
        "offline-claude-sonnet",
        "offline-codex-gpt",
        "offline-codex-ollama-local",
    ]
    assert len(report["context_transfers"]) == 4
    for consumer in report["consumer_results"]:
        assert consumer["metrics"] == {
            "baseline_accuracy": 0.0,
            "memory_accuracy": 1.0,
            "memory_lift": 1.0,
            "shared_recall_hit_rate": 1.0,
            "private_isolation_violations": 0,
        }
        assert consumer["invocations_ok"] is True
    assert report["metrics"]["correction_accuracy"] == 1.0
    assert report["metrics"]["stale_value_leaks"] == 0
    assert report["local_model"]["status"] == "offline-simulated"
    assert report["security_controls"]["environment_values_recorded"] is False
    assert "HOME" in report["security_controls"]["environment_allowlist_keys"]


def test_codex_json_model_extracts_final_message_and_usage(tmp_path) -> None:
    fake = tmp_path / "fake-codex.py"
    fake.write_text(
        "import json\n"
        "print(json.dumps({'type':'thread.started','thread_id':'x'}))\n"
        "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'{\\\"ok\\\":\\\"YES\\\"}'}}))\n"
        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':12,'output_tokens':3}}))\n"
    )
    model = CodexJsonModel(sys.executable, model="fake")
    model.command = [sys.executable, str(fake)]

    response = model.invoke("probe", "ignored")

    assert response.error is None
    assert json.loads(response.text) == {"ok": "YES"}
    assert response.usage == {"input_tokens": 12, "output_tokens": 3}


def test_live_local_requires_an_explicit_model(tmp_path) -> None:
    try:
        run_provider_matrix(
            mode="live",
            artifacts_dir=tmp_path,
            include_local=True,
            local_model=None,
        )
    except ValueError as exc:
        assert "--local-model" in str(exc)
    else:
        raise AssertionError("missing local model must fail explicitly")


class _FakeHttpResponse:
    def __init__(self, value: dict) -> None:
        self.payload = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_ollama_adapter_requires_loopback_and_extracts_native_usage() -> None:
    model = OllamaHttpModel(endpoint="http://127.0.0.1:11434", model="llama-test")
    value = {
        "response": '{"project_code":"PROJECT-AAAAAA"}',
        "done": True,
        "prompt_eval_count": 41,
        "eval_count": 9,
        "total_duration": 123,
    }
    with patch("demo.provider_matrix.urlopen", return_value=_FakeHttpResponse(value)):
        response = model.invoke("probe", "Return project_code")

    assert response.error is None
    assert response.usage == {
        "input_tokens": 41,
        "output_tokens": 9,
        "total_duration_ns": 123,
    }
    assert validate_loopback_endpoint("http://localhost:11434") == "http://localhost:11434"
    try:
        validate_loopback_endpoint("http://192.168.1.10:11434")
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("remote Ollama endpoints must be rejected")
