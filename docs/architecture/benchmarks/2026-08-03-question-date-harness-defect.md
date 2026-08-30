# Harness Defect — Question Date Absent From Every Answering Prompt

Date: 2026-08-03
Status: defect confirmed and fixed; **prior answer-quality numbers are affected and a
re-measurement is required before they are cited again**

## What was found

While diagnosing temporal-reasoning failures for a SCAMPER candidate, the five failed
temporal questions in the Opus stratified-60 were examined individually. The answerer had
the right dates in its context and still declined. Its own words on `8077ef71`:

> "You attended a networking event (6–8 PM) on 9 March 2022 — you mentioned it the same
> day ... **Without a specified reference date, I can't compute a different day count.**"

`questionDate` is `None` for **60 of 60** questions in the retrieval checkpoint, so
`build_answer_prompt` rendered `Question Date: Not specified` on every call in every paid
answering run to date.

## Cause

Not upstream. MemoryBench supports the field end to end —
`src/benchmarks/longmemeval/index.ts:203` reads `item.question_date`, and
`src/orchestrator/checkpoint.ts:205` writes it. This project runs the orchestrator with
`phases: ["ingest", "indexing", "search"]` and performs answering separately in its own
Python runner, which read `question.get("questionDate")` from a checkpoint that the
retrieval-only phase list never populates. The runner had no `--dataset` argument and
therefore no other source for the date.

## Impact

Bounded by inspection of the five temporal failures rather than assumed:

| Question | Cause |
| --- | --- |
| `8077ef71` | **Date-blocked.** Explicitly stated it could not compute without a reference date. |
| `gpt4_8279ba03` | **Probably date-blocked.** "What did I buy 10 days ago" cannot be resolved without today's date; answered "I don't know" without explaining. |
| `a3045048` | Evidence absent from context. |
| `gpt4_21adecb5` | Evidence absent from context. |
| `gpt4_468eb063` | Evidence absent from context. |

So roughly **two of five** temporal failures are attributable to the defect, not five.
Recovering them would move the stratified-60 from 47/60 to about 49/60, and temporal from
5/10 to about 7/10. That is an estimate from inspection, **not a measurement**, and it must
be re-run rather than assumed.

The defect is systematic across all 60 questions and all categories, so effects outside
temporal cannot be ruled out. Every answer-quality figure produced so far — the 47/60
stratified diagnostic, the 45/60 and 40/60 paired arms, and the human-adjudicated 47/60 and
41/60 — was measured with no reference date supplied. Those numbers are a **floor**.

The paired `session-diverse-v1` comparison is not invalidated: both arms ran under the same
defect, so the comparison remains internally valid and the candidate's rejection stands.

## Fix

`scripts/run_memorybench_claude_pilot.py` takes an optional `--dataset` and resolves
`question_date` from the pinned dataset, preferring it over the checkpoint value and
falling back to it. Each answer records `question_date` and a `question_date_source` of
`dataset`, `checkpoint`, or `unresolved`, so any future run states on its face whether the
date was supplied. Retrieval, ranking, storage, and stored data are untouched.

`tests/test_memorybench_question_dates.py` covers mapping, the empty case, prompt
inclusion, and the prior fallback behaviour, so the silent-failure mode cannot return
unnoticed.

The equivalent path in `run_memorybench_kimi_paired_development.py` reads
`question.get("questionDate")` from the same checkpoints and needs the same treatment
before its next run.

## Why this outranks the candidate work

Every candidate's promotion gate is measured through this harness. A defect upstream of
every measurement invalidates the basis on which candidates would be compared, so it is
fixed before any candidate is contracted. Cost was one argument, one helper, and four
tests.
