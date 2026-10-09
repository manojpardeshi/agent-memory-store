#!/usr/bin/env python3
"""Score answer-content presence in retrieved context for provenance-incomparable arms.

The deterministic session-label diagnostic cannot compare a raw-message store against an
extractive memory system: Mem0 rewrites a memory's source metadata when a later ingest
call updates it, so retrieved provenance no longer identifies the originating session.
This scorer ignores provenance entirely and asks one question of both arms under one code
path: does the retrieved context actually contain the gold answer text?

It is a lexical proxy, not a judge. It cannot credit a correct paraphrase, so treat it as
a floor on answer availability rather than a measure of answer quality.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any

MIN_TOKEN_LENGTH = 3
OVERLAP_THRESHOLD = 0.8
SHORT_ANSWER_TOKENS = 2


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", str(text).lower())


def content_tokens(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > MIN_TOKEN_LENGTH - 1}


def answer_present(gold: str, haystack: str) -> bool:
    """Exact containment for very short answers, token overlap otherwise."""
    tokens = content_tokens(gold)
    if len(tokens) <= SHORT_ANSWER_TOKENS:
        return normalize(gold).strip() in haystack
    return sum(1 for token in tokens if token in haystack) / len(tokens) >= OVERLAP_THRESHOLD


def store_context(entry: dict[str, Any]) -> str:
    """Concatenate retrieved raw-message bodies, dropping the source-metadata header line."""
    parts = []
    for result in entry["phases"]["search"]["results"][:10]:
        content = str(result.get("content", ""))
        # The adapter prefixes each memory with a [longmemeval-source]{...} JSON header.
        # It carries no answer text, so excluding it avoids crediting incidental matches.
        body = content.split("\n", 1)[1] if content.startswith("[longmemeval-source]") else content
        parts.append(body)
    return normalize(" ".join(parts))


def mem0_context(entry: dict[str, Any]) -> str:
    results = entry.get("phases", {}).get("search", {}).get("results", [])
    return normalize(" ".join(str(r.get("memory") or "") for r in results[:10]))


def _supermemory_text(results: list[dict[str, Any]]) -> str:
    """The text MemoryBench's Supermemory prompt shows the answerer: memories plus raw chunks."""
    parts = [str(r.get("memory") or "") for r in results]
    for r in results:
        parts.extend(str(c.get("content") or "") for c in r.get("chunks") or [])
        if isinstance(r.get("chunk"), str):
            parts.append(r["chunk"])
    return " ".join(parts)


def supermemory_context_top10(entry: dict[str, Any]) -> str:
    """Supermemory at the store's depth: the first ten results, with their chunks."""
    results = entry.get("phases", {}).get("search", {}).get("results", [])
    return normalize(_supermemory_text(results[:10]))


def supermemory_context_full(entry: dict[str, Any]) -> str:
    """Supermemory's MemoryBench default: every returned result (up to 30), with chunks."""
    results = entry.get("phases", {}).get("search", {}).get("results", [])
    return normalize(_supermemory_text(results))


def context_characters(entry: dict[str, Any], extractor) -> int:
    return len(extractor(entry))


def score(
    checkpoint: dict[str, Any],
    gold: dict[str, dict[str, str]],
    extractor,
) -> dict[str, Any]:
    hits: collections.Counter[str] = collections.Counter()
    totals: collections.Counter[str] = collections.Counter()
    misses: list[str] = []
    for question_id, meta in gold.items():
        entry = checkpoint["questions"].get(question_id)
        if entry is None:
            raise ValueError(f"checkpoint is missing question {question_id!r}")
        category = meta["question_type"]
        totals[category] += 1
        if answer_present(meta["answer"], extractor(entry)):
            hits[category] += 1
        else:
            misses.append(question_id)
    total = sum(totals.values())
    return {
        "overall": {"hits": sum(hits.values()), "total": total,
                    "rate": round(sum(hits.values()) / total, 4)},
        "categories": {
            category: {"hits": hits[category], "total": totals[category]}
            for category in sorted(totals)
        },
        "missed_question_ids": misses,
        "context_characters_median": sorted(
            context_characters(checkpoint["questions"][q], extractor) for q in gold
        )[len(gold) // 2],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--store-checkpoint", type=Path, required=True)
    parser.add_argument("--mem0-checkpoint", type=Path)
    parser.add_argument("--mem0-label", default="mem0-oss-local-llama3.1-8b")
    parser.add_argument("--supermemory-checkpoint", type=Path)
    parser.add_argument("--supermemory-label", default="supermemory-local")
    args = parser.parse_args()

    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    store = json.loads(args.store_checkpoint.read_text(encoding="utf-8"))
    arms = {"llm-memory-store-raw": score(store, gold, store_context)}
    if args.mem0_checkpoint:
        mem0 = json.loads(args.mem0_checkpoint.read_text(encoding="utf-8"))
        arms[args.mem0_label] = score(mem0, gold, mem0_context)
    if args.supermemory_checkpoint:
        sm = json.loads(args.supermemory_checkpoint.read_text(encoding="utf-8"))
        arms[f"{args.supermemory_label}-top10"] = score(sm, gold, supermemory_context_top10)
        arms[f"{args.supermemory_label}-full"] = score(sm, gold, supermemory_context_full)

    report = {
        "schema_version": 1,
        "metric": "answer-content presence in top-10 retrieved context",
        "metric_scope": (
            "lexical proxy, provenance-free; a floor on answer availability, not a judge "
            "and not an answer-quality score"
        ),
        "criterion": {
            "min_token_length": MIN_TOKEN_LENGTH,
            "overlap_threshold": OVERLAP_THRESHOLD,
            "short_answer_exact_containment_at_or_below_tokens": SHORT_ANSWER_TOKENS,
        },
        "question_count": len(gold),
        "arms": arms,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
