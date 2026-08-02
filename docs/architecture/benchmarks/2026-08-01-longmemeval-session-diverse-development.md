# LongMemEval-S Session-Diverse Development Experiment

Date: 2026-08-01
Status: **all frozen retrieval-development gates passed; answer-quality confirmation pending**

## Outcome

The default-off `session-diverse-v1` candidate passed every pre-registered gate on the frozen 180
development questions. It preserved the released ranking and result count while replacing third
and later messages from an already represented session with the next ranked sessions from an
unchanged top-50 pool.

| Metric | Released top 10 | Session-diverse v1 | Change |
| --- | ---: | ---: | ---: |
| Answer-session recall@10 | 92.80% | 95.74% | +2.94 pp |
| Answer-session recall@5 | 83.77% | 90.70% | +6.94 pp |
| Hit@10 | 96.67% | 97.78% | +1.11 pp |
| MRR@10 | 0.8972 | 0.9027 | +0.0055 |
| Mean distinct sessions | 3.32 | 5.98 | +2.66 |
| Mean formatted context bytes | 30,443 | 26,415 | -13.2% |
| P95 formatted context bytes | 42,894 | 39,598 | -7.7% |

## Category coverage

| Category | Released recall@10 | Candidate recall@10 |
| --- | ---: | ---: |
| Knowledge update | 96.55% | 98.28% |
| Multi-session | 89.32% | 92.99% |
| Single-session assistant | 100% | 100% |
| Single-session preference | 100% | 100% |
| Single-session user | 100% | 100% |
| Temporal reasoning | 83.48% | 90.72% |

No category regressed, no question lost labeled answer-session recall, and no question changed its
result count. All 180 deeper pools reproduced the baseline ranked top-10 prefix exactly before
selection. Pure selection p50/p95 was 0.011/0.013 ms; replay search p95 was 29.4 ms. The replay
reused existing local indexes and cost $0 in hosted APIs.

## Interpretation

The mechanism worked as intended: fewer duplicate messages consumed context slots, distinct
labeled answer-session coverage increased, and context became smaller. Message-level result
precision@10 fell from 68.7% to 37.6%, largely because repeated messages from the same labeled
session no longer count multiple times. This is still a meaningful warning: the context is broader
and less dense, so retrieval-label improvement alone cannot establish answer improvement.

The candidate remains default-off and development-only. The next safe measurement is a frozen,
matched Kimi answer-quality comparison on development data with equal prompts and judging. Sealed
validation and reserve remain unopened, and this report is not a shipment or competitive claim.

Machine-readable evidence is in
`2026-08-01-longmemeval-session-diverse-development.json`. The gate contract SHA-256 is
`fd653d693e0557339125d5536be52ff0d28a390b2e293ce416992d63d1b9dfa4`.
