# Where Recall Misses Evidence — Tuning-Pool Diagnosis

Date: 2026-10-23
Data: LongMemEval-S development 180, the tuning pool under `../held-out-renewal-plan.md`. Per-question
inspection is allowed for this pool.
Script: `scripts/diagnose_evidence_misses.py` (vector recall, benchmark header stripped, depth 100).
Free and local.

## Complete evidence in the top ten (vector recall)

| Category | Complete |
| --- | ---: |
| single-session-assistant | 22 / 22 |
| single-session-user | 24 / 25 |
| knowledge-update | 20 / 26 |
| single-session-preference | 11 / 15 |
| temporal-reasoning | 26 / 43 |
| multi-session | **18 / 43** |
| **All** | **121 / 174** |

## Where the 84 missed evidence turns rank

| Kind | Turns | Share |
| --- | ---: | ---: |
| Near miss: ranked 11–30 | 61 | 73% |
| Its session is in the top ten, the turn is not | 12 | 14% |
| Ranked 31–100 | 8 | 10% |
| Beyond rank 100 | 3 | 4% |

Multi-session accounts for 33 near misses, 9 same-session misses, 2 at ranks 31–100, and 2 beyond
rank 100. Temporal reasoning accounts for 14 near misses, 3 same-session misses, 6 at ranks 31–100,
and 1 beyond rank 100.

## Reading

The misses are mostly not topic misses. Recall finds the evidence and ranks it just below the cut.
Multi-session and temporal questions need two to five evidence turns, often from different
sessions, and the top ten fills before all of them arrive. True topic misses beyond rank 100 are 3
of 84 turns.

A remedy therefore targets ranking within the top thirty: put the right turns among the first ten
without enlarging the context. Query reformulation and other recall-widening ideas address a
failure that barely occurs.

This bears on the roadmap's closed context-bundling hypothesis. Its reopening condition is
"evidence that message selection rather than synthesis dominates multi-session or temporal
failure." This diagnosis shows that at turn level, selection, not search, leaves evidence out of
the top ten. Whether that costs answers cannot be measured without a paid answerer. Any candidate
must therefore be justified on evidence recall, with that limit stated.
