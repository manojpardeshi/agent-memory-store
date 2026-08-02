from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder
from scripts.memorybench_bridge import (
    RANKED_CONTEXT_POLICY,
    SESSION_DIVERSE_CONTEXT_POLICY,
    BridgeRequestError,
    MemoryBenchBridge,
)
from scripts.verify_longmemeval_dataset import verify_dataset


def _session(content: str = "The synthetic access code is cobalt-731.") -> dict:
    return {
        "sessionId": "question-1-session-0",
        "messages": [
            {"role": "user", "content": content},
            {"role": "assistant", "content": "I will remember that synthetic value."},
        ],
        "metadata": {
            "date": "2026-01-02T03:04:00.000Z",
            "formattedDate": "3:04 am on 2 January, 2026",
        },
    }


def test_bridge_ingests_idempotently_searches_and_isolates_containers(tmp_path: Path) -> None:
    bridge = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))

    first = bridge.ingest("container-a", [_session()])
    repeated = bridge.ingest("container-a", [_session()])
    other = bridge.ingest("container-b", [_session("The synthetic access code is amber-992.")])

    assert repeated == first
    assert len(first["documentIds"]) == 2
    assert len(other["documentIds"]) == 2

    results = bridge.search("container-a", "What is the synthetic access code?", 5)
    assert results
    assert "cobalt-731" in results[0]["content"]
    assert results[0]["metadata"]["session_date"] == "2026-01-02T03:04:00.000Z"
    assert results[0]["trust_label"] == "untrusted_memory"
    assert all("amber-992" not in item["content"] for item in results)

    database_files = list(tmp_path.glob("*.sqlite3"))
    assert len(database_files) == 2
    assert all(
        "container-a" not in path.name and "container-b" not in path.name
        for path in database_files
    )


def test_bridge_clear_is_exact_and_missing_search_is_empty(tmp_path: Path) -> None:
    bridge = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))
    bridge.ingest("container-a", [_session()])
    bridge.ingest("container-b", [_session("The synthetic access code is amber-992.")])

    receipt = bridge.clear("container-a")

    assert receipt["deleted_files"] >= 1
    assert bridge.search("container-a", "code", 5) == []
    assert bridge.search("container-b", "amber-992", 5)


def test_session_diverse_selection_caps_then_backfills_in_rank_order() -> None:
    ranked = [
        {"memory_id": f"m{index}", "metadata": {"session_id": session_id}}
        for index, session_id in enumerate(("a", "a", "a", "b", "b", "c"), start=1)
    ]

    selected = MemoryBenchBridge.select_session_diverse(ranked, limit=6)

    assert [item["memory_id"] for item in selected] == [
        "m1",
        "m2",
        "m3",
        "m4",
        "m5",
        "m6",
    ]
    without_backfill = MemoryBenchBridge.select_session_diverse(ranked, limit=5)
    assert [item["memory_id"] for item in without_backfill] == [
        "m1",
        "m2",
        "m4",
        "m5",
        "m6",
    ]


def test_session_diverse_policy_is_explicit_and_default_stays_ranked(tmp_path: Path) -> None:
    default_bridge = MemoryBenchBridge(tmp_path / "default", DeterministicEmbedder(64))
    candidate_bridge = MemoryBenchBridge(
        tmp_path / "candidate",
        DeterministicEmbedder(64),
        context_policy=SESSION_DIVERSE_CONTEXT_POLICY,
    )

    assert default_bridge.initialize()["context_policy"] == RANKED_CONTEXT_POLICY
    candidate = candidate_bridge.initialize()
    assert candidate["context_policy"] == SESSION_DIVERSE_CONTEXT_POLICY
    assert candidate["context_policy_config"]["ranked_candidate_pool"] == 50
    assert candidate["context_policy_config"]["per_session_cap"] == 2


def test_session_diverse_selection_rejects_missing_session_provenance() -> None:
    with pytest.raises(ValueError, match="provenance session_id"):
        MemoryBenchBridge.select_session_diverse(
            [{"memory_id": "m1", "metadata": {}}], limit=1
        )


def test_bridge_rejects_changed_content_for_same_operation(tmp_path: Path) -> None:
    bridge = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))
    bridge.ingest("container-a", [_session()])

    with pytest.raises(RuntimeError, match="different content"):
        bridge.ingest("container-a", [_session("Changed benchmark content.")])


def test_bridge_rejects_invalid_roles(tmp_path: Path) -> None:
    bridge = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))
    session = _session()
    session["messages"][0]["role"] = "system"

    with pytest.raises(BridgeRequestError, match="user or assistant"):
        bridge.ingest("container-a", [session])


def test_bridge_preserves_empty_source_message_position_with_placeholder(
    tmp_path: Path,
) -> None:
    bridge = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))
    session = _session()
    session["messages"][0]["content"] = ""

    bridge.ingest("container-a", [session])
    results = bridge.search("container-a", "empty source message", 5)

    placeholder = next(
        item for item in results if "[empty source message]" in item["content"]
    )
    assert placeholder["metadata"]["message_index"] == 0
    assert placeholder["metadata"]["source_content_empty"] is True


def test_json_lines_protocol_keeps_diagnostics_out_of_stdout(tmp_path: Path) -> None:
    session = _session()
    session["messages"][1]["content"] += " Unicode line separator:\u2028preserved."
    requests = [
        {"id": 1, "operation": "initialize"},
        {
            "id": 2,
            "operation": "ingest",
            "container_tag": "container-a",
            "sessions": [session],
        },
        {
            "id": 3,
            "operation": "search",
            "container_tag": "container-a",
            "query": "cobalt-731",
            "limit": 5,
        },
    ]
    process = subprocess.run(
        [
            sys.executable,
            "scripts/memorybench_bridge.py",
            "--data-dir",
            str(tmp_path),
            "--embedder",
            "deterministic",
        ],
        input="".join(json.dumps(item) + "\n" for item in requests),
        text=True,
        capture_output=True,
        check=True,
    )

    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert len(responses) == 3
    assert [response["id"] for response in responses] == [1, 2, 3]
    assert all(response["ok"] is True for response in responses)
    assert any("cobalt-731" in result["content"] for result in responses[2]["result"])


def test_protocol_isolates_native_stdout_writes_from_json() -> None:
    program = """
import os
from scripts.memorybench_bridge import _isolate_protocol_stdout, _write_response

protocol = _isolate_protocol_stdout()
os.write(1, b"native diagnostic\\n")
_write_response(7, result={"value": "ok"}, output=protocol)
protocol.close()
"""
    process = subprocess.run(
        [sys.executable, "-c", program],
        text=True,
        capture_output=True,
        check=True,
    )

    assert json.loads(process.stdout) == {
        "id": 7,
        "ok": True,
        "result": {"value": "ok"},
    }
    assert process.stderr == "native diagnostic\n"


def test_dataset_verifier_rejects_unfrozen_input(tmp_path: Path) -> None:
    source = tmp_path / "longmemeval.json"
    source.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="byte size mismatch"):
        verify_dataset(source)
