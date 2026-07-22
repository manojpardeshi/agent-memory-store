# Retrieval Quality Gate v1

Date: 2026-07-19
Status: **failed; public-release quality gate remains closed**

## Claim and limits

This is a heuristic product gate over one versioned, synthetic personal/project corpus. It is not a universal retrieval benchmark and contains no user-derived memories. The run used the pinned `BAAI/bge-small-en-v1.5` FastEmbed path with local files only; it opened no network listener and made no model-provider calls.

## Corpus

- Dataset: `evaluation/retrieval_v1.json`
- Dataset SHA-256: `a5360cc957e9defe51363b20b5e179668dad553365d6f4bf8ae056202f450889`
- 50 synthetic memories and 50 queries.
- Exactly 10 memories for each type: turn, fact, preference, summary, and event.
- Private exact scopes and explicitly selected shared pools.
- Every query identifies one expected memory, one accessible but irrelevant distractor, and one inaccessible-scope control.
- Each distractor was manually chosen from the same permitted scope or pool to be topically unrelated to the expected answer; these are neutral relevance controls, not adversarial near-duplicates.
- Retrieval depth: top five.

## Threshold decision

Recall and MRR regression floors were calibrated after observing the first real baseline. Zero scope violations is a hard security invariant. The 0.10 distractor ceiling is a normative context-quality target, not an empirically fitted noise floor:

| Metric | Threshold | Baseline | Result |
| --- | ---: | ---: | --- |
| Recall@5 | at least 0.90 | 0.98 (49/50) | Pass |
| Mean reciprocal rank | at least 0.85 | 0.98 | Pass |
| Designated distractor leak rate | at most 0.10 | 0.24 (12/50) | **Fail** |
| Uniform-random distractor control | diagnostic only | 0.40 expected (20/50) | Model is 40% better than random |
| Inaccessible-scope violations | 0 | 0 | Pass |
| End-to-end runtime | at most 60 s | 0.47 s | Pass |
| Dataset coverage | at least 50 queries and one memory of every type | 50 and ten/type | Pass |

The recall and MRR floors leave measured regression margin below the initial 0.98 baseline. Because eligible per-query corpora contain 10–15 items, a uniform-random top-five ranking would expose the designated distractor 40% of the time. The model's 24% is better than that noise floor, so it is not by itself proof of a general retrieval defect. The stricter 10% ceiling expresses the product requirement that top-five context should rarely include a known unrelated item; it is intentionally not relaxed to manufacture a pass.

Leakage is not evenly distributed. Private exact-scope queries leaked 10/25 distractors (0.40), exactly equal to their 0.40 uniform-random expectation: no measured improvement over chance in that stratum. Shared-pool queries leaked 2/25 (0.08) against their 0.40 random expectation, an 80% reduction. The aggregate 40% reduction is therefore entirely driven by shared-pool performance and must not be read as broad-based improvement. By distractor memory type the rates were: fact 0.10, summary 0.20, event 0.27, preference 0.30, and turn 0.33. Small private corpora and unconditional top-five filling are the first diagnostic target, not the embedding model generally.

## Security and correctness result

Exact scope isolation passed: no memory designated inaccessible to a query appeared in any ranking. Distractor leakage is not a scope breach—the leaking items were intentionally accessible. Shared-pool ranking beats its uniform-random control, while private exact-scope ranking does not. Irrelevant context still increases prompt-injection exposure, so the normative quality gate remains useful as a conservative defense-in-depth target.

## Decision

OQ-009 is resolved as a measurement contract, but the current implementation does not pass its normative relevance target. Keep the repository private. The next retrieval-focused cycle should examine score calibration and minimum-relevance filtering, particularly for small private scopes, without changing this recorded baseline or silently tuning the gate.

Machine-readable evidence is preserved in `2026-07-19-retrieval-quality-v1.json`.
