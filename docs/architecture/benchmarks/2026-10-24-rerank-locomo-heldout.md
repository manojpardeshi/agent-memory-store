# Re-Ranking — LoCoMo Held-Out Decision

Date: 2026-10-24
Status: **passed; LoCoMo look 1 of 3.**
Frozen candidate and rule: `evaluation/memorybench/rerank-minilm-c512-k20-v1-frozen.json`
(commit c572178), frozen before any LoCoMo scoring.
Ledger: `evaluation/memorybench/held-out-ledger.json` records the look and its verdict, applied
mechanically by `verdict()` in `scripts/locomo_heldout.py`.
Data: LoCoMo-10 (Maharana et al., snap-research/locomo, CC BY-NC 4.0), downloaded at run time and
never committed. 1,536 questions in categories 1–4 have parseable evidence; 4 were excluded for
unparseable evidence, and category 5 (adversarial) is out of scope. Free and local.

## Candidate

Vector recall's top 50 with the relevance filter off. Take the first 20 and re-score each by the
MiniLM-L6 cross-encoder (`Xenova/ms-marco-MiniLM-L-6-v2`, Apache-2.0) on its first 512
characters. Keep the top 10, ties keeping vector order. The candidate was tuned on the
LongMemEval-S development 180 only (`2026-10-23-rerank-tuning.md`).

## Result

| Metric | Vector | Re-ranker | Rule |
| --- | ---: | ---: | --- |
| Complete evidence in top 10 | 805 | **924** | at least 836 (baseline + 2%): **pass** |
| Evidence recall | 0.579 | 0.657 | — |
| Category 1 | 49 / 282 | 64 / 282 | loss at most 2: **pass** |
| Category 2 | 210 / 321 | 229 / 321 | loss at most 3: **pass** |
| Category 3 | 22 / 92 | 28 / 92 | loss at most 0: **pass** |
| Category 4 | 524 / 841 | 603 / 841 | loss at most 8: **pass** |
| Per-query time, median / p95 | 7.2 / 11.1 ms | 148.9 / 195.3 ms | +500 / +750 ms: **pass** |

Category labels follow the dataset's numbers. MemoryBench calls 1–4 single-hop, multi-hop,
temporal, and world-knowledge; the LoCoMo paper numbers its categories differently.

## Reading

On a held-out dataset from a different distribution, never used for tuning, re-ranking put every
answer-bearing turn in the top ten for 119 more questions (+14.8%). Every category improved. The
tuning-set loss on LongMemEval single-session-assistant (2 of 22) did not recur as a category loss
here. The latency cost is real: about 140 ms added per recall on this Mac's CPU. That is why the
re-ranker ships only as an opt-in setting.

Answer quality is not measured, so no answer gain is claimed. LoCoMo has two looks left.
