#!/usr/bin/env python3
"""Free, deterministic evidence-level retrieval metric for LongMemEval-S.

LongMemEval marks the exact answer-bearing turns with `has_answer: true`. This scores whether
those turns reach the top-k context, rather than whether any message from the right session does.
Session-level Hit@10 is 97% on the 180 development questions; evidence-level completeness is 70%,
and the gap sits where answers fail. It needs no model and costs nothing to run.

It measures retrieval only. A question whose evidence is complete can still be answered wrongly:
the v1.2 diagnostic raised complete-evidence questions from 121 to 129 of 174 while answers moved by
one. Treat a gain here as better retrieval, never as an answer-quality claim.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

SESSION_RE = re.compile(r"^(?P<q>.+)-session-(?P<i>\d+)$")


def evidence_turns(item: dict[str, Any]) -> set[tuple[int, int]]:
    """(session index, message index) of every labelled answer-bearing turn."""
    return {
        (i, j)
        for i, session in enumerate(item["haystack_sessions"])
        for j, message in enumerate(session)
        if message.get("has_answer") is True
    }


def retrieved_turns(
    question_id: str, results: list[dict[str, Any]], k: int
) -> set[tuple[int, int]]:
    """Positions present in the first k results that belong to this question."""
    found = set()
    for result in results[:k]:
        meta = result.get("metadata") or {}
        match = SESSION_RE.match(str(meta.get("session_id", "")))
        index = meta.get("message_index")
        if match and match.group("q") == question_id and isinstance(index, int):
            found.add((int(match.group("i")), index))
    return found


def score(
    dataset: dict[str, dict[str, Any]],
    results_by_question: dict[str, list[dict[str, Any]]],
    question_ids: list[str],
    *,
    k: int = 10,
) -> dict[str, Any]:
    cats: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    recall_sum: dict[str, float] = collections.defaultdict(float)
    no_evidence = 0
    for qid in question_ids:
        item = dataset[qid]
        evidence = evidence_turns(item)
        if not evidence:
            no_evidence += 1
            continue
        hit = evidence & retrieved_turns(qid, results_by_question[qid], k)
        c = cats[item["question_type"]]
        c["n"] += 1
        c["complete"] += hit == evidence
        c["any"] += bool(hit)
        recall_sum[item["question_type"]] += len(hit) / len(evidence)
    n = sum(c["n"] for c in cats.values())
    return {
        "k": k,
        "scored_questions": n,
        "questions_without_labelled_evidence": no_evidence,
        "evidence_recall": round(sum(recall_sum.values()) / n, 4) if n else 0.0,
        "complete_evidence": sum(c["complete"] for c in cats.values()),
        "any_evidence": sum(c["any"] for c in cats.values()),
        "categories": {
            cat: {
                "n": c["n"],
                "evidence_recall": round(recall_sum[cat] / c["n"], 4),
                "complete_evidence": c["complete"],
                "any_evidence": c["any"],
            }
            for cat, c in sorted(cats.items())
        },
    }


def load_results(checkpoints: list[Path]) -> dict[str, list[dict[str, Any]]]:
    """Read results from MemoryBench checkpoints or candidate checkpoints, inline or sidecar."""
    out: dict[str, list[dict[str, Any]]] = {}
    for path in checkpoints:
        data = json.loads(path.read_text())
        for qid, entry in data["questions"].items():
            search = entry["phases"]["search"]
            if isinstance(search.get("results"), list):
                out[qid] = search["results"]
            else:
                out[qid] = json.loads((path.parents[3] / search["resultFile"]).read_text())[
                    "results"
                ]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--checkpoint", type=Path, action="append", required=True)
    ap.add_argument("--k", type=int, default=10)
    a = ap.parse_args()
    dataset = {str(x["question_id"]): x for x in json.loads(a.dataset.read_text())}
    ids = [str(q) for q in json.loads(a.manifest.read_text())["question_ids"]]
    print(json.dumps(score(dataset, load_results(a.checkpoint), ids, k=a.k), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
