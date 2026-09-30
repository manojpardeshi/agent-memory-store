# event-date-annotation-v1 — Stage 2 Result

Date: 2026-09-30
Status: **FAILED its primary gate. Candidate closed.**
Contract: `../event-date-annotation-v1-contract.md`, frozen before measurement.
Report: `demo-artifacts/kimi-event-date-v1-stage2.json`, SHA-256 `6d62ee2356941f0e3068c03bfff87712d3a3181024560275f902c2e9f5d72ecc`. Cost $6.48.

| Gate | Threshold | Result |
| --- | --- | --- |
| **temporal-reasoning** | ≥ 34/44 | **29/44 — FAIL** |
| overall | ≥ 136/180 | 137/180 — pass |
| any other category loses at most 1 | — | pass, none lost |

| Category | Baseline | Event dates |
| --- | ---: | ---: |
| single-session-assistant | 22/22 | 22/22 |
| single-session-user | 25/26 | 26/26 |
| knowledge-update | 24/29 | 25/29 |
| single-session-preference | 10/15 | 12/15 |
| multi-session | 23/44 | 23/44 |
| temporal-reasoning | 30/44 | 29/44 |
| **Total** | **134/180** | **137/180** |

Paired: 132 both, 41 neither, 2 baseline-only, 5 candidate-only; sign test p = 0.45.

## Reading

The annotation reached 20 of the 44 temporal questions through labelled answer evidence, and
temporal answers went from 30 to 29. Supplying resolved event dates did not help the category it
targeted. The overall gain of three comes from preference, user, and knowledge-update, categories
the annotation barely touches, with p = 0.45. It is the kind of churn the gates were sized to reject
and must not be read as an improvement.

## Together with the other results of the day

- Wider session context (v1.2 diagnostic) did not move multi-session or temporal answers.
- Resolved event dates did not move temporal answers.
- Hosted Mem0 scored 7/10 on temporal where the store scored 5/10 on the same ten questions.

Neither more raw text nor pre-computed dates closes the temporal gap. What Mem0 supplies instead is
a compact, deduplicated, dated fact per memory. The next temporal hypothesis worth a contract is
fact-shaped context, not more or better-annotated raw context.
