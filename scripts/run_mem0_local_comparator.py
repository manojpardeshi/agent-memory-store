#!/usr/bin/env python3
"""Run the matched-local Mem0 OSS comparator over a frozen LongMemEval-S selection.

This is comparator evidence for the competitive benchmark contract. It runs Mem0 OSS
entirely locally: extraction through loopback Ollama, embeddings through FastEmbed with
the same `BAAI/bge-small-en-v1.5` identity the product store uses, and a local on-disk
Qdrant collection per question. No hosted API, no credential, and no network egress
beyond the machine's own loopback interface.

The emitted checkpoint is deliberately shaped for `analyze_longmemeval_retrieval.py`, so
both arms are scored by the identical deterministic session-label analyzer.

Ingestion is slow by construction: Mem0 issues an LLM extraction call per session. The
run checkpoints after every question and is resumable, because a full pass takes hours.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import time
from pathlib import Path
from typing import Any

# Mem0 OSS enables PostHog telemetry by default. This project forbids a runtime cloud
# dependency in benchmark runs, so the switch is set before mem0 is imported.
os.environ.setdefault("MEM0_TELEMETRY", "false")

SEARCH_DEPTH = 10
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIMS = 384


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write the checkpoint atomically so an interrupted run cannot corrupt it."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
    tmp.replace(path)


def _build_memory(work_dir: Path, collection: str, ollama_url: str, model: str):
    from mem0 import Memory

    return Memory.from_config(
        {
            "llm": {
                "provider": "ollama",
                "config": {
                    "model": model,
                    "ollama_base_url": ollama_url,
                    "temperature": 0,
                },
            },
            "embedder": {
                "provider": "fastembed",
                "config": {"model": EMBED_MODEL, "embedding_dims": EMBED_DIMS},
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "collection_name": collection,
                    "path": str(work_dir),
                    "embedding_model_dims": EMBED_DIMS,
                    "on_disk": True,
                },
            },
        }
    )


def run_question(
    item: dict[str, Any],
    *,
    work_root: Path,
    ollama_url: str,
    model: str,
) -> dict[str, Any]:
    """Ingest one question's full haystack, then search once at the fixed depth."""
    question_id = str(item["question_id"])
    work_dir = work_root / question_id
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    memory = _build_memory(work_dir, "comparator", ollama_url, model)
    sessions = item["haystack_sessions"]

    ingest_started = time.time()
    extracted = 0
    failures: list[dict[str, Any]] = []
    for index, session in enumerate(sessions):
        messages = [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in session
            if str(m.get("content", "")).strip()
        ]
        if not messages:
            continue
        # The analyzer resolves provenance by this exact label, so it must encode the
        # session's index within haystack_session_ids rather than the opaque source id.
        label = f"{question_id}-session-{index}"
        try:
            result = memory.add(
                messages,
                user_id=question_id,
                metadata={"session_id": label},
                infer=True,
            )
            extracted += len(result.get("results", []) if isinstance(result, dict) else [])
        except Exception as error:  # noqa: BLE001 - one bad session must not lose the run
            failures.append({"session_index": index, "error": repr(error)[:300]})
    ingest_seconds = time.time() - ingest_started

    search_started = time.time()
    raw = memory.search(
        str(item["question"]), filters={"user_id": question_id}, limit=SEARCH_DEPTH
    )
    search_seconds = time.time() - search_started
    hits = raw.get("results") if isinstance(raw, dict) else raw

    results = [
        {
            "id": hit.get("id"),
            "memory": hit.get("memory"),
            "score": hit.get("score"),
            "metadata": {"session_id": (hit.get("metadata") or {}).get("session_id")},
        }
        for hit in (hits or [])[:SEARCH_DEPTH]
    ]

    return {
        "phases": {"search": {"results": results}},
        "diagnostics": {
            "session_count": len(sessions),
            "message_count": sum(len(s) for s in sessions),
            "memories_extracted": extracted,
            "ingest_seconds": round(ingest_seconds, 3),
            "search_seconds": round(search_seconds, 4),
            "returned_result_count": len(results),
            "session_failures": failures,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--max-questions", type=int, default=0)
    args = parser.parse_args()

    dataset = _load_json(args.dataset)
    by_id = {str(item["question_id"]): item for item in dataset}
    selection = _load_json(args.selection)
    target_ids = [str(q) for q in selection["question_ids"]]
    if args.max_questions:
        target_ids = target_ids[: args.max_questions]

    missing = [q for q in target_ids if q not in by_id]
    if missing:
        raise SystemExit(f"selection references absent questions: {missing[:5]}")

    args.work.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.output.exists():
        checkpoint = _load_json(args.output)
        done = len(checkpoint.get("questions", {}))
        print(f"resuming from {args.output} with {done} done", flush=True)
    else:
        import mem0

        checkpoint = {
            "status": "in-progress",
            "targetQuestionIds": target_ids,
            "questions": {},
            "run": {
                "provider": "mem0-oss-local",
                "mem0_version": getattr(mem0, "__version__", "unknown"),
                "llm": {"provider": "ollama", "model": args.model, "endpoint": args.ollama_url},
                "embedder": {"provider": "fastembed", "model": EMBED_MODEL, "dims": EMBED_DIMS},
                "vector_store": "qdrant-local-on-disk",
                "infer": True,
                "search_depth": SEARCH_DEPTH,
                "telemetry_disabled": os.environ.get("MEM0_TELEMETRY"),
                "hosted_api_calls": 0,
                "paid_cost_usd": 0.0,
                "machine": {
                    "platform": platform.platform(),
                    "machine": platform.machine(),
                    "node": platform.node(),
                },
                "selection_file": str(args.selection),
                "dataset_file": str(args.dataset),
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
        }
        _write_atomic(args.output, checkpoint)

    pending = [q for q in target_ids if q not in checkpoint["questions"]]
    print(f"{len(pending)} of {len(target_ids)} questions pending", flush=True)

    run_started = time.time()
    for position, question_id in enumerate(pending, start=1):
        started = time.time()
        try:
            entry = run_question(
                by_id[question_id],
                work_root=args.work,
                ollama_url=args.ollama_url,
                model=args.model,
            )
        except Exception as error:  # noqa: BLE001 - record and continue
            entry = {"phases": {}, "error": repr(error)[:500]}
            print(f"[{position}/{len(pending)}] {question_id} FAILED: {error!r}", flush=True)
        checkpoint["questions"][question_id] = entry
        _write_atomic(args.output, checkpoint)

        elapsed = time.time() - started
        mean = (time.time() - run_started) / position
        remaining = (len(pending) - position) * mean
        diagnostics = entry.get("diagnostics", {})
        print(
            f"[{position}/{len(pending)}] {question_id} "
            f"{elapsed:.0f}s sessions={diagnostics.get('session_count', '?')} "
            f"memories={diagnostics.get('memories_extracted', '?')} "
            f"returned={diagnostics.get('returned_result_count', '?')} "
            f"| eta {remaining / 3600:.1f}h",
            flush=True,
        )

    complete = all(q in checkpoint["questions"] for q in target_ids)
    scoreable = all(
        checkpoint["questions"].get(q, {}).get("phases", {}).get("search")
        for q in target_ids
    )
    checkpoint["status"] = "completed" if complete and scoreable else "in-progress"
    checkpoint["run"]["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    checkpoint["run"]["total_seconds"] = round(time.time() - run_started, 1)
    _write_atomic(args.output, checkpoint)
    print(f"status={checkpoint['status']} output={args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
