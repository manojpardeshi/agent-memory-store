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


def _long_session(session_id: str, count: int, marker: str) -> dict:
    """A session whose bodies are long enough that spans can pay for expansion."""
    filler = "This sentence is deliberate filler about unrelated household matters. " * 12
    messages = []
    for index in range(count):
        body = filler + (f" I spent 500 dollars on the {marker} last week." if index == 3 else "")
        messages.append({"role": "user" if index % 2 == 0 else "assistant", "content": body})
    return {
        "sessionId": session_id,
        "messages": messages,
        "metadata": {
            "date": "2026-01-02T03:04:00.000Z",
            "formattedDate": "3:04 am on 2 January, 2026",
        },
    }


def test_within_session_expansion_policy_is_explicit_and_reports_config(tmp_path: Path) -> None:
    from scripts.memorybench_bridge import (
        EXPANSION_BODY_FLOOR_CHARS,
        EXPANSION_PER_SESSION_CAP,
        WITHIN_SESSION_EXPANSION_CONTEXT_POLICY,
    )

    default_bridge = MemoryBenchBridge(tmp_path / "d", DeterministicEmbedder(64))
    assert default_bridge.initialize()["context_policy"] == RANKED_CONTEXT_POLICY
    candidate = MemoryBenchBridge(
        tmp_path / "c", DeterministicEmbedder(64),
        context_policy=WITHIN_SESSION_EXPANSION_CONTEXT_POLICY,
    ).initialize()
    config = candidate["context_policy_config"]
    assert config["per_session_expansion_cap"] == EXPANSION_PER_SESSION_CAP
    assert config["body_floor_chars"] == EXPANSION_BODY_FLOOR_CHARS
    assert config["new_sessions_introduced"] == 0
    assert config["model_in_query_path"] is False


def test_within_session_expansion_keeps_baseline_prefix_no_new_sessions_within_budget(
    tmp_path: Path,
) -> None:
    from scripts.memorybench_bridge import WITHIN_SESSION_EXPANSION_CONTEXT_POLICY
    from scripts.within_session_expansion import context_json_bytes

    sessions = [_long_session("q-session-0", 8, "designer handbag"),
                _long_session("q-session-1", 6, "garden hose")]
    ranked = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))
    ranked.ingest("tag", sessions)
    baseline, _ = ranked.search_with_diagnostics("tag", "how much did I spend on the handbag", 3)

    expanded = MemoryBenchBridge(
        tmp_path, DeterministicEmbedder(64),
        context_policy=WITHIN_SESSION_EXPANSION_CONTEXT_POLICY,
    )
    query = "how much did I spend on the handbag"
    selected, diag = expanded.search_with_diagnostics("tag", query, 3)

    # baseline retained as an ordered prefix, by identity
    assert [m["memory_id"] for m in selected[:3]] == [m["memory_id"] for m in baseline]
    # no session outside the baseline's
    base_sessions = {m["metadata"]["session_id"] for m in baseline}
    assert {m["metadata"]["session_id"] for m in selected} <= base_sessions
    # budget: never above what the baseline cost
    assert context_json_bytes(selected) <= context_json_bytes(baseline)
    assert diag["selected_context_json_bytes"] <= diag["baseline_context_json_bytes"]
    # spans actually paid for expansion here
    assert diag["expansions_admitted"] >= 1
    assert all("expansion" in m for m in selected[3:])
    # a reduced baseline body keeps its provenance header
    assert all(m["content"].startswith("[longmemeval-source]") for m in selected)


def test_v12_protects_each_sessions_anchor_and_keeps_all_v11_invariants(tmp_path: Path) -> None:
    from scripts.memorybench_bridge import WITHIN_SESSION_EXPANSION_V12_CONTEXT_POLICY
    from scripts.within_session_expansion import context_json_bytes, split_header

    sessions = [_long_session("q-session-0", 8, "designer handbag"),
                _long_session("q-session-1", 6, "garden hose")]
    ranked = MemoryBenchBridge(tmp_path, DeterministicEmbedder(64))
    ranked.ingest("tag", sessions)
    query = "how much did I spend on the handbag"
    baseline, _ = ranked.search_with_diagnostics("tag", query, 3)

    v12 = MemoryBenchBridge(
        tmp_path, DeterministicEmbedder(64),
        context_policy=WITHIN_SESSION_EXPANSION_V12_CONTEXT_POLICY,
    )
    assert v12.initialize()["context_policy_config"]["protected"].startswith("each session")
    selected, diag = v12.search_with_diagnostics("tag", query, 3)

    assert [m["memory_id"] for m in selected[:3]] == [m["memory_id"] for m in baseline]
    assert {m["metadata"]["session_id"] for m in selected} <= {
        m["metadata"]["session_id"] for m in baseline
    }
    assert context_json_bytes(selected) <= context_json_bytes(baseline)
    anchors = {}
    for m in baseline:
        anchors.setdefault(m["metadata"]["session_id"], m)
    for anchor in anchors.values():
        chosen = next(m for m in selected if m["memory_id"] == anchor["memory_id"])
        assert split_header(chosen["content"])[1] == split_header(anchor["content"])[1]
    assert diag["protected_anchors"] == len(anchors)
