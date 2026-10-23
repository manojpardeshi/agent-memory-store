# Cross-Encoder Re-Ranking — Tuning Results

Date: 2026-10-23
Data: tuning pool only (LongMemEval-S development 180, 174 with evidence) plus the synthetic
suites retrieval_v1, retrieval_v2 and retrieval_v3. Held-out data was not read.
Script: `scripts/prototype_rerank.py`. Reports: `demo-artifacts/rerank-tuning-dev180.json` and
`demo-artifacts/rerank-tuning-dev180-truncation.json`. Free and local (FastEmbed cross-encoders).

## Sweep 1: five models × depth K ∈ {20, 30, 50}, full text

Complete evidence in the top ten, out of 174 (baseline vector: 121):

| Model | Size | K=20 | K=30 | K=50 | Re-rank median at K=30 |
| --- | ---: | ---: | ---: | ---: | ---: |
| ms-marco-MiniLM-L-6-v2 | 92 MB | 136 | 139 | 141 | 1.8 s |
| ms-marco-MiniLM-L-12-v2 | 134 MB | 134 | 139 | 135 | 3.4 s |
| jina-reranker-v1-tiny-en | 134 MB | 132 | 134 | 131 | 1.5 s |
| jina-reranker-v1-turbo-en | 153 MB | 140 | **143** | 135 | 2.2 s |
| bge-reranker-base | 1,130 MB | 133 | 137 | 138 | 10.3 s |

Synthetic suites were run for the top three. All failed retrieval_v3:

- jina-turbo lowered v3's paraphrase MRR from 0.80 to 0.68.
- MiniLM-L6 at K=50 raised v3 MRR from 0.87 to 0.95, but its distractor leak of 0.117 exceeds the
  0.10 gate.

## Sweep 2: MiniLM-L6, re-rank on the first C characters

Truncation affects only the cross-encoder's input; stored memories are unchanged.

| Variant | Complete (all / multi-session / temporal / single-session-assistant) | Recall | Re-rank median / p95 | v1 v2 v3 |
| --- | --- | ---: | ---: | --- |
| Baseline | 121 / 18 / 26 / 22 | 0.793 | — | ✓ ✓ ✓ |
| C256 K20 | 127 / 19 / 29 / 21 | 0.837 | 134 / 180 ms | ✓ ✓ ✓ |
| **C512 K20** | **138 / 28 / 29 / 20** | **0.867** | **249 / 338 ms** | ✓ ✓ ✓ |
| C1024 K20 | 137 / 27 / 29 / 20 | 0.865 | 512 / 636 ms | ✓ ✓ ✓ |
| No truncation, K20 | 136 / 26 / 29 / 20 | 0.860 | 1,292 / 1,477 ms | ✓ ✓ ✓ |
| C512 K30 | 141 / 29 / 30 / 20 | 0.876 | 387 / 517 ms | ✓ ✓ ✗ |
| C512 K50 | 143 / 30 / 31 / 20 | 0.880 | 669 / 926 ms | ✓ ✓ ✗ |

Notes on the synthetic suites:

- Every K=30 and K=50 variant fails retrieval_v3 on distractor leak (0.117 vs the 0.10 gate).
- Every K=20 variant passes v3, exactly at 0.10. Re-ranking raises v3 MRR from 0.867 to 0.951 in
  all twelve variants.
- On retrieval_v2, every variant drops one expected item (recall 1.000 → 0.983), raises MRR
  from 0.894 to 0.936, and halves distractor leak (0.10 → 0.05).
- v1 is unchanged.
- No variant has a scope violation in any suite.

## Reading

Re-ranking targets the diagnosed failure: multi-session complete evidence rises from 18 to 28
with C512 K20, temporal from 26 to 29, and knowledge-update from 20 to 24–26. It costs
single-session-assistant 2 of 22.

The best variant passing every synthetic gate is **MiniLM-L6, first 512 characters, top 20**:
+17 complete-evidence questions at about 250 ms median added time on CPU. That is far above the
held-out plan's default latency condition of +3 ms, which was written for changes to the default
path. A re-ranker can only be an opt-in setting, and its latency budget is an owner decision before
the variant is frozen.

Selection used retrieval_v3 as a gate, so v3 is no longer independent evidence for this choice.
LoCoMo, untouched, decides.
