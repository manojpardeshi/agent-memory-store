# event-date-annotation-v1 — Stage 1 Result

Date: 2026-09-30
Status: **PASSED all eight Stage 1 gates.** Stage 2 launched under the frozen contract.
Contract: `../event-date-annotation-v1-contract.md`, frozen before measurement.
Report: `demo-artifacts/event-date-annotation-v1-stage1.json`, SHA-256 `e00352181843d134da41ff3554d0aa0cfa02736c855bb08a1a21b5a334543260`

| Gate | Result |
| --- | --- |
| 180 complete, zero errors | pass |
| context identical to ranked baseline apart from `event_dates` | pass, all 180 |
| temporal questions with an annotated answer-session item ≥ 11 | **pass, 20 of 44** |
| bytes mean ≤ 1.05×, p95 ≤ 1.10× | pass, 1.0020× and 1.0084× |
| selection p95 ≤ 15 ms | pass, 0.64 ms |
| search p95 ≤ 225 ms | pass, 18.9 ms |

74 of 180 questions received at least one annotation, 136 items in total.
The policy reaches 20 of the 44 temporal questions through their labelled answer evidence, which
bounds the plausible gain: the Stage 2 gate asks for 4 more correct answers among those 44.
