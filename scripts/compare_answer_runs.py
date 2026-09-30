#!/usr/bin/env python3
"""Compare two kimi answer reports on the questions they share.

Reports per-category accuracy for each arm and paired outcomes (both right, only A, only B,
both wrong) with an exact two-sided sign test on the discordant pairs. Questions listed in a
design-blind manifest contribute to every aggregate but are never printed individually, so the
tool cannot be used to read held-out failures one by one.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
from pathlib import Path
from typing import Any


def _labels(report: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {
        qid: (entry["question_type"], entry["label"])
        for qid, entry in report["questions"].items()
        if "label" in entry
    }


def sign_test_p(only_a: int, only_b: int) -> float:
    """Exact two-sided binomial sign test on discordant pairs (p=0.5)."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def compare(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    design_blind: set[str] = frozenset(),
    only: set[str] | None = None,
) -> dict[str, Any]:
    la, lb = _labels(a), _labels(b)
    shared = sorted(set(la) & set(lb) & (only if only is not None else set(la)))
    cats: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    paired = collections.Counter()
    visible_discordant: list[dict[str, str]] = []
    for qid in shared:
        category = la[qid][0]
        ra, rb = la[qid][1] == "correct", lb[qid][1] == "correct"
        cats[category]["n"] += 1
        cats[category]["a"] += ra
        cats[category]["b"] += rb
        key = {
            (True, True): "both",
            (True, False): "only_a",
            (False, True): "only_b",
            (False, False): "neither",
        }[(ra, rb)]
        paired[key] += 1
        cats[category][key] += 1
        if key in ("only_a", "only_b") and qid not in design_blind:
            visible_discordant.append({"question_id": qid, "category": category, "winner": key})
    blind_discordant = sum(
        1
        for qid in shared
        if qid in design_blind and (la[qid][1] == "correct") != (lb[qid][1] == "correct")
    )
    return {
        "shared_questions": len(shared),
        "arm_a_correct": sum(c["a"] for c in cats.values()),
        "arm_b_correct": sum(c["b"] for c in cats.values()),
        "paired": dict(paired),
        "sign_test_p": sign_test_p(paired["only_a"], paired["only_b"]),
        "categories": {k: dict(v) for k, v in sorted(cats.items())},
        "visible_discordant": visible_discordant,
        "design_blind_discordant_count_only": blind_discordant,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", type=Path, required=True, help="reference arm, e.g. the store baseline")
    ap.add_argument("--b", type=Path, required=True, help="comparison arm")
    ap.add_argument("--design-blind", type=Path)
    ap.add_argument("--only", type=Path, help="manifest restricting the comparison")
    args = ap.parse_args()
    blind = (
        set(json.loads(args.design_blind.read_text())["question_ids"])
        if args.design_blind
        else set()
    )
    only = set(json.loads(args.only.read_text())["question_ids"]) if args.only else None
    result = compare(
        json.loads(args.a.read_text()),
        json.loads(args.b.read_text()),
        design_blind=blind,
        only=only,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
