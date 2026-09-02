#!/usr/bin/env python3
"""Pure selection primitives for the `within-session-expansion-v1` context policy.

Diagnosis: a retrieved answer session contributes a mean of 38% of its messages to the
context, and the aggregation components the answerer reports as missing sit in the other
62%. This policy admits more of a session the baseline already selected, then reduces
content to query-aware spans so the budget stays flat. No model in the query path.

Three invariants the contract fixes and these functions enforce:
- no new session is introduced;
- every baseline item is retained, in original rank order, as a prefix;
- byte accounting uses the identical formula the paired runner uses.
"""

from __future__ import annotations

import json
import re
from typing import Any

HEADER_PREFIX = "[longmemeval-source]"
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN = re.compile(r"[a-z0-9]+")


def context_json_bytes(results: list[dict[str, Any]]) -> int:
    """Exactly the paired runner's measurement, so budgets are comparable across runs."""
    return len(json.dumps(results, indent=2, ensure_ascii=False).encode())


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if len(t) >= 3}


def split_header(content: str) -> tuple[str, str]:
    """Separate the provenance header line from the message body. Header may be absent."""
    if content.startswith(HEADER_PREFIX) and "\n" in content:
        header, body = content.split("\n", 1)
        return header, body
    return "", content


def expand_within_sessions(
    baseline: list[dict[str, Any]],
    session_messages: dict[str, list[dict[str, Any]]],
    *,
    cap: int,
) -> list[dict[str, Any]]:
    """Select up to `cap` additional messages per baseline session, nearest to the anchor.

    The anchor is the highest-ranked baseline message of that session. Candidates are
    ordered by index distance from the anchor, ties broken by lower index. Messages already
    in the baseline are skipped. Sessions absent from the baseline are never touched.
    """
    if cap < 0:
        raise ValueError("cap must be non-negative")
    baseline_ids = {item["memory_id"] for item in baseline}
    baseline_positions: set[tuple[str, int]] = set()
    anchors: dict[str, int] = {}
    order: list[str] = []
    for item in baseline:
        meta = item.get("metadata") or {}
        session_id, index = meta.get("session_id"), meta.get("message_index")
        if not isinstance(session_id, str) or not isinstance(index, int):
            raise ValueError("baseline item lacks session_id or integer message_index")
        baseline_positions.add((session_id, index))
        if session_id not in anchors:
            anchors[session_id] = index
            order.append(session_id)

    expansions: list[dict[str, Any]] = []
    for session_id in order:
        anchor = anchors[session_id]
        pool = [
            m
            for m in session_messages.get(session_id, [])
            if m["memory_id"] not in baseline_ids
            and isinstance((m.get("metadata") or {}).get("message_index"), int)
            # A baseline message is never re-admitted, even if its id differed.
            and (session_id, m["metadata"]["message_index"]) not in baseline_positions
        ]
        pool.sort(
            key=lambda m: (
                abs(m["metadata"]["message_index"] - anchor),
                m["metadata"]["message_index"],
            )
        )
        for m in pool[:cap]:
            chosen = dict(m)
            chosen["expansion"] = {
                "policy": "within-session-expansion-v1",
                "anchor_message_index": anchor,
                "distance": abs(m["metadata"]["message_index"] - anchor),
            }
            expansions.append(chosen)
    return expansions


def reduce_to_span(content: str, query: str, *, max_body_chars: int) -> str:
    """Keep the header; reduce the body to the query-densest window within the char cap.

    Deterministic and model-free. The best-overlap sentence is chosen first, then
    neighbours are added alternately on each side until the cap would be exceeded.
    Returns the input unchanged when the body already fits.
    """
    if max_body_chars <= 0:
        raise ValueError("max_body_chars must be positive")
    header, body = split_header(content)
    if len(body) <= max_body_chars:
        return content
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(body) if s.strip()]
    if not sentences:
        return f"{header}\n{body[:max_body_chars]}" if header else body[:max_body_chars]
    q = _tokens(query)
    scores = [len(q & _tokens(s)) for s in sentences]
    best = max(range(len(sentences)), key=lambda i: (scores[i], -i))
    lo = hi = best
    length = len(sentences[best])
    grow_left = True
    while True:
        moved = False
        if grow_left and lo > 0 and length + 1 + len(sentences[lo - 1]) <= max_body_chars:
            lo -= 1
            length += 1 + len(sentences[lo])
            moved = True
        elif hi + 1 < len(sentences) and length + 1 + len(sentences[hi + 1]) <= max_body_chars:
            hi += 1
            length += 1 + len(sentences[hi])
            moved = True
        grow_left = not grow_left
        if not moved:
            # try the other side once before giving up
            if lo > 0 and length + 1 + len(sentences[lo - 1]) <= max_body_chars:
                lo -= 1
                length += 1 + len(sentences[lo])
            elif hi + 1 < len(sentences) and length + 1 + len(sentences[hi + 1]) <= max_body_chars:
                hi += 1
                length += 1 + len(sentences[hi])
            else:
                break
    span = " ".join(sentences[lo : hi + 1])
    if len(span) > max_body_chars:
        span = span[:max_body_chars]
    if lo > 0:
        span = "… " + span
    if hi + 1 < len(sentences):
        span = span + " …"
    return f"{header}\n{span}" if header else span


def _with_body(item: dict[str, Any], content: str) -> dict[str, Any]:
    out = dict(item)
    out["content"] = content
    out["memory"] = content
    return out


def fit_to_budget(
    baseline: list[dict[str, Any]],
    expansions: list[dict[str, Any]],
    query: str,
    *,
    budget_bytes: int,
    floor_body_chars: int,
    reduce_baseline: bool,
) -> list[dict[str, Any]]:
    """Return baseline + expansions within `budget_bytes`, reducing before dropping.

    Order of sacrifice: expansion bodies (largest first) down to the floor; then, only if
    `reduce_baseline`, baseline bodies (largest first) down to the floor; then expansions
    dropped from the tail. Baseline items are never dropped and never reordered.
    """
    if floor_body_chars <= 0:
        raise ValueError("floor_body_chars must be positive")
    base = list(baseline)
    exp = list(expansions)

    def total() -> int:
        return context_json_bytes(base + exp)

    if total() <= budget_bytes:
        return base + exp

    def shrink(items: list[dict[str, Any]]) -> bool:
        """Reduce the largest not-yet-floored body by one step; True if anything changed."""
        order = sorted(
            range(len(items)),
            key=lambda i: -len(split_header(items[i]["content"])[1]),
        )
        for i in order:
            body = split_header(items[i]["content"])[1]
            if len(body) <= floor_body_chars:
                continue
            target = max(floor_body_chars, len(body) // 2)
            reduced = reduce_to_span(items[i]["content"], query, max_body_chars=target)
            items[i] = _with_body(items[i], reduced)
            return True
        return False

    while total() > budget_bytes and shrink(exp):
        pass
    while total() > budget_bytes and reduce_baseline and shrink(base):
        pass
    while total() > budget_bytes and exp:
        exp.pop()
    return base + exp
