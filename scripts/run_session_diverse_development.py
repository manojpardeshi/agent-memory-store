#!/usr/bin/env python3
"""Replay frozen development searches with the session-diverse context policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__:
    from scripts.memorybench_bridge import (
        SESSION_DIVERSE_CONTEXT_POLICY,
        MemoryBenchBridge,
    )
else:
    from memorybench_bridge import (
        SESSION_DIVERSE_CONTEXT_POLICY,
        MemoryBenchBridge,
    )

from llm_memory_store import FastEmbedder


class DevelopmentReplayError(RuntimeError):
    """Raised when frozen replay inputs or unchanged ranking do not match."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _context_bytes(results: list[dict[str, Any]]) -> int:
    return len(
        json.dumps(results, indent=2, ensure_ascii=False).encode("utf-8")
    )


def replay(
    *,
    manifest_path: Path,
    gate_path: Path,
    checkpoint_paths: list[Path],
    data_dir: Path,
    cache_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    manifest = _load(manifest_path)
    gates = _load(gate_path)
    if (
        manifest.get("role") != "development"
        or manifest.get("sealed") is not False
        or manifest.get("question_count") != 180
    ):
        raise DevelopmentReplayError("expected the unsealed 180-question development manifest")
    if gates.get("status") != "frozen-before-candidate-run":
        raise DevelopmentReplayError("candidate gates were not frozen before replay")
    if gates.get("development_manifest", {}).get("sha256") != _sha256(manifest_path):
        raise DevelopmentReplayError("gate contract identifies a different development manifest")
    policy = gates.get("candidate_policy", {})
    if policy.get("policy_id") != SESSION_DIVERSE_CONTEXT_POLICY:
        raise DevelopmentReplayError("gate contract has an unsupported candidate policy")

    checkpoints = [_load(path) for path in checkpoint_paths]
    source_hashes = {_sha256(path): str(path) for path in checkpoint_paths}
    sources: dict[str, tuple[dict[str, Any], str]] = {}
    for checkpoint in checkpoints:
        if checkpoint.get("status") != "completed":
            raise DevelopmentReplayError("every source checkpoint must be completed")
        source_run_id = checkpoint.get("dataSourceRunId")
        if not isinstance(source_run_id, str) or not source_run_id:
            raise DevelopmentReplayError("source checkpoint has no dataSourceRunId")
        for question_id in checkpoint.get("targetQuestionIds", []):
            if question_id in sources:
                raise DevelopmentReplayError(f"duplicate source question {question_id}")
            sources[question_id] = (checkpoint["questions"][question_id], source_run_id)

    question_ids = manifest.get("question_ids")
    if not isinstance(question_ids, list) or len(question_ids) != 180:
        raise DevelopmentReplayError("development question IDs are incomplete")
    if any(question_id not in sources for question_id in question_ids):
        raise DevelopmentReplayError("a development question is absent from source checkpoints")

    identity = {
        "experiment_id": gates["experiment_id"],
        "gate_sha256": _sha256(gate_path),
        "manifest_sha256": _sha256(manifest_path),
        "source_checkpoint_sha256": sorted(source_hashes),
    }
    if output_path.exists():
        report = _load(output_path)
        for name, expected in identity.items():
            if report.get(name) != expected:
                raise DevelopmentReplayError(f"resume identity mismatch: {name}")
    else:
        report = {
            "schema_version": 1,
            "status": "running",
            **identity,
            "model": "BAAI/bge-small-en-v1.5",
            "context_policy": policy,
            "source_checkpoints": source_hashes,
            "question_ids": question_ids,
            "questions": {},
            "started_at": datetime.now(UTC).isoformat(),
        }
        _write_atomic(output_path, report)

    embedder = FastEmbedder(
        model_name="BAAI/bge-small-en-v1.5",
        cache_dir=str(cache_dir),
        local_files_only=True,
    )
    bridge = MemoryBenchBridge(
        data_dir,
        embedder,
        context_policy=SESSION_DIVERSE_CONTEXT_POLICY,
    )
    completed = report["questions"]
    for index, question_id in enumerate(question_ids, start=1):
        if question_id in completed:
            continue
        source, source_run_id = sources[question_id]
        baseline_results = source["phases"]["search"]["results"]
        candidate_results, diagnostics = bridge.search_with_diagnostics(
            f"{question_id}-{source_run_id}", source["question"], 10
        )
        baseline_ids = [item["memory_id"] for item in baseline_results]
        pool_prefix = diagnostics["ranked_pool_top_10_memory_ids"][: len(baseline_ids)]
        if pool_prefix != baseline_ids:
            raise DevelopmentReplayError(
                f"unchanged ranked prefix did not reproduce for {question_id}"
            )
        if len(candidate_results) != len(baseline_results):
            raise DevelopmentReplayError(
                f"candidate changed result count for {question_id}"
            )
        completed[question_id] = {
            "question_type": source["questionType"],
            "results": candidate_results,
            "diagnostics": diagnostics,
            "context_json_bytes": _context_bytes(candidate_results),
        }
        _write_atomic(output_path, report)
        if index % 10 == 0 or index == len(question_ids):
            print(f"session-diverse development replay: {index}/{len(question_ids)}")

    report["status"] = "completed"
    report["completed_at"] = datetime.now(UTC).isoformat()
    _write_atomic(output_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay(
        manifest_path=args.manifest,
        gate_path=args.gates,
        checkpoint_paths=args.checkpoint,
        data_dir=args.data_dir,
        cache_dir=args.cache_dir,
        output_path=args.output,
    )
    print(f"completed {len(report['questions'])} development searches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
