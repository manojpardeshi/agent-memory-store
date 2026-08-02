#!/usr/bin/env python3
"""Verify the frozen LongMemEval-S input before a competitive benchmark run."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path

EXPECTED_BYTES = 277_383_467
EXPECTED_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"
EXPECTED_COUNTS = {
    "knowledge-update": 78,
    "multi-session": 133,
    "single-session-assistant": 56,
    "single-session-preference": 30,
    "single-session-user": 70,
    "temporal-reasoning": 133,
}


def verify_dataset(path: str | Path) -> dict[str, object]:
    source = Path(path)
    size = source.stat().st_size
    if size != EXPECTED_BYTES:
        raise ValueError(f"dataset byte size mismatch: expected {EXPECTED_BYTES}, got {size}")
    digest_value = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest_value.update(chunk)
    digest = digest_value.hexdigest()
    if digest != EXPECTED_SHA256:
        raise ValueError(f"dataset SHA-256 mismatch: expected {EXPECTED_SHA256}, got {digest}")
    with source.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, list):
        raise ValueError("dataset root must be an array")
    counts = dict(sorted(collections.Counter(item.get("question_type") for item in value).items()))
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"dataset question categories mismatch: {counts}")
    return {
        "bytes": size,
        "question_count": len(value),
        "question_type_counts": counts,
        "sha256": digest,
        "verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    args = parser.parse_args()
    print(json.dumps(verify_dataset(args.dataset), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
