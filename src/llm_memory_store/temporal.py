"""Deterministic resolution of event dates from relative English date expressions.

A message is *said* at one time and often describes an event at another: "I saw the dentist
last Tuesday", said on 30 May 2023, refers to 23 May 2023. The store records only when a memory
was written. This module resolves the event date without a model, so it is auditable, offline,
and cheap enough to run on every message.

It is deliberately conservative. It recognises a closed set of patterns and returns nothing for
anything else, rather than guessing. Ambiguous references follow fixed, documented rules:

- "last <weekday>" is the most recent such weekday strictly before the reference date, and
  "next <weekday>" the first strictly after it; "this <weekday>" is the one in the reference
  date's Monday-to-Sunday week.
- A month and day without a year resolve to the occurrence nearest the reference date.

Known limitation: a bare month name followed by a number ("you may 3 ...") can match as a date.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

__all__ = ["EventDate", "resolve_event_dates"]

_WEEKDAYS = {
    name: i
    for i, name in enumerate(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    )
}
_MONTHS = {name: i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name[:3]: i for name, i in list(_MONTHS.items())})
_MONTHS = {k.lower(): v for k, v in _MONTHS.items()}
_MONTHS["sept"] = 9
_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "couple of": 2,
    "a couple of": 2,
    "few": 3,
    "a few": 3,
}

_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY_RE = "|".join(_WEEKDAYS)
_NUM_RE = r"\d{1,3}|" + "|".join(sorted(map(re.escape, _NUMBER_WORDS), key=len, reverse=True))


@dataclass(frozen=True, slots=True)
class EventDate:
    """A resolved event date or date range, with the text that produced it."""

    start: date
    end: date
    expression: str
    span: tuple[int, int]


def _clamp_day(year: int, month: int, day: int) -> date | None:
    if not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    if not 1 <= day <= last:
        return None
    return date(year, month, day)


def _shift_months(ref: date, months: int) -> date:
    index = ref.year * 12 + (ref.month - 1) + months
    year, month = divmod(index, 12)
    last = calendar.monthrange(year, month + 1)[1]
    return date(year, month + 1, min(ref.day, last))


def _number(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        value = int(token)
        return value if 0 < value <= 400 else None
    return _NUMBER_WORDS.get(token)


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("iso", re.compile(r"\b(?P<y>(?:19|20)\d\d)-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b")),
    (
        "month_day",
        re.compile(
            rf"\b(?:on\s+)?(?P<mon>{_MONTH_RE})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?"
            rf"(?:,?\s+(?P<y>\d{{4}}))?\b",
            re.I,
        ),
    ),
    (
        "day_month",
        re.compile(
            rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mon>{_MONTH_RE})\.?"
            rf"(?:,?\s+(?P<y>\d{{4}}))?\b",
            re.I,
        ),
    ),
    ("ago", re.compile(rf"\b(?P<n>{_NUM_RE})\s+(?P<unit>day|week|month|year)s?\s+ago\b", re.I)),
    (
        "relative_weekday",
        re.compile(
            rf"\b(?P<which>last|next|this|this past|this coming)\s+(?P<wd>{_WEEKDAY_RE})\b", re.I
        ),
    ),
    (
        "relative_period",
        re.compile(r"\b(?P<which>last|next|this)\s+(?P<unit>week|month|year)\b", re.I),
    ),
    (
        "simple",
        re.compile(r"\b(?P<word>today|yesterday|tomorrow|the day before yesterday)\b", re.I),
    ),
]


def _resolve(kind: str, m: re.Match[str], ref: date) -> tuple[date, date] | None:
    g = m.groupdict()
    if kind == "iso":
        d = _clamp_day(int(g["y"]), int(g["m"]), int(g["d"]))
        return (d, d) if d else None
    if kind in ("month_day", "day_month"):
        month = _MONTHS[g["mon"].lower().rstrip(".")]
        day = int(g["d"])
        if g.get("y"):
            d = _clamp_day(int(g["y"]), month, day)
            return (d, d) if d else None
        # No year: the occurrence nearest the reference, across last, this, and next year.
        # People mention both past events and upcoming plans ("my appointment is June 5",
        # said on 30 May, means this June), so "most recent past" would misdate plans.
        options = [
            candidate
            for year in (ref.year - 1, ref.year, ref.year + 1)
            if (candidate := _clamp_day(year, month, day)) is not None
        ]
        if not options:
            return None
        d = min(options, key=lambda c: (abs((c - ref).days), c))
        return d, d
    if kind == "ago":
        n = _number(g["n"])
        if n is None:
            return None
        unit = g["unit"].lower()
        if unit == "day":
            d = ref - timedelta(days=n)
            return d, d
        if unit == "week":
            d = ref - timedelta(weeks=n)
            return d, d
        if unit == "month":
            d = _shift_months(ref, -n)
            return d, d
        d = _shift_months(ref, -12 * n)
        return d, d
    if kind == "relative_weekday":
        which = g["which"].lower()
        target = _WEEKDAYS[g["wd"].lower()]
        delta = (ref.weekday() - target) % 7
        if which in ("last", "this past"):
            d = ref - timedelta(days=delta or 7)
        elif which in ("next", "this coming"):
            d = ref + timedelta(days=((target - ref.weekday()) % 7) or 7)
        else:  # "this <weekday>": the one in the current Monday-to-Sunday week
            d = ref - timedelta(days=ref.weekday()) + timedelta(days=target)
        return d, d
    if kind == "relative_period":
        which, unit = g["which"].lower(), g["unit"].lower()
        step = {"last": -1, "this": 0, "next": 1}[which]
        if unit == "week":
            monday = ref - timedelta(days=ref.weekday()) + timedelta(weeks=step)
            return monday, monday + timedelta(days=6)
        if unit == "month":
            first = _shift_months(ref.replace(day=1), step)
            last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
            return first, last
        year = ref.year + step
        return date(year, 1, 1), date(year, 12, 31)
    if kind == "simple":
        word = g["word"].lower()
        offset = {"today": 0, "yesterday": -1, "tomorrow": 1, "the day before yesterday": -2}[word]
        d = ref + timedelta(days=offset)
        return d, d
    return None


def resolve_event_dates(text: str, reference: date) -> list[EventDate]:
    """Return every recognised date expression in `text`, resolved against `reference`.

    Overlapping matches keep the earliest, longest one. Expressions outside the recognised
    set produce nothing. Results are ordered by position in the text.
    """
    found: list[EventDate] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            span = m.span()
            if any(span[0] < end and start < span[1] for start, end in taken):
                continue
            resolved = _resolve(kind, m, reference)
            if resolved is None:
                continue
            taken.append(span)
            found.append(EventDate(resolved[0], resolved[1], m.group(0), span))
    return sorted(found, key=lambda e: e.span)
