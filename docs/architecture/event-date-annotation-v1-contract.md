# Event-Date Annotation v1 — Development Contract

Date: 2026-09-30
Status: **FROZEN 2026-09-30 under delegated authority, before any measurement of this policy.** Set by
the author without owner review during an unattended session; owner review requested.
**Owner accepted these gates unchanged on 2026-10-09**, after its measured result was known; acceptance ratifies the contract as frozen and changes no outcome.
Baseline: `benchmarks/2026-09-27-kimi-question-date-baseline180.md` (134/180; temporal 30/44).
Evidence behind the design: `benchmarks/2026-09-30-event-date-resolver-coverage.md`, measured on the
stratified sixty only.

## Hypothesis

Temporal questions fail partly because the answering model must compute event dates from relative
expressions ("last Tuesday", "3 weeks ago") against a session date. Supplying the resolved date
beside the message should help.

## The one material variable

An added `event_dates` field on user messages already in the ranked top ten. Ranking, selection,
order, bodies, storage, prompts, and the answer and judge protocol are unchanged. No model in the
query path. Assistant text and bare "today" are never annotated.

## Stage 1 — local, API-free, all 180 development questions

- 180 complete, zero errors;
- every question's context identical to the ranked baseline except `event_dates` and the two
  time-varying score fields;
- **mechanism:** at least 11 of the 44 temporal-reasoning questions (25%) have an annotated item
  from a labelled answer session. Fewer would leave too little reach for a +4 answer gain;
- context bytes mean ≤ 1.05× and p95 ≤ 1.10× baseline;
- selection p95 ≤ 15 ms and search p95 ≤ 225 ms.

Any miss closes the candidate before a paid call.

## Stage 2 — paid, kimi-k3, all 180

Candidate arm only, under the unchanged single-arm protocol that produced the 134/180 baseline.

| Gate | Threshold |
| --- | --- |
| temporal-reasoning | **≥ 34/44** (+4) |
| overall | ≥ 136/180 (+2) |
| any other category | may lose at most 1 answer |
| cost | ≤ $12.00 hard ceiling |

A +4 gate on 44 questions is roughly four standard deviations of measured identical-protocol churn.
The 120 design-blind questions are aggregated only.
