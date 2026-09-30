#!/usr/bin/env python3
"""event-date-annotation-v1: attach resolved event dates to user messages already in context.

Ranking, selection, order, and every message body are untouched. The only change is an extra
`event_dates` field on eligible items, so the answering model sees "2023-05-23 (last Tuesday)"
instead of having to compute it. Guided by the measured precision sample in
`docs/architecture/benchmarks/2026-09-30-event-date-resolver-coverage.md`:

- user messages only, because assistant text produced most correct-but-useless matches;
- bare "today" is skipped, the most frequent match and mostly meaning "nowadays".
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from llm_memory_store.temporal import resolve_event_dates

HEADER_PREFIX = "[longmemeval-source]"
EXCLUDED_EXPRESSIONS = frozenset({"today"})


def _header_and_body(content: str) -> tuple[dict[str, Any] | None, str]:
    if content.startswith(HEADER_PREFIX) and "\n" in content:
        header, body = content.split("\n", 1)
        try:
            return json.loads(header[len(HEADER_PREFIX) :]), body
        except json.JSONDecodeError:
            return None, content
    return None, content


def _reference_date(item: dict[str, Any], header: dict[str, Any] | None) -> date | None:
    raw = (item.get("metadata") or {}).get("session_date") or (header or {}).get("date")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def annotate_event_dates(results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Return a copy of `results` with `event_dates` on eligible user items, and a count."""
    out: list[dict[str, Any]] = []
    annotated = 0
    for item in results:
        header, body = _header_and_body(str(item.get("content", "")))
        role = (header or {}).get("role")
        reference = _reference_date(item, header)
        entries: list[str] = []
        if role == "user" and reference is not None:
            for event in resolve_event_dates(body, reference):
                if event.expression.strip().lower() in EXCLUDED_EXPRESSIONS:
                    continue
                span = (
                    str(event.start) if event.start == event.end else f"{event.start}..{event.end}"
                )
                entries.append(f"{span} ({event.expression.strip()})")
        if entries:
            copy = dict(item)
            copy["event_dates"] = entries
            out.append(copy)
            annotated += 1
        else:
            out.append(item)
    return out, annotated
