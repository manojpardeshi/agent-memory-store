# Hybrid Retrieval Prototype — Keyword + Vector Fusion

Date: 2026-10-02
Status: **confirmed on held-out questions under a configuration frozen beforehand.** Evaluation-only:
the product schema and recall are unchanged. No model beyond the store's local embedder; no cost.
Frozen choice: `evaluation/memorybench/hybrid-rrf-v1-frozen.json` (committed before the held-out run).
Code: `scripts/prototype_hybrid_retrieval.py`. Metric: `scripts/analyze_evidence_recall.py`.

## What was tested

Reciprocal rank fusion of the store's vector ranking and a SQLite FTS5 BM25 keyword ranking (porter
stemming, stopwords removed), equal weights, k = 60, top ten. The FTS5 index was built in memory per
benchmark store for the measurement.

## Discipline

Variants were compared on the stratified sixty only. Equal-weight fusion at the standard k = 60 was
frozen, with the held-out reading fixed in advance: fusion must beat vector-only by at least 4
complete-evidence questions, and no category may lose more than 1. The 120 design-blind questions
were then evaluated once, unchanged, and are reported only in aggregate.

## Results — questions with every answer-bearing message in the top ten

| Set | Vector only | Keyword only | **Fusion** |
| --- | ---: | ---: | ---: |
| Tuning, stratified sixty (57 scored) | 41 | 45 | **47** |
| **Held-out, 120 (117 scored)** | 80 | 79 | **91** |
| All 180 (174 scored) | 121 | 124 | **138** |

Evidence recall over all 174: **0.793 → 0.844**. BM25 query p95 under 1 ms.

Held-out per-category change, fusion minus vector: knowledge-update +4, multi-session +4,
temporal-reasoning +3, every other category 0. Both frozen conditions are met.

On the tuning set, preference lost 2 complete-evidence questions. That was visible before freezing,
did not recur on the held-out set, and is recorded rather than omitted.

## Reading

Keyword and vector retrieval fail on different questions, and fusing them recovers evidence that
neither finds alone, concentrated in the weakest answer categories. This is a retrieval improvement.
Because answer quality is no longer measured and complete evidence proved necessary but not
sufficient, no answer-quality gain is claimed.

## Before it can ship

Integrating it into the product needs a persisted FTS5 index kept in sync with every write,
correction, deletion, and expiry purge; a migration that builds the index for existing stores;
interaction rules with the relevance filter; and the internal synthetic retrieval suites passing
unchanged or better. That is a schema change to a published library and is proposed separately.
