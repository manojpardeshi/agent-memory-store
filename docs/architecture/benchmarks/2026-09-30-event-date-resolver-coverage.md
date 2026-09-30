# Event-Date Resolver — Coverage and Precision on the Stratified Sixty

Date: 2026-09-30
Status: exploratory measurement. The resolver is an unwired library utility; no candidate is
authorized. Measured only on the observed stratified sixty, never on the 120 design-blind questions.
Module: `src/llm_memory_store/temporal.py`

## Why

Temporal reasoning is the second-weakest category at 30/44 (68%) on the 180-question baseline.
Its questions need when an event happened, while the store records only when a message was written.
"I saw the dentist last Tuesday", said on 30 May 2023, is an event on 23 May. Supermemory stores
both a document date and an event date. This resolver produces event dates deterministically, with
no model: fixed patterns, fixed documented rules for ambiguity, and nothing returned for anything
outside the recognised set.

## Coverage

Each session's own date is the reference date.

| Measure | Result |
| --- | ---: |
| messages with ≥ 1 resolved date | 1,826 / 29,829 (6.1%) |
| user messages with ≥ 1 resolved date | 1,142 / 14,802 (7.7%) |
| answer sessions containing a resolvable date | 43 / 96 |

By category, answer sessions containing a resolvable date:

| Category | Sessions |
| --- | ---: |
| **temporal-reasoning** | **13 / 18 (72%)** |
| **multi-session** | **18 / 28 (64%)** |
| knowledge-update | 5 / 20 |
| single-session-user | 3 / 10 |
| single-session-assistant | 2 / 10 |
| single-session-preference | 2 / 10 |

The resolver fires where the failures are.

## Precision, from a random sample of fourteen matches read by hand

- **Resolution correct given the text:** 13 of 14 after the fix below. Examples: "about 3 weeks ago"
  on 30 May became 9 May; "last month" on 22 May became April; "the one I went to on March 4th" on
  20 May became 2023-03-04.
- **One real bug, fixed:** "the final assault on March 6, 1836" resolved to 2023-03-06 because the
  year pattern accepted only 19xx and 20xx. Any four-digit year is now honoured, with a regression
  test.
- **Correct but useless matches:** "preserved today in Pompeii", "joining us today" in a sample
  script, a date inside R code, "next week" inside a sample dialogue. These are mostly in
  assistant-written text. "today" is the single most frequent match (620) and mostly means
  "nowadays".

## What a candidate should take from this

Recorded for a future contract, not authorized by this document:

1. Resolve dates from **user** messages only. Assistant text contributes most of the noise.
2. Exclude bare "today", or require it to co-occur with a past-tense event verb.
3. Store resolved event dates as metadata at ingest, leaving content untouched, so the source
   remains authoritative and the feature is reversible.
4. Measure it through the frozen single-arm kimi protocol against the 180 baseline, gated on
   temporal-reasoning with a threshold sized above the measured churn.
