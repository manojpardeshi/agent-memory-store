# Within-Session Expansion v1.2 — Development Contract

Date: 2026-09-30
Status: **FROZEN 2026-09-30 under delegated authority, before any v1.2 measurement.** The owner
delegated decisions for an unattended working session; the author set these gates without owner
review. Gates were fixed before any v1.2 output was observed. Owner review is requested on return,
and any change after a result is observed creates a new experiment identity.
**Owner accepted these gates unchanged on 2026-10-09**, after its measured result was known; acceptance ratifies the contract as frozen and changes no outcome.
Predecessor: `within-session-expansion-contract.md` (v1.1, failed Stage 1, closed).
Baseline: `benchmarks/2026-09-27-kimi-question-date-baseline180.md` (134/180).

## What changes from v1.1, and why

Exactly three changes, each tied to a recorded v1.1 defect. The policy is otherwise identical:
same baseline prefix, same 4-message per-session cap, same zero new sessions, same 400-character
body floor, same ≤ 1.00× budget, same model-free query path.

| Change | v1.1 evidence |
| --- | --- |
| Each session's highest-ranked baseline message is never span-reduced. | `18dcd5a5`: the top-ranked message was cut to a span that kept the title and lost the count. |
| Exact incremental byte accounting. Proven equal to full encoding, so decisions are unchanged. | Selection p95 34.1 ms against 15 ms. |
| Neighbours fetched per baseline session with `find_by_metadata`, uncapped. | `list_memories` 1,000-record cap would silently truncate larger stores. |

## Stage 1 — local, API-free, all 180 development questions

Identical gates to v1.1:

- 180 complete, zero errors, zero scope, lifecycle, source, or provenance failures;
- every baseline top-ten item present, in order; zero new sessions;
- within-session coverage ≥ 55% and ≥ 15 points above the same-180 baseline; no category falls;
- context bytes mean ≤ 1.00× and p95 ≤ 1.05× baseline;
- selection p95 ≤ 15 ms; search p95 ≤ 225 ms;
- answer presence on the stratified sixty's extractive questions does not fall;
- internal suites unchanged.

Any miss closes v1.2 before a paid call.

## Stage 2 — paid, kimi-k3, all 180

Candidate arm only, under the identical single-arm runner and protocol that produced the 134/180
baseline three days earlier. Single-arm is valid only because that protocol is unchanged.

Gates, sized on the measured identical-protocol churn of about one answer per sixty:

| Gate | Threshold |
| --- | --- |
| multi-session + temporal combined | **≥ +4** over 53/88, i.e. ≥ 57/88 |
| overall | ≥ +3 over 134/180, i.e. ≥ 137/180 |
| multi-session alone | must not fall below 23/44 |
| any other category | may lose at most 1 answer |
| cost | ≤ $9.00 hard ceiling |

The 120 design-blind questions are measured but not read per question for any v1.3 design.

## What a pass would establish

That within-session expansion with anchor protection improves answer quality on 180 LongMemEval-S
development questions at no increase in context cost, on one benchmark with one evaluator. It would
not authorise shipping as default, a competitive claim, or opening sealed validation.
