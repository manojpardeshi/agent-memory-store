#!/usr/bin/env python3
"""Compute deterministic session-level retrieval diagnostics for LongMemEval-S."""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

if __package__:
    from scripts.verify_longmemeval_dataset import verify_dataset
else:
    from verify_longmemeval_dataset import verify_dataset


def _mean(rows: list[dict[str, Any]], name: str) -> float:
    return sum(float(row[name]) for row in rows) / len(rows)


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    return {
        "question_count": len(rows),
        "returned_result_count_mean": _mean(rows, "returned_result_count"),
        "returned_result_count_min": min(int(row["returned_result_count"]) for row in rows),
        "returned_result_count_max": max(int(row["returned_result_count"]) for row in rows),
        "hit_at_5": _mean(rows, "hit_at_5"),
        "hit_at_10": _mean(rows, "hit_at_10"),
        "answer_session_recall_at_5": _mean(rows, "answer_session_recall_at_5"),
        "answer_session_recall_at_10": _mean(rows, "answer_session_recall_at_10"),
        "mrr_at_10": _mean(rows, "mrr_at_10"),
        "result_precision_at_5": _mean(rows, "result_precision_at_5"),
        "result_precision_at_10": _mean(rows, "result_precision_at_10"),
    }


def analyze_retrieval(
    dataset: list[dict[str, Any]],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Compare retrieved session IDs with the dataset's labeled answer sessions."""
    by_id = {item.get("question_id"): item for item in dataset}
    if len(by_id) != len(dataset) or None in by_id:
        raise ValueError("dataset question IDs must be present and unique")

    target_ids = checkpoint.get("targetQuestionIds")
    questions = checkpoint.get("questions")
    if not isinstance(target_ids, list) or not target_ids:
        raise ValueError("checkpoint targetQuestionIds must be a non-empty array")
    if not isinstance(questions, dict):
        raise ValueError("checkpoint questions must be an object")

    rows: list[dict[str, Any]] = []
    for question_id in target_ids:
        item = by_id.get(question_id)
        if item is None:
            raise ValueError(f"question {question_id!r} is absent from dataset")
        answer_ids = set(item.get("answer_session_ids", []))
        session_ids = item.get("haystack_session_ids")
        if not answer_ids or not isinstance(session_ids, list):
            raise ValueError(f"question {question_id!r} has invalid answer-session labels")
        relevant = {
            index
            for index, session_id in enumerate(session_ids)
            if session_id in answer_ids
        }
        if len(relevant) != len(answer_ids):
            raise ValueError(f"question {question_id!r} has unmatched answer-session labels")

        try:
            results = questions[question_id]["phases"]["search"]["results"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"question {question_id!r} has no completed search results") from error
        if not isinstance(results, list):
            raise ValueError(f"question {question_id!r} search results must be an array")

        pattern = re.compile(rf"^{re.escape(question_id)}-session-(\d+)$")
        retrieved: list[int] = []
        for result in results[:10]:
            try:
                source_session_id = result["metadata"]["session_id"]
            except (KeyError, TypeError) as error:
                raise ValueError(
                    f"question {question_id!r} has a result without source session metadata"
                ) from error
            match = pattern.fullmatch(source_session_id)
            if match is None:
                raise ValueError(
                    f"question {question_id!r} has invalid source session {source_session_id!r}"
                )
            session_index = int(match.group(1))
            if session_index >= len(session_ids):
                raise ValueError(
                    f"question {question_id!r} references out-of-range session {session_index}"
                )
            retrieved.append(session_index)

        first_relevant_rank = next(
            (
                rank
                for rank, session_index in enumerate(retrieved, start=1)
                if session_index in relevant
            ),
            None,
        )
        retrieved_at_5 = retrieved[:5]
        retrieved_at_10 = retrieved[:10]
        rows.append(
            {
                "question_id": question_id,
                "question_type": item.get("question_type"),
                "labeled_answer_session_count": len(relevant),
                "returned_result_count": len(retrieved),
                "retrieved_distinct_answer_sessions_at_5": len(
                    relevant.intersection(retrieved_at_5)
                ),
                "retrieved_distinct_answer_sessions_at_10": len(
                    relevant.intersection(retrieved_at_10)
                ),
                "hit_at_5": float(any(index in relevant for index in retrieved_at_5)),
                "hit_at_10": float(any(index in relevant for index in retrieved_at_10)),
                "answer_session_recall_at_5": len(relevant.intersection(retrieved_at_5))
                / len(relevant),
                "answer_session_recall_at_10": len(relevant.intersection(retrieved_at_10))
                / len(relevant),
                "mrr_at_10": 0.0
                if first_relevant_rank is None
                else 1.0 / first_relevant_rank,
                "result_precision_at_5": sum(index in relevant for index in retrieved_at_5) / 5,
                "result_precision_at_10": sum(index in relevant for index in retrieved_at_10) / 10,
            }
        )

    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in rows:
        grouped[str(row["question_type"])].append(row)

    return {
        "schema_version": 1,
        "metric_scope": "deterministic session-label diagnostic; not MemoryBench LLM relevance",
        "search_depth": 10,
        "overall": _aggregate(rows),
        "categories": {
            question_type: _aggregate(grouped[question_type])
            for question_type in sorted(grouped)
        },
        "questions": rows,
    }


def merge_checkpoints(checkpoints: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine disjoint completed checkpoints for one aggregate retrieval analysis."""
    target_ids: list[str] = []
    questions: dict[str, Any] = {}
    for checkpoint in checkpoints:
        if checkpoint.get("status") != "completed":
            raise ValueError("all retrieval checkpoints must be complete")
        checkpoint_ids = checkpoint.get("targetQuestionIds")
        checkpoint_questions = checkpoint.get("questions")
        if not isinstance(checkpoint_ids, list) or not isinstance(checkpoint_questions, dict):
            raise ValueError("checkpoint has invalid target questions")
        for question_id in checkpoint_ids:
            if question_id in questions:
                raise ValueError(f"duplicate question across checkpoints: {question_id!r}")
            if question_id not in checkpoint_questions:
                raise ValueError(f"checkpoint is missing question {question_id!r}")
            target_ids.append(question_id)
            questions[question_id] = checkpoint_questions[question_id]
    return {
        "status": "completed",
        "targetQuestionIds": target_ids,
        "questions": questions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("checkpoint", nargs="+")
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args()

    verify_dataset(args.dataset)
    with Path(args.dataset).open(encoding="utf-8") as stream:
        dataset = json.load(stream)
    checkpoints = []
    for checkpoint_path in args.checkpoint:
        with Path(checkpoint_path).open(encoding="utf-8") as stream:
            checkpoints.append(json.load(stream))
    checkpoint = checkpoints[0] if len(checkpoints) == 1 else merge_checkpoints(checkpoints)
    result = analyze_retrieval(dataset, checkpoint)
    if args.aggregate_only:
        del result["questions"]
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
