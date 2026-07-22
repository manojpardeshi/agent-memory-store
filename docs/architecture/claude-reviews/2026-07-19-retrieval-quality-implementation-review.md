# Claude Review: Retrieval Quality Gate Implementation

Date: 2026-07-19

## Prompt sent to Claude

Act as a skeptical principal architect reviewing a completed retrieval-quality gate for a private, local-first personal LLM memory store. Use only the facts below. Return sections Verdict, Ship blockers, Metric/threshold assessment, Small improvements, and Next-cycle recommendation. Do not inspect or edit files.

Implementation facts:

- A dependency-free Python evaluation module validates a schema-v1 JSON corpus, seeds an isolated temporary SQLite/sqlite-vec store, runs normal production recall, scores results, and deletes the temporary store.
- A new `llm-memory evaluate-retrieval` CLI command supports FastEmbed or a deterministic test embedder, an `--offline` flag that makes FastEmbed require cached local files, optional owner-only JSON report output, refusal to overwrite without an explicit flag, and nonzero exit when a threshold fails.
- The versioned corpus has 50 wholly synthetic memories and 50 queries, with exactly ten memories of each type: turn, fact, preference, summary, and event. It covers private exact scopes and explicitly selected shared pools.
- Every query has one expected memory, one accessible but deliberately irrelevant distractor, and one memory in an inaccessible scope. Retrieval depth is top five.
- The harness computes micro Recall@5, mean reciprocal rank, designated distractor leak rate, inaccessible-scope violation count, runtime, query-count coverage, and type coverage. It preserves per-query rankings using synthetic fixture IDs but not memory bodies.
- Dataset integrity is pinned with SHA-256; the report records embedding model/revision/runtime/dimension and labels the result a heuristic single-corpus product gate rather than a universal benchmark.
- Thresholds were chosen after the first real baseline: Recall@5 >= 0.90, MRR >= 0.85, designated distractor leak <= 0.10, zero inaccessible-scope violations, at least 50 queries with all five types, and runtime <= 60 seconds.
- Real offline `BAAI/bge-small-en-v1.5` / FastEmbed 0.8.0 baseline: Recall@5 0.98 (49/50), MRR 0.98, distractor leak 0.24 (12/50), scope violations 0, runtime about 0.47 seconds. The gate is recorded as failed and the repository remains private; the distractor ceiling was not relaxed to manufacture a pass.
- The deterministic token-hash embedder is used only for fast metric/contract tests, never to set product thresholds.
- Fourteen new evaluation tests bring the full suite to 43 passing tests. They cover schema validation, role/type rules, reference/accessibility validation, integer thresholds, perfect and failed scoring, distractor and scope violations, duplicate rankings, isolated end-to-end execution, private report permissions/no-overwrite, and production-fixture coverage.
- Architecture decisions AD-028 and AD-029, the active roadmap, OQ-009 status, a human decision report, and machine-readable evidence are updated.

Review for correctness and overclaiming. In particular: Is the designated-distractor-in-top-five metric defensible with one labeled distractor per query and small per-scope corpora? Is the 10% ceiling reasonable as a product gate even though the observed baseline is 24%? Should this slice ship while the gate itself fails? Identify concrete blockers only; do not request a redesign unless necessary.

## Claude response (preserved with minor copy-editing)

### Verdict

The evaluation harness is well-engineered and, most importantly, honest: it failed the gate on real data and kept the repo private rather than relaxing the threshold to force a pass. That discipline is worth more than the numbers themselves. But the specific metric that failed—designated-distractor leak—is the least trustworthy part of this gate as constructed, and the story behind its 0.10 threshold doesn't hold together against the reported baseline. Ship the tooling and tests; don't yet treat "24% leak" as proven evidence of a retrieval defect, and don't relax the number without diagnosing it first.

### Ship blockers

1. **Threshold-calibration story is internally inconsistent.** Thresholds are described as "chosen after the first real baseline," yet the baseline reported here misses the leak threshold by 2.4x while comfortably clearing Recall@5 and MRR. Either the calibration baseline differed from the reported one, or the leak threshold was set without reference to measured leak behavior. Undocumented, this casts doubt on whether any of the thresholds were empirically grounded rather than asserted.
2. **No noise-floor control for the leak metric.** With approximately 49 candidate memories and top-five depth, a uniformly random retriever would leak the designated distractor roughly 10% of the time by chance alone—which is exactly where the ceiling was set. A real embedding model landing at 24% could mean genuine semantic confusion, or it could mean same-type/same-scope memories are inherently close in embedding space at this corpus size. Without a random-embedding control run, the gate can't distinguish these.
3. **Distractor construction rules aren't specified.** If distractors were authored to be maximally confusable to stress-test the retriever, a high leak rate is an expected byproduct of the test design, not a product bug. If they were meant to be topically neutral, 24% is a real signal. This ambiguity has to be resolved before the number means anything to a reader who isn't in the room.

### Metric/threshold assessment

- **Recall@5 ≥ 0.90 / MRR ≥ 0.85**—reasonable, well-calibrated. Baseline (0.98/0.98) clears both with real margin, consistent with a threshold set below observed performance.
- **Zero inaccessible-scope violations**—correct as a hard, non-negotiable gate. This is a security property, not a quality one.
- **Runtime ≤ 60s / coverage checks**—sane sanity gates.
- **Distractor leak ≤ 0.10**—the weak link. It needs recalibration or reinterpretation, not blind enforcement.

### Small improvements

- Add a shuffled/random-embedding control run so every leak-rate report is shown alongside its expected chance-level floor for that corpus size.
- Document the distractor-authoring rule explicitly.
- Reconcile AD-028/AD-029 with the actual calibration data.
- Stratify leak rate by type/scope pair; 12/50 failures could be concentrated rather than evenly spread.

### Next-cycle recommendation

Before touching retrieval code or the threshold value, add the random-baseline control to establish the true noise floor, then inspect the 12 leaking queries individually. Only after that root-cause pass should the team decide whether to fix retrieval, redesign the distractor set, or revise the threshold with documented justification.

## Reconciliation

All blockers were addressed before shipment. The harness now computes the exact deterministic uniform-random top-K expectation from each query's eligible candidate count rather than assuming all 50 memories are candidates. Because scope filtering leaves 10–15 candidates, the actual random floor is 0.40; FastEmbed's 0.24 leakage is a 40% reduction versus random. The report no longer calls this proof of a general retrieval defect.

The dataset now requires and records its distractor policy: one manually selected, topically unrelated memory from the same accessible scope or pool, not an adversarial near-duplicate. Leakage is stratified by memory kind and access mode. Private exact scopes account for 10/25 leaks (0.40) while shared pools account for 2/25 (0.08), making small private corpora and unconditional top-five filling the next diagnostic target.

The calibration story is now explicit: Recall and MRR are baseline-calibrated regression floors; zero scope leakage is a hard invariant; the 0.10 distractor ceiling is a normative defense-in-depth product target. AD-029, the human report, roadmap, and README use that wording. The gate remains failed without weakening its target or overstating what the failure proves.

## Follow-up prompt sent to Claude

We applied your blockers as follows. The harness now computes an exact uniform-random top-K leak expectation using each query's actually accessible candidate count. Scope filtering leaves 10–15 candidates, so random top-five leakage is 0.40; measured FastEmbed leakage is 0.24, a 40% reduction versus random. The dataset now records that each distractor is manually selected from the same accessible scope/pool but is topically unrelated, not an adversarial near-duplicate. Reports stratify leakage: private exact scopes 10/25 (0.40), shared pools 2/25 (0.08), plus rates by memory type. Documentation no longer calls 0.24 proof of a retrieval defect. It states Recall/MRR are baseline-calibrated regression floors, zero scope leakage is a hard invariant, and 0.10 is a normative defense-in-depth context-quality target. The gate remains failed and the next investigation is small-private-scope score calibration/minimum relevance filtering. Tests and machine evidence were updated. Are any concrete ship blockers left for committing this evaluation slice? Reply with Verdict, Remaining blockers, and Next action only. Do not inspect or edit files.

## Claude follow-up response

### Verdict

Conditional pass—one blocker remains before this is committable.

### Remaining blocker

The private-exact-scope leakage (10/25 = 0.40) exactly equals the aggregate random baseline (0.40), meaning that stratum shows zero measured improvement over chance—but only an aggregate random baseline was reported. Since private scopes are the sensitive case, the report needs private-exact and shared-pool random baselines separately. Otherwise the aggregate 40% improvement could come solely from shared-pool performance while masking a null private-scope result.

### Next action

Add per-stratum random-baseline expectations before commit. If private exact scopes show no signal over chance, keep that as the headline finding for the small-private-scope calibration follow-up rather than letting the aggregate imply broad improvement.

## Final reconciliation

The requested per-stratum controls are now machine-reported. Private exact-scope leakage is 10/25 (0.40) against 10 expected random hits (0.40), a 0% reduction. Shared-pool leakage is 2/25 (0.08) against 10 expected random hits (0.40), an 80% reduction. The human report, README, and roadmap explicitly state that the aggregate improvement is entirely shared-pool-driven and that private-scope retrieval shows no relevance signal over chance under this top-five control. This resolves the reporting blocker without changing retrieval behavior or weakening the gate.
