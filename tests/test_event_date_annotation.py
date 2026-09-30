"""event-date-annotation-v1 changes nothing but an added field on eligible user items."""

from __future__ import annotations

import json

from scripts.event_date_annotation import annotate_event_dates


def _item(role: str, body: str, date: str = "2023-05-30T10:00:00.000Z") -> dict:
    header = json.dumps({"date": date, "role": role, "session_id": "q-session-1"})
    content = f"[longmemeval-source]{header}\n{body}"
    return {"memory_id": f"{role}-{len(body)}", "content": content, "memory": content,
            "metadata": {"session_date": date, "session_id": "q-session-1"}}


def test_user_items_gain_resolved_dates_and_nothing_else_changes() -> None:
    items = [_item("user", "I saw the dentist last Tuesday."), _item("assistant", "Noted.")]
    out, count = annotate_event_dates(items)
    assert count == 1
    assert out[0]["event_dates"] == ["2023-05-23 (last Tuesday)"]
    assert {k: v for k, v in out[0].items() if k != "event_dates"} == items[0]
    assert out[1] is items[1]
    assert [i["memory_id"] for i in out] == [i["memory_id"] for i in items]


def test_assistant_text_is_never_annotated() -> None:
    out, count = annotate_event_dates([_item("assistant", "Your trip is next Friday.")])
    assert count == 0 and "event_dates" not in out[0]


def test_bare_today_is_skipped_but_other_expressions_kept() -> None:
    out, _ = annotate_event_dates([_item("user", "Today I booked it; the show was 3 weeks ago.")])
    assert out[0]["event_dates"] == ["2023-05-09 (3 weeks ago)"]


def test_ranges_render_with_both_ends() -> None:
    out, _ = annotate_event_dates([_item("user", "We moved house last week.")])
    assert out[0]["event_dates"] == ["2023-05-22..2023-05-28 (last week)"]


def test_items_without_header_or_date_pass_through() -> None:
    raw = {"memory_id": "x", "content": "last Tuesday", "metadata": {}}
    out, count = annotate_event_dates([raw])
    assert count == 0 and out[0] is raw
