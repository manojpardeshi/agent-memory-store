"""Validate the two independently authored halves of retrieval-v3 and build the frozen corpus.

Each author wrote 30 memory/question pairs from `retrieval_v3_authoring/AUTHOR-SPEC.md` without
seeing the other's work, any repository code, or any retrieval candidate. This script enforces
the specification mechanically, then assembles the corpus with the same scope, distractor and
inaccessible-control construction as retrieval-v2. Question styles are kept in a sidecar file so
the corpus itself stays in the standard evaluation schema.
"""

# ruff: noqa: E501 -- authored word lists and report rows stay on one line.

from __future__ import annotations

import collections
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
AUTHORING = HERE / "retrieval_v3_authoring"
OUTPUT = HERE / "retrieval_v3.json"
STYLES = HERE / "retrieval_v3_styles.json"
KINDS = ("turn", "fact", "preference", "summary", "event")

# Function words a paraphrase question may share with its memory (the spec's "the, what, did, is").
FUNCTION_WORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "has",
        "have",
        "having",
        "he",
        "her",
        "here",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "itself",
        "just",
        "me",
        "more",
        "most",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "that",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "yours",
        "yourself",
        "yourselves",
        "any",
        "anything",
        "something",
        "there's",
        "what's",
        "who's",
        "i'm",
        "it's",
        "we're",
        "they're",
        "don't",
        "didn't",
        "doesn't",
        "isn't",
        "wasn't",
        "weren't",
        "won't",
        "can't",
        "get",
        "got",
        "ever",
        "also",
        "us",
        "one",
        "ones",
    ]
)
SCOPES = {
    "author-a": {
        "kind": "private",
        "subject": "eval-v3",
        "environment": "independent-evaluation",
        "owner": "photographer-assistant",
    },
    "author-b": {
        "kind": "private",
        "subject": "eval-v3",
        "environment": "independent-evaluation",
        "owner": "household-assistant",
    },
}
SHARED_SCOPE = {
    "kind": "shared",
    "subject": "eval-v3",
    "environment": "independent-evaluation",
    "owner": "garden-coop",
}
PREFIX = {"author-a": "a", "author-b": "b"}


def content_words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in FUNCTION_WORDS and len(w) > 1
    }


def related(a: str, b: str) -> bool:
    """Same word or an inflection/derivation of it (shared stem of at least five letters)."""
    if a == b:
        return True
    stem = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        stem += 1
    return stem >= 5 or (stem >= 4 and min(len(a), len(b)) <= 5)


def validate(half: dict, label: str) -> list[str]:
    problems: list[str] = []
    items = half["items"]
    if half.get("author") != label:
        problems.append(f"{label}: author label is {half.get('author')!r}")
    if [i["local_id"] for i in items] != list(range(1, 31)):
        problems.append(f"{label}: local_id must run 1..30 in order")
    for item in items:
        expected_pool = "private" if item["local_id"] <= 20 else "shared"
        if item["pool"] != expected_pool:
            problems.append(f"{label}#{item['local_id']}: pool should be {expected_pool}")
        if item["kind"] not in KINDS:
            problems.append(f"{label}#{item['local_id']}: unknown kind {item['kind']!r}")
        if (item["kind"] == "turn") != ("role" in item):
            problems.append(f"{label}#{item['local_id']}: role must be present only for turns")
        if item.get("role") not in (None, "user", "assistant"):
            problems.append(f"{label}#{item['local_id']}: bad role {item['role']!r}")
        if (item["style"] == "anchor") != ("anchor_token" in item):
            problems.append(f"{label}#{item['local_id']}: anchor_token only for anchor items")
    kinds = collections.Counter(i["kind"] for i in items)
    if any(kinds[k] != 6 for k in KINDS):
        problems.append(f"{label}: kind counts {dict(kinds)} (need 6 each)")
    styles = collections.Counter(i["style"] for i in items)
    if styles != {"anchor": 15, "paraphrase": 15}:
        problems.append(f"{label}: style counts {dict(styles)} (need 15 each)")
    if {i["role"] for i in items if i["kind"] == "turn"} != {"user", "assistant"}:
        problems.append(f"{label}: turns must use both roles")
    for item in items:
        tag = f"{label}#{item['local_id']}"
        if item["style"] == "anchor":
            token = item["anchor_token"].lower()
            if token not in item["content"].lower():
                problems.append(f"{tag}: anchor {token!r} not in its memory")
            if token not in item["query"].lower():
                problems.append(f"{tag}: anchor {token!r} not in its question")
        else:
            shared = sorted(
                f"{q}~{m}"
                for q in content_words(item["query"])
                for m in content_words(item["content"])
                if related(q, m)
            )
            if shared:
                problems.append(f"{tag}: paraphrase shares content words {shared}")
    return problems


def cross_validate(halves: dict[str, dict]) -> list[str]:
    """Anchor tokens must be unique among every memory a question can reach."""
    problems: list[str] = []
    shared = [i for h in halves.values() for i in h["items"] if i["pool"] == "shared"]
    for label, half in halves.items():
        reachable = [i for i in half["items"] if i["pool"] == "private"] + shared
        for item in half["items"]:
            if item["style"] != "anchor":
                continue
            token = item["anchor_token"].lower()
            holders = [i for i in reachable if token in i["content"].lower()]
            if item["pool"] == "shared":
                holders = [
                    i
                    for h in halves.values()
                    for i in h["items"]
                    if i["pool"] == "shared" and token in i["content"].lower()
                ]
            if len(holders) != 1:
                problems.append(
                    f"{label}#{item['local_id']}: anchor {token!r} appears in "
                    f"{len(holders)} reachable memories"
                )
    return problems


def build(halves: dict[str, dict]) -> tuple[dict, dict]:
    memories: list[dict] = []
    queries: list[dict] = []
    styles: dict[str, str] = {}
    private = {
        label: [i for i in h["items"] if i["pool"] == "private"] for label, h in halves.items()
    }
    shared = [
        (label, i) for label, h in halves.items() for i in h["items"] if i["pool"] == "shared"
    ]
    other = {"author-a": "author-b", "author-b": "author-a"}

    def fixture_id(label: str, index: int) -> str:
        return f"{PREFIX[label]}{index + 1:02d}"

    for label, items in private.items():
        for index, item in enumerate(items):
            memory = {
                "fixture_id": fixture_id(label, index),
                "kind": item["kind"],
                "content": item["content"],
                "scope": SCOPES[label],
            }
            if "role" in item:
                memory["role"] = item["role"]
            memories.append(memory)
    for index, (_, item) in enumerate(shared):
        memory = {
            "fixture_id": f"s{index + 1:02d}",
            "kind": item["kind"],
            "content": item["content"],
            "scope": SHARED_SCOPE,
        }
        if "role" in item:
            memory["role"] = item["role"]
        memories.append(memory)

    for label, items in private.items():
        for index, item in enumerate(items):
            query_id = f"q{PREFIX[label]}{index + 1:02d}"
            queries.append(
                {
                    "query_id": query_id,
                    "query": item["query"],
                    "private_scope": SCOPES[label],
                    "shared_pools": [],
                    "expected_fixture_ids": [fixture_id(label, index)],
                    "distractor_fixture_ids": [fixture_id(label, (index + 7) % len(items))],
                    "inaccessible_fixture_ids": [fixture_id(other[label], index)],
                }
            )
            styles[query_id] = item["style"]
    for index, (_label, item) in enumerate(shared):
        query_id = f"qs{index + 1:02d}"
        # Alternate the asking scope; the other private scope is the inaccessible control.
        asker = "author-a" if index % 2 == 0 else "author-b"
        queries.append(
            {
                "query_id": query_id,
                "query": item["query"],
                "private_scope": SCOPES[asker],
                "shared_pools": ["garden-coop"],
                "expected_fixture_ids": [f"s{index + 1:02d}"],
                "distractor_fixture_ids": [f"s{(index + 7) % len(shared) + 1:02d}"],
                "inaccessible_fixture_ids": [fixture_id(other[asker], index % 20)],
            }
        )
        styles[query_id] = item["style"]

    corpus = {
        "schema_version": 1,
        "dataset_id": "independent-retrieval-v3",
        "description": (
            "Two-author blind synthetic corpus: a wildlife photographer's assistant, a household "
            "renovation assistant, and a shared community-garden pool. Half the questions repeat "
            "one distinctive word from their memory; half share no content word with it. No "
            "user-derived data; frozen before any retrieval evaluation."
        ),
        "distractor_policy": (
            "Each query preselects one accessible non-answer seven positions later in the same "
            "pool; shared queries alternate asking scope. Each also names one inaccessible "
            "control from the other private scope."
        ),
        "top_k": 5,
        "thresholds": {
            "query_count_min": 60,
            "memory_kind_count_min": 12,
            "recall_at_k_min": 0.9,
            "mrr_min": 0.85,
            "distractor_leak_rate_max": 0.1,
            "scope_violation_count_max": 0,
            "runtime_seconds_max": 60,
        },
        "memories": memories,
        "queries": queries,
    }
    return corpus, {"dataset_id": corpus["dataset_id"], "query_styles": styles}


def main() -> int:
    halves = {
        label: json.loads((AUTHORING / f"{label}.json").read_text(encoding="utf-8"))
        for label in ("author-a", "author-b")
    }
    problems = [p for label, half in halves.items() for p in validate(half, label)]
    problems += cross_validate(halves)
    if problems:
        print("\n".join(problems))
        return 1
    corpus, styles = build(halves)
    OUTPUT.write_text(json.dumps(corpus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    STYLES.write_text(json.dumps(styles, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {OUTPUT.name}: {len(corpus['memories'])} memories, {len(corpus['queries'])} queries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
