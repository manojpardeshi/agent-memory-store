# Session-Diverse Context Development Contract

Date: 2026-08-01
Status: frozen before candidate execution

## Decision

Evaluate one provider-neutral context-selection policy on the frozen 180-question development
split. The policy reads the unchanged top 50 ranked, relevance-filtered message results, greedily
admits no more than two messages from one provenance session, and returns ten single-message slots.
If diversity cannot fill ten slots, it backfills previously skipped messages in their original
rank order. Final output preserves original rank order.

The candidate is label-blind. It may read only rank and `metadata.session_id`. It does not use
LongMemEval answer-session labels, question type, reference answer, or judge output. It changes no
storage, embedding, ranking, relevance, prompt, source, or result-schema behavior. Adjacent-message
expansion is excluded because it would add context without increasing distinct-session coverage.

## Frozen development baseline

The baseline was computed from the existing immutable 60-question and 440-question retrieval
checkpoints, filtered only by the already-frozen development manifest. No candidate result existed.

| Metric | Development baseline |
| --- | ---: |
| Questions | 180 |
| Overall answer-session recall@10 | 92.80% |
| Multi-session answer-session recall@10 | 89.32% |
| Temporal answer-session recall@10 | 83.48% |
| Overall MRR@10 | 0.8972 |
| Mean / p95 formatted context bytes | 30,443 / 42,894 |
| Search p95 | 173 ms |

The source manifest SHA-256 is
`34f0d70817fc972fe15ad405d11c78e2309266d6324697badeac314bd5585f94`.

## Acceptance

At least one of multi-session or temporal answer-session recall@10 must improve by two percentage
points and the other must not regress. Overall recall must remain at least 92.30%, MRR at least
0.8922, every category within one percentage point of baseline, and no more than three questions
may lose labeled-session recall. Mean distinct sessions must increase by at least one.

Mean formatted context bytes may be at most 1.05 times baseline and p95 at most 1.10 times
baseline. Pure selection p50/p95 must remain at most 5/15 ms, and development search p95 at most
225 ms. All existing retrieval, scope, lifecycle, and provenance tests remain mandatory.

The machine-readable contract is
`evaluation/memorybench/session-diverse-development-gates-v1.json`. Passing authorizes retaining a
frozen development candidate only. It does not authorize shipment or opening sealed validation.

## Failure and rollback

The policy is default-off. Disabling it restores the released top-K behavior without migration or
reindexing. A failed gate is recorded; cap, pool depth, or bundling may not be tuned on the observed
development result without a new preregistration that discloses the earlier observation.
