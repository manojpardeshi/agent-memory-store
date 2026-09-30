"""Event-date resolution against a fixed reference: Tuesday 30 May 2023."""

from __future__ import annotations

from datetime import date

import pytest

from llm_memory_store.temporal import resolve_event_dates

REF = date(2023, 5, 30)  # a Tuesday


def one(text: str) -> tuple[date, date]:
    found = resolve_event_dates(text, REF)
    assert len(found) == 1, found
    return found[0].start, found[0].end


def day(y: int, m: int, d: int) -> tuple[date, date]:
    return date(y, m, d), date(y, m, d)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I saw the dentist last Tuesday.", day(2023, 5, 23)),
        ("We went hiking last Sunday", day(2023, 5, 28)),
        ("this past Monday was busy", day(2023, 5, 29)),
        ("next Friday is the deadline", day(2023, 6, 2)),
        ("this Friday works", day(2023, 6, 2)),
        ("this coming Tuesday", day(2023, 6, 6)),
        ("yesterday I baked", day(2023, 5, 29)),
        ("the day before yesterday", day(2023, 5, 28)),
        ("tomorrow we fly", day(2023, 5, 31)),
        ("I finished 3 days ago", day(2023, 5, 27)),
        ("two weeks ago I started", day(2023, 5, 16)),
        ("a month ago", day(2023, 4, 30)),
        ("a couple of months ago", day(2023, 3, 30)),
        ("five years ago", day(2018, 5, 30)),
        ("on May 3rd", day(2023, 5, 3)),
        ("my appointment is June 5", day(2023, 6, 5)),
        ("back on January 15", day(2023, 1, 15)),
        ("last December 20", day(2022, 12, 20)),
        ("the 4th of July", day(2023, 7, 4)),
        ("Sept 12, 2021", day(2021, 9, 12)),
        ("logged on 2023-05-03", day(2023, 5, 3)),
    ],
)
def test_single_expressions(text: str, expected: tuple[date, date]) -> None:
    assert one(text) == expected


def test_periods_resolve_to_ranges() -> None:
    assert one("last week") == (date(2023, 5, 22), date(2023, 5, 28))
    assert one("this month") == (date(2023, 5, 1), date(2023, 5, 31))
    assert one("next month") == (date(2023, 6, 1), date(2023, 6, 30))
    assert one("last year") == (date(2022, 1, 1), date(2022, 12, 31))


def test_multiple_expressions_are_ordered_by_position() -> None:
    found = resolve_event_dates("Last Tuesday, May 23, and again 3 days ago.", REF)
    assert [(e.expression, e.start) for e in found] == [
        ("Last Tuesday", date(2023, 5, 23)),
        ("May 23", date(2023, 5, 23)),
        ("3 days ago", date(2023, 5, 27)),
    ]


def test_invalid_and_unrecognised_text_produces_nothing() -> None:
    assert resolve_event_dates("February 30 is not a date", REF) == []
    assert resolve_event_dates("I prefer local-first tools.", REF) == []
    assert resolve_event_dates("May I ask a question?", REF) == []


def test_month_end_arithmetic_clamps() -> None:
    assert resolve_event_dates("a month ago", date(2023, 3, 31))[0].start == date(2023, 2, 28)
    assert resolve_event_dates("a year ago", date(2024, 2, 29))[0].start == date(2023, 2, 28)


def test_explicit_years_outside_this_century_are_respected() -> None:
    """Regression: 'March 6, 1836' was resolved to the nearest March 6 in 2023."""
    assert one("the final assault on March 6, 1836") == day(1836, 3, 6)
    assert one("founded 4 July 1776") == day(1776, 7, 4)
