# within-session-expansion-v1.2 — Stage 1 Result

Date: 2026-09-30
Status: **FAILED Stage 1 on one gate. Candidate closed. No paid call made.**
Contract: `../within-session-expansion-v1.2-contract.md`, frozen before measurement.
Report: `demo-artifacts/within-session-expansion-v1.2-stage1.json`, SHA-256 `1d58b94478169dc54359c3a9a702d19786fc56cb18387741ffda88ee542b85f6`

## Gates

| Gate | v1.1 | v1.2 |
| --- | --- | --- |
| baseline prefix, no new sessions, zero errors | pass | pass |
| coverage ≥ +15 points over same-180 baseline | pass (+21.5) | pass (+17.7) |
| **coverage ≥ 55% absolute** | pass (57.6%) | **FAIL (53.8%)** |
| no category coverage regression | pass | pass |
| context bytes mean ≤ 1.00×, p95 ≤ 1.05× | pass | pass (0.968×, 0.998×) |
| **selection p95 ≤ 15 ms** | FAIL (34.1 ms) | **pass (4.4 ms)** |
| search p95 ≤ 225 ms | pass (62 ms) | pass (27 ms) |
| **answer presence does not fall** | FAIL (29 → 28) | **pass (29 → 29)** |

Both v1.1 failures are fixed. The anchor protection kept the answer that v1.1 pruned, and exact
incremental accounting cut selection latency roughly eightfold with provably identical decisions.

## Why coverage fell short

Protected anchors cannot be reduced, so less budget is available to pay for expansions: 4.3
admitted per question against 5.6 for v1.1. Coverage rose from 36.1% to
53.8%, 1.2 points short of the absolute bar.

| Category | Baseline | v1.2 |
| --- | ---: | ---: |
| knowledge-update | 36.3% | 58.8% |
| multi-session | 29.3% | 44.4% |
| single-session-assistant | 66.8% | 84.7% |
| single-session-preference | 38.2% | 61.6% |
| single-session-user | 49.2% | 67.8% |
| temporal-reasoning | 31.5% | 47.5% |

## An observation for owner review, not a basis for proceeding

The contract carried two coverage gates from v1.1: ≥ 55% absolute and ≥ +15 points relative. The
absolute bar was set when the baseline was believed to be about 38% on sixty questions, making the
two roughly equivalent. Re-measured on 180, the baseline is 36.1%, so 55% requires +18.9 points and
became the binding gate. The relative gate, which measures the mechanism the candidate targets,
passed.

This was noticed only after the result, so under the contract it cannot rescue v1.2. Any successor
that restates the coverage gate must say it was restated after observing this result.

## What remains untested

Whether wider within-session context improves **answers** has still never been measured: both
candidates stopped at the free mechanism stage. A candidate arm run through the frozen kimi protocol
on all 180 would cost about $6.50 and could be run as a clearly labelled diagnostic, not a
promotion test, if the owner chooses.
