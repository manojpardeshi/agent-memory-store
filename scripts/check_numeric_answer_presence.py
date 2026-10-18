#!/usr/bin/env python3
"""Sensitivity check for the lexical answer-presence metric: also require the gold answer's numbers.

The frozen metric (`score_content_answer_presence.py`) accepts a long answer when 80% of its words
appear in the retrieved text. LongMemEval temporal answers such as "26 days. 27 days (including the
last day) is also acceptable" are mostly filler words, which a long context can match by chance
without containing the number. This check keeps the frozen rule and additionally requires every
number in the answer's first sentence to appear as a word. It only ever removes hits.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

if __package__:
    from scripts.score_content_answer_presence import (
        answer_present,
        store_context,
        supermemory_context_full,
        supermemory_context_top10,
    )
else:
    from score_content_answer_presence import (
        answer_present,
        store_context,
        supermemory_context_full,
        supermemory_context_top10,
    )


def answer_numbers(answer: str) -> list[str]:
    first = re.split(r"(?<=\D)\.\s", str(answer))[0]
    return re.findall(r"\b\d+(?:\.\d+)?\b", first)


def number_checked(answer: str, haystack: str) -> bool:
    if not answer_present(answer, haystack):
        return False
    return all(re.search(r"\b" + re.escape(n) + r"\b", haystack) for n in answer_numbers(answer))


def sign_test(a: int, b: int) -> float:
    n = a + b
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(0, min(a, b) + 1)) / 2**n)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--store-checkpoint", type=Path, required=True)
    parser.add_argument("--supermemory-checkpoint", type=Path, required=True)
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text())
    store = json.loads(args.store_checkpoint.read_text())["questions"]
    sm = json.loads(args.supermemory_checkpoint.read_text())["questions"]
    arms = {
        "llm-memory-store-raw": (store, store_context),
        "supermemory-local-top10": (sm, supermemory_context_top10),
        "supermemory-local-full": (sm, supermemory_context_full),
    }
    hits = {
        arm: {q: number_checked(gold[q]["answer"], fn(src[q])) for q in gold}
        for arm, (src, fn) in arms.items()
    }
    categories = sorted({meta["question_type"] for meta in gold.values()})
    report = {
        "metric": "frozen answer-content presence plus every number in the answer's first sentence",
        "arms": {
            arm: {
                "hits": sum(h.values()),
                "total": len(gold),
                "categories": {
                    c: sum(v for q, v in h.items() if gold[q]["question_type"] == c)
                    for c in categories
                },
            }
            for arm, h in hits.items()
        },
        "paired_vs_store": {},
    }
    s = hits["llm-memory-store-raw"]
    for other in ("supermemory-local-top10", "supermemory-local-full"):
        o = hits[other]
        a = sum(s[q] and not o[q] for q in gold)
        b = sum(o[q] and not s[q] for q in gold)
        report["paired_vs_store"][other] = {
            "store_only": a,
            "other_only": b,
            "sign_test_p": sign_test(a, b),
        }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
