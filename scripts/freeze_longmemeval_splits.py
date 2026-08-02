#!/usr/bin/env python3
"""Freeze development, validation, and reserve LongMemEval-S question manifests."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
from typing import Any

if __package__:
    from scripts.verify_longmemeval_dataset import EXPECTED_SHA256, verify_dataset
else:
    from verify_longmemeval_dataset import EXPECTED_SHA256, verify_dataset

SEED = "longmemeval-kimi-evaluation-splits-v1"
MEMORYBENCH_COMMIT = "118209a746d97d0d85e5a7234267f0b6962857e9"
SPLIT_COUNTS = {
    "development-complement": {
        "single-session-preference": 5,
        "single-session-user": 16,
        "multi-session": 34,
        "temporal-reasoning": 34,
        "knowledge-update": 19,
        "single-session-assistant": 12,
    },
    "validation": {
        "single-session-preference": 7,
        "single-session-user": 20,
        "multi-session": 42,
        "temporal-reasoning": 42,
        "knowledge-update": 23,
        "single-session-assistant": 16,
    },
    "reserve": {
        "single-session-preference": 8,
        "single-session-user": 24,
        "multi-session": 47,
        "temporal-reasoning": 47,
        "knowledge-update": 26,
        "single-session-assistant": 18,
    },
}
QUALIFICATION_COUNTS = {
    "single-session-preference": 4,
    "single-session-user": 4,
    "multi-session": 3,
    "temporal-reasoning": 3,
    "knowledge-update": 3,
    "single-session-assistant": 3,
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _rank(question_type: str, question_id: str) -> bytes:
    return hashlib.sha256(f"{SEED}\0{question_type}\0{question_id}".encode()).digest()


def split_complement(
    dataset: list[dict[str, Any]],
    observed_ids: set[str],
    question_type_order: list[str],
) -> dict[str, list[str]]:
    by_type: dict[str, list[str]] = collections.defaultdict(list)
    dataset_ids: set[str] = set()
    for item in dataset:
        question_id = item.get("question_id")
        question_type = item.get("question_type")
        if not isinstance(question_id, str) or not isinstance(question_type, str):
            raise ValueError("dataset questions must have string IDs and types")
        if question_id in dataset_ids:
            raise ValueError(f"duplicate dataset question ID: {question_id}")
        dataset_ids.add(question_id)
        if question_id not in observed_ids:
            by_type[question_type].append(question_id)

    if not observed_ids.issubset(dataset_ids):
        raise ValueError("observed manifest contains IDs absent from the dataset")
    if set(question_type_order) != set(SPLIT_COUNTS["validation"]):
        raise ValueError("question type order does not match frozen allocation")

    result = {name: [] for name in SPLIT_COUNTS}
    for question_type in question_type_order:
        ranked = sorted(by_type[question_type], key=lambda value: _rank(question_type, value))
        offset = 0
        for split_name, allocation in SPLIT_COUNTS.items():
            count = allocation[question_type]
            result[split_name].extend(ranked[offset : offset + count])
            offset += count
        if offset != len(ranked):
            raise ValueError(
                f"frozen allocation does not cover {question_type}: {offset} != {len(ranked)}"
            )
    return result


def _counts(
    question_ids: list[str],
    question_types: dict[str, str],
) -> dict[str, int]:
    counts = collections.Counter(question_types[question_id] for question_id in question_ids)
    return dict(sorted(counts.items()))


def freeze_manifests(
    dataset_path: Path,
    observed_path: Path,
) -> dict[str, dict[str, Any]]:
    verify_dataset(dataset_path)
    with dataset_path.open(encoding="utf-8") as stream:
        dataset = json.load(stream)
    with observed_path.open(encoding="utf-8") as stream:
        observed = json.load(stream)

    observed_ids = observed.get("question_ids")
    question_type_order = observed.get("question_type_order")
    if not isinstance(observed_ids, list) or len(observed_ids) != 60:
        raise ValueError("observed manifest must contain exactly 60 question IDs")
    if len(set(observed_ids)) != len(observed_ids):
        raise ValueError("observed question IDs must be unique")
    if not isinstance(question_type_order, list):
        raise ValueError("observed question type order must be an array")

    complement = split_complement(dataset, set(observed_ids), question_type_order)
    question_types = {item["question_id"]: item["question_type"] for item in dataset}
    development_ids = observed_ids + complement["development-complement"]
    complement_ids = (
        complement["development-complement"]
        + complement["validation"]
        + complement["reserve"]
    )
    observed_by_type: dict[str, list[str]] = collections.defaultdict(list)
    for question_id in observed_ids:
        observed_by_type[question_types[question_id]].append(question_id)
    qualification_ids = []
    for question_type in question_type_order:
        ranked = sorted(
            observed_by_type[question_type],
            key=lambda value: _rank(f"qualification-{question_type}", value),
        )
        qualification_ids.extend(ranked[: QUALIFICATION_COUNTS[question_type]])
    base = {
        "schema_version": 1,
        "dataset_sha256": EXPECTED_SHA256,
        "memorybench_commit": MEMORYBENCH_COMMIT,
        "partition_seed": SEED,
        "observed_selection_sha256": file_sha256(observed_path),
        "question_type_order": question_type_order,
    }
    return {
        "development": {
            **base,
            "split_id": "longmemeval-kimi-development180-v1",
            "role": "development",
            "sealed": False,
            "observed_question_count": 60,
            "complement_question_count": 120,
            "question_count": len(development_ids),
            "question_type_counts": _counts(development_ids, question_types),
            "question_ids": development_ids,
        },
        "validation": {
            **base,
            "split_id": "longmemeval-kimi-validation150-v1",
            "role": "sealed-validation",
            "sealed": True,
            "question_count": len(complement["validation"]),
            "question_type_counts": _counts(complement["validation"], question_types),
            "question_ids": complement["validation"],
        },
        "reserve": {
            **base,
            "split_id": "longmemeval-kimi-reserve170-v1",
            "role": "sealed-competitor-reserve",
            "sealed": True,
            "question_count": len(complement["reserve"]),
            "question_type_counts": _counts(complement["reserve"], question_types),
            "question_ids": complement["reserve"],
        },
        "complement": {
            **base,
            "split_id": "longmemeval-kimi-complement440-v1",
            "role": "local-retrieval-complement",
            "sealed": False,
            "contains_sealed_question_ids": True,
            "question_count": len(complement_ids),
            "question_type_counts": _counts(complement_ids, question_types),
            "question_ids": complement_ids,
        },
        "qualification": {
            **base,
            "split_id": "longmemeval-kimi-qualification20-v1",
            "role": "evaluator-qualification",
            "sealed": False,
            "source_run_id": "llm-memory-store-longmemeval-stratified60-v1",
            "question_count": len(qualification_ids),
            "question_type_counts": _counts(qualification_ids, question_types),
            "question_ids": qualification_ids,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("observed_manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()

    manifests = freeze_manifests(args.dataset, args.observed_manifest)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    for name, manifest in manifests.items():
        output = args.output_directory / f"longmemeval-kimi-{name}-v1.json"
        output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"{name}: {output} ({manifest['question_count']} questions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
