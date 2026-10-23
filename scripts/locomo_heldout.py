#!/usr/bin/env python3
"""LoCoMo-10 as the project's fresh held-out set: build stores and score looks, aggregate only.

See docs/architecture/held-out-renewal-plan.md. LoCoMo (snap-research/locomo, CC BY-NC 4.0) is
downloaded at run time and never committed. `build` ingests each conversation into its own store,
one turn per memory, with the session's real date as `occurred_at`. `look` scores a frozen
candidate against vector recall in one paired pass. It refuses to run without a clean worktree and
a freeze commit, records the look in the held-out ledger before computing anything, stops after the
set's look budget, and writes only aggregate and per-category results, never per-question outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_memory_store import FastEmbedder, MemoryStore, Scope

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "evaluation" / "memorybench" / "held-out-ledger.json"
SET_NAME = "locomo10"
SCORED_CATEGORIES = (1, 2, 3, 4)  # 5 is adversarial (unanswerable) and excluded
DEPTH = 10
_DIA = re.compile(r"D\d+:\d+")
_DATE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})\s*$", re.I
)
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)  # fmt: skip
_MONTHS = {name: number for number, name in enumerate(_MONTH_NAMES, start=1)}


def session_datetime(value: str) -> str:
    """'1:56 pm on 8 May, 2023' -> ISO 8601 UTC (LoCoMo gives no timezone; UTC is assumed)."""
    match = _DATE.match(value)
    if match is None:
        raise ValueError(f"unrecognized LoCoMo session date: {value!r}")
    hour, minute, ampm, day, month, year = match.groups()
    hour_24 = int(hour) % 12 + (12 if ampm.lower() == "pm" else 0)
    month_number = _MONTHS[month.lower()]
    return datetime(int(year), month_number, int(day), hour_24, int(minute), tzinfo=UTC).isoformat()


def turn_content(turn: dict[str, Any]) -> str:
    text = f"{turn['speaker']}: {turn.get('text', '').strip()}"
    if turn.get("blip_caption"):
        text += f" [shares an image: {turn['blip_caption']}]"
    return text


def evidence_ids(question: dict[str, Any]) -> set[str]:
    return {part for item in question.get("evidence") or [] for part in _DIA.findall(str(item))}


def scope_for(sample_id: str) -> Scope:
    return Scope.private("locomo", str(sample_id), "heldout")


def store_path(store_dir: Path, sample_id: str) -> Path:
    return store_dir / f"{sample_id}.sqlite3"


def build(dataset: list[dict[str, Any]], store_dir: Path, embedder: Any) -> dict[str, int]:
    store_dir.mkdir(parents=True, exist_ok=True)
    counts = {"conversations": 0, "turns": 0}
    for conversation in dataset:
        sample_id = str(conversation["sample_id"])
        sessions = conversation["conversation"]
        scope = scope_for(sample_id)
        with MemoryStore(
            store_path(store_dir, sample_id), embedder, default_turn_ttl_days=None
        ) as store:
            numbers = sorted(
                int(k.split("_")[1])
                for k, v in sessions.items()
                if re.fullmatch(r"session_\d+", k) and isinstance(v, list)
            )
            for number in numbers:
                occurred = session_datetime(sessions[f"session_{number}_date_time"])
                for turn in sessions[f"session_{number}"]:
                    store.remember_turn(
                        turn_content(turn),
                        "user",
                        scope,
                        metadata={"dia_id": turn["dia_id"], "session": number},
                        occurred_at=occurred,
                        operation_id=f"locomo:{sample_id}:{turn['dia_id']}",
                    )
                    counts["turns"] += 1
        counts["conversations"] += 1
    return counts


Arm = Callable[[MemoryStore, Scope, str], list[Any]]

ARMS: dict[str, Arm] = {
    "vector": lambda store, scope, q: store.recall(q, scope, limit=DEPTH, relevance_filter=None),
    "hybrid": lambda store, scope, q: store.recall(
        q, scope, limit=DEPTH, relevance_filter=None, retrieval="hybrid"
    ),
}


def score(
    dataset: list[dict[str, Any]], store_dir: Path, embedder: Any, arms: dict[str, Arm]
) -> dict[str, Any]:
    """Aggregate evidence-level recall per arm and category. Never returns per-question data."""
    totals: dict[str, dict[int, dict[str, float]]] = {
        name: {c: {"n": 0, "complete": 0, "recall_sum": 0.0} for c in SCORED_CATEGORIES}
        for name in arms
    }
    latency: dict[str, list[float]] = {name: [] for name in arms}
    excluded = 0
    for conversation in dataset:
        sample_id = str(conversation["sample_id"])
        scope = scope_for(sample_id)
        with MemoryStore(
            store_path(store_dir, sample_id), embedder, default_turn_ttl_days=None, read_only=True
        ) as store:
            for question in conversation["qa"]:
                category = int(question["category"])
                evidence = evidence_ids(question)
                if category not in SCORED_CATEGORIES:
                    continue
                if not evidence:
                    excluded += 1
                    continue
                for name, arm in arms.items():
                    started = time.perf_counter()
                    results = arm(store, scope, str(question["question"]))
                    latency[name].append((time.perf_counter() - started) * 1000)
                    found = {r.memory.metadata.get("dia_id") for r in results[:DEPTH]}
                    hit = evidence & found
                    bucket = totals[name][category]
                    bucket["n"] += 1
                    bucket["complete"] += hit == evidence
                    bucket["recall_sum"] += len(hit) / len(evidence)
    report: dict[str, Any] = {"excluded_without_parseable_evidence": excluded, "arms": {}}
    for name in arms:
        cats = totals[name]
        n = sum(c["n"] for c in cats.values())
        report["arms"][name] = {
            "scored_questions": n,
            "complete_evidence": int(sum(c["complete"] for c in cats.values())),
            "evidence_recall": round(sum(c["recall_sum"] for c in cats.values()) / n, 4)
            if n
            else 0,
            "median_latency_ms": round(sorted(latency[name])[len(latency[name]) // 2], 2)
            if latency[name]
            else None,
            "categories": {
                str(c): {
                    "n": v["n"],
                    "complete_evidence": int(v["complete"]),
                    "evidence_recall": round(v["recall_sum"] / v["n"], 4) if v["n"] else 0,
                }
                for c, v in cats.items()
            },
        }
    return report


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def record_look(candidate: str, freeze_commit: str, dataset_sha: str) -> dict[str, Any]:
    """Append the look to the ledger before any result exists; enforce the budget and freezing."""
    if _git("status", "--porcelain").strip():
        raise SystemExit("a held-out look requires a clean worktree")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", freeze_commit, "HEAD"], cwd=ROOT, check=True
    )
    ledger = json.loads(LEDGER.read_text())
    entry = ledger["held_out_sets"][SET_NAME]
    if entry["status"] != "active":
        raise SystemExit(f"{SET_NAME} is {entry['status']}")
    if dataset_sha != entry["dataset_sha256"]:
        raise SystemExit("LoCoMo file does not match the ledger digest")
    if len(entry["looks"]) >= entry["max_looks"]:
        raise SystemExit(f"{SET_NAME} has used its {entry['max_looks']} looks")
    look = {
        "candidate": candidate,
        "frozen_in": _git("rev-parse", "--short", freeze_commit).strip(),
        "evaluated_at_commit": _git("rev-parse", "--short", "HEAD").strip(),
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "result": None,
    }
    entry["looks"].append(look)
    if len(entry["looks"]) >= entry["max_looks"]:
        entry["status"] = "retired to tuning after its last look"
    LEDGER.write_text(json.dumps(ledger, indent=2) + "\n")
    return look


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "look"))
    parser.add_argument("--dataset", type=Path, default=ROOT / "demo-artifacts" / "locomo10.json")
    parser.add_argument("--stores", type=Path, default=ROOT / "demo-artifacts" / "locomo-stores")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--candidate", help="arm name in ARMS for a look")
    parser.add_argument("--freeze-commit", help="commit that froze the candidate and its rule")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    dataset = json.loads(raw)
    embedder = FastEmbedder(cache_dir=str(args.cache_dir), local_files_only=True)
    if args.command == "build":
        print(json.dumps(build(dataset, args.stores, embedder)))
        return 0
    if args.candidate not in ARMS or args.candidate == "vector" or not args.freeze_commit:
        raise SystemExit("a look needs --candidate (a non-baseline arm) and --freeze-commit")
    if args.output is None:
        raise SystemExit("a look needs --output for its aggregate report")
    look = record_look(args.candidate, args.freeze_commit, hashlib.sha256(raw).hexdigest())
    report = score(
        dataset,
        args.stores,
        embedder,
        {"vector": ARMS["vector"], args.candidate: ARMS[args.candidate]},
    )
    report["look"] = look
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "look"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
