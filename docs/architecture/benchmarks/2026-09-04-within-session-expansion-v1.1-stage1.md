# within-session-expansion-v1.1 — Stage 1 Result

Date: 2026-09-04
Status: **FAILED Stage 1 under the frozen v1.1 contract. Candidate closed. No paid call made.**
Contract: `../within-session-expansion-contract.md` (v1.1, frozen 2026-09-04)
Report: `demo-artifacts/within-session-expansion-stage1.json`, SHA-256 `65c39d2d2bec82ac3204e8db1f91968b9fe71aca253c04dc7d01c17d17eff3c3`
Scope: all 180 development questions, API-free, on-disk stores. Sealed validation and reserve untouched.

## Gates

| Gate | Result |
| --- | --- |
| questions complete (180) | pass |
| every baseline top-ten item present, in order | pass — all 180 |
| new sessions introduced | pass — 0 |
| coverage ≥ 55% absolute | pass — 57.6% |
| coverage ≥ +15 pts over same-180 baseline | pass — +21.5 pts |
| no category coverage regression | pass — every category up |
| context bytes mean ≤ 1.00× | pass — 0.968× |
| context bytes p95 ≤ 1.05× | pass — 0.997× |
| **selection p95 ≤ 15 ms** | **FAIL — 34.1 ms** |
| search p95 ≤ 225 ms | pass — 62 ms |
| **answer presence (stratified 60, extractive) does not fall** | **FAIL — 29/30 → 28/30** |
| zero errors | pass |

Ten of twelve pass. Under the contract's stop rule any miss ends the candidate before a paid
call; this candidate is closed and no Stage 2 is requested.

## The mechanism worked

Within-session coverage on retrieved answer sessions rose from 36.1% to
57.6% at 0.968× the baseline's bytes, with a mean of 5.6 expansions admitted per
question, zero new sessions, and the baseline retained as an ordered prefix on all 180.

| Category | Baseline | Candidate |
| --- | ---: | ---: |
| knowledge-update | 36.3% | 62.0% |
| multi-session | 29.3% | 48.6% |
| single-session-assistant | 66.8% | 90.7% |
| single-session-preference | 38.2% | 62.0% |
| single-session-user | 49.2% | 71.3% |
| temporal-reasoning | 31.5% | 51.5% |

The hypothesis's mechanism — more of an already-relevant session at constant cost — is
established as implementable. What failed is the *cost* of paying for it.

## Failure 1: answer presence fell on `18dcd5a5`

Single-session-assistant. Question: *"remind me how many mu…"* about a one-shot adventure.
Gold: **4**. The answer was in the **top-ranked baseline message**, a 3,079-character story
reply. Under the contract's order of sacrifice (largest body first), the candidate reduced that
message to the 384-character floor, and the query-aware span selected the story's *opening* —
where the title "Lost Temple of the Djinn" lexically matches the question — rather than the
sentence containing the count. The context lost the answer while coverage rose.

This is systematic, not incidental. For "how many / how much" questions, the query's
distinctive tokens name the **topic**, which appears at the top of a message, while the numeric
fact sits elsewhere. **Query-aware span selection is not answer-aware**, and the question class
it fails on is precisely the aggregation class that motivated the candidate. The guard added
under fix A existed to catch exactly this, and it did.

Two properties of v1.1 combine to produce it: the anchor (each session's highest-ranked hit —
the message retrieval itself judged most relevant) is eligible for reduction like any other
body, and once it is the largest body it is reduced *first*.

## Failure 2: selection latency

p50 15.3 ms, p95 34.1 ms, max 50.0 ms against a 15 ms bound. The bound was carried over from
the session-density draft, whose policy swapped two items; span fitting re-encodes the context
several times per question. Search p95 is 62 ms against 225. This is an implementation cost,
not a policy property: exact incremental byte accounting would remove the repeated full
encodes without changing any output. It was frozen at 15 ms and it missed.

## Implementation defects found and fixed during the run

Two stalls occurred before the reported run, both in budget fitting and both caught by a
watchdog stack: a halving loop that re-encoded the full context hundreds of times, and a
non-progress loop when the overshoot was smaller than the ellipsis markers re-added by span
reduction. Both were fixed with regression tests; partial checkpoints from the defective loops
were discarded so the reported run is uniform. The runner now enforces a 120 s per-question
deadline that records an error instead of hanging.

## What a successor would have to change

Not authorized by this document; recorded so the next contract starts from evidence.

1. **Protect the anchor.** Never span-reduce each session's highest-ranked baseline message.
   Directly prevents the observed failure and is a bound, not a heuristic.
2. **Latency.** Incremental exact byte accounting; verify byte-identical outputs on all 180
   before treating it as the same policy.
3. Deferred: an answer-aware span heuristic (prefer sentences with numerals for count questions)
   is a second heuristic with its own failure surface; it should be its own candidate only if a
   successor's guard still fires.

## Limits

Stage 1 is API-free and measures coverage, budget, structure, and a lexical answer-presence
proxy on thirty extractive questions. It does not measure answer quality. The coverage gain is
real; whether it would have translated into answers was never tested and, under the contract,
must not be inferred.
