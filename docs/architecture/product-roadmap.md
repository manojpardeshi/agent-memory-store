# Product Roadmap

Last updated: 2026-08-02
Status: active; post-0.1 roadmap ordered by evidence and competitive risk

## Product direction

Build the most auditable, private, provider-neutral local memory layer whose retrieval quality is
non-inferior to leading local memory systems under matched conditions. The product does not attempt
feature-for-feature parity with hosted context platforms. Its intended advantage is the combination
of useful recall with inspectable single-file storage, exact scope isolation, explicit provenance,
verified lifecycle operations, offline-capable core behavior, and reproducible evidence.

The 0.1 cycle established the safety and portability foundation. The post-0.1 cycle must establish
standard benchmark evidence before changing retrieval behavior. Small synthetic corpora remain
regression gates, but they are not competitive evidence.

## Post-0.1 ordered phases

| Order | Phase | Outcome | Entry condition | Exit evidence |
| ---: | --- | --- | --- | --- |
| 1 | Competitive baseline | A frozen LongMemEval-S protocol measures the released store before product tuning and supports matched local comparisons. | Published 0.1.0 and stable internal retrieval gates. | Pinned dataset/framework, provider adapter, raw-ingestion baseline, per-category accuracy, retrieval/context/latency/footprint evidence, and pre-registered comparison rules. **In progress: retrieval-only evidence is complete for all 500 at 97.0% Hit@10 and 92.1% answer-session recall@10. That aggregate includes the 150 sealed-validation and 170 reserve questions, so their retrieval statistics are already observed; sealed validation remains unopened for answer quality only. Kimi passed the independent answerer gate at 17/20 on actual Kimi answers and the separate judge gate at 28/30 human agreement on Opus answers. No sealed answer run has started.** |
| 2 | First measured retrieval improvement | The largest baseline retrieval gap is improved without weakening privacy or internal quality gates. | Frozen retrieval baseline and written error analysis. | Paired before/after LongMemEval-S evidence plus unchanged internal Recall@5, MRR, distractor, latency, and zero-scope-leakage gates. **Completed negative result: default-off session-diverse v1 passed retrieval gates but failed the final human-adjudicated answer gate at 41/60 versus 47/60 baseline. Human reliability and judge-agreement gates passed. The candidate is rejected and does not advance to sealed validation.** |
| 3 | Second measured memory-quality improvement | The next dominant failure class is addressed independently. | Phase 2 evidence and residual-error analysis. | Paired standard-benchmark evidence. **Closed without execution on 2026-08-02 under the abandonment criterion below. The `session-density-v2` candidate's ceiling was one to three answers on sixty questions, below the measurement's noise floor, while twelve of thirteen observed answer errors fell in multi-session and temporal-reasoning — categories whose retrieval already succeeds. The independently authored and cross-reviewed 60-case corpus is retained unfrozen as a reusable screening instrument; no baseline runner was built and no paid run was made. See AD-053.** |
| 4 | Matched local comparator runs | Mem0 and Supermemory are measured on the same machine, dataset, and depth, completing the Phase 1 exit condition and making every later quality decision informed rather than blind. | Phase 3 closed; pinned MemoryBench revision and working adapter. | Matched comparator configurations, disclosed asymmetries, and per-category retrieval/context/latency/footprint evidence. **Active — the only unmet Phase 1 exit condition.** |
| 5 | Multi-session and temporal synthesis | The dominant answer-failure class is addressed where the loss actually occurs, downstream of retrieval. | Phase 3 closed and residual error analysis of retrieval-succeeded/answer-wrong questions. | Written diagnosis distinguishing context formatting, ordering, prompt construction, and reader capability, then one pre-registered paired change. **Not started.** |
| 6 | Retention tombstones | Expired source payloads retained only for live provenance can be redacted without orphaning descendants. | Two benchmark-driven quality releases or concrete user retention evidence. | Approved schema/interchange/migration contract, explicit rollback boundary, and end-to-end redaction verification. **Paused.** |

### Context-bundling abandonment criterion — invoked 2026-08-02

Phases 2 and 3 tested one hypothesis: that provider-neutral changes to which retrieved messages
enter the context bundle improve answer quality. **That hypothesis is now closed.** Phase 2 failed
under human adjudication, and Phase 3 was closed without execution because its ceiling was smaller
than the noise floor of the measurement that would evaluate it. No further bundling variant, swap
count, score threshold, cap grid, or adjacent-expansion rule may be proposed.

Two independent lines of evidence support the closure:

- **Ceiling.** The v1 paired run scored baseline 47/60 against candidate 41/60 under human
  adjudication, with one candidate win and seven candidate losses. A v2 that avoids every loss and
  keeps every win reaches about 48/60, or 50/60 under the more generous machine scoring. A one- to
  three-answer delta on sixty questions cannot be distinguished from noise.
- **Location of the loss.** On the Opus stratified sixty, four categories scored 39/40 combined
  while multi-session scored 3/10 and temporal-reasoning 5/10. Answer-session recall@10 for those
  two categories is already 0.892 and 0.858, and the v1 discordance diagnostic recorded full
  answer-session coverage in both arms on all eleven disputed questions. Retrieval is comparably
  strong everywhere; answers collapse only where evidence must be composed across sessions or
  reasoned over dates.

The synthesis headroom in those two categories is roughly twelve answers — several times anything
top-ten reordering can deliver. Selection was therefore the wrong optimization target, and effort
moves to Phase 4 (matched comparators, to stop deciding blind) and Phase 5 (synthesis).

Reopening requires evidence that message selection rather than synthesis dominates multi-session or
temporal failure. The unfrozen `session-density` corpus and its completed cross-review are retained
as a reusable screening instrument should that evidence appear.

## No paid evaluation — owner decision, 2026-10-02

The owner stopped all spending on kimi-k3, hosted Mem0, Supermemory, and similar paid services.
Answer quality, which needs a strong paid answerer and judge, is therefore no longer measured. Free
local models proved unreliable as answerers and must not be presented as answer evidence.

Retrieval candidates are now judged on free, deterministic signals: evidence-level recall from
LongMemEval's `has_answer` turn labels (`benchmarks/2026-10-02-evidence-recall-baseline.md`), the
internal synthetic suites, latency, and footprint. A frozen contract with a paid stage stops at its
free stage. Results on the final completed comparison stand: store 134/180, hosted Mem0 Hobby tier
93/180 (`benchmarks/2026-09-30-mem0-hosted-dev180.md`).

### First free retrieval improvement — hybrid recall, 2026-10-02

BM25 + vector reciprocal rank fusion was tuned on the stratified sixty, frozen, and confirmed on the
120 design-blind questions. Complete evidence rose from 80 to 91 of 117, with no category losing
(`benchmarks/2026-10-02-hybrid-retrieval-prototype.md`). It shipped as an opt-in `retrieval="hybrid"`
backed by a trigger-maintained, secure-delete FTS5 index. It stays off by default because it fails
the paraphrase-heavy retrieval_v2 MRR gate, 0.834 against 0.85
(`benchmarks/2026-10-02-hybrid-recall-product.md`). Next: a way to keep the keyword gain without the
paraphrase loss, judged against a new independently authored paraphrase suite rather than tuned on
retrieval_v2.

## Competitive baseline rules

- Use LongMemEval-S first because its categories isolate single-session facts, preferences,
  multi-session reasoning, temporal reasoning, and knowledge updates.
- Freeze the benchmark framework revision, dataset digest, sampling, prompts, reader/judge models,
  retrieval depth, hardware description, and provider versions before tuning.
- Compare only matched configurations. Local results must not be compared directly with proprietary
  managed-platform scores.
- Run the store first with deterministic raw-message ingestion to isolate retrieval behavior. A
  separate review-first extraction track may diagnose extraction loss, but its results must not be
  merged with the raw track.
- Pre-register non-inferiority before viewing comparator results. The initial candidate boundary is
  Recall@5 within five percentage points of the best matched local comparator at equal or fewer
  context tokens.
- Report per-category answer quality, retrieval metrics, context tokens, p50/p95 search latency, and
  on-disk size. Do not publish a single unqualified “better than” score.
- Preserve the synthetic retrieval and extraction suites as independent safety/regression gates.
- Treat answerer/judge validity as a benchmark prerequisite. A run with high labeled retrieval
  recall but systematically non-responsive answers is diagnostic evidence, not a product score.
- Preserve the completed Opus 60 as a separate diagnostic; never merge it with Kimi results as one
  answer-quality score. Run its frozen 440 complement locally for retrieval evidence.
- Use exact direct-API `kimi-k3` for worker tasks and the now-qualified frozen answerer/judge
  protocol. Keep the 17/20 Kimi-answer audit separate from the 28/30 Kimi-judge audit on Opus
  answers. Claude remains the architecture reviewer, not the bulk answerer or judge.
- Keep development, sealed validation, and reserve manifests disjoint. Product selection may use
  development only; validation and reserve remain unopened until their respective gates.
- "Unopened" is scoped to answer quality. The completed 440-question complement covered every sealed
  and reserve question for retrieval metrics, so their aggregate retrieval statistics are already
  observed and a later sealed run is not a first look at retrieval. No sealed or reserve question has
  received an answer, judge vote, or per-question score, and none may before its gate.

The detailed protocol is recorded in
[`competitive-benchmark-contract.md`](competitive-benchmark-contract.md).

## Completed 0.1 foundation

The first release implemented:

1. Versioned synthetic retrieval-quality gates and identity-scoped relevance filtering.
2. Physical expiry purge with protected live descendants.
3. New-destination embedding migration.
4. JSON v1/v2 portability and new-destination import.
5. A real-application Python/MCP starter and provider-neutral evidence demos.
6. Review-first extraction and summarization proposals.
7. Two independent extraction-quality matrices; every measured small local candidate failed the
   automation gate and was not promoted.
8. Store-aware deterministic proposal-review ergonomics.
9. Reproducible, privacy-scrubbed PyPI and Codeberg publication of version 0.1.0.

Release evidence is recorded in
[`../release/2026-07-24-publication.md`](../release/2026-07-24-publication.md).

## Deferred surface-area expansion

The current competitive position does not require connectors, document RAG, multimodal ingestion,
graph memory, a hosted service, a consumer application, multi-user authorization, or background
processing. Automatic extraction is not retuned on the existing frozen corpora. These items require
benchmark or user evidence showing that they address the dominant failure.

## Working rules

- Baseline before tuning; publish failed evidence rather than moving thresholds after a run.
- Change one material memory-system variable per paired benchmark.
- A failed quality gate is recorded, not tuned away during the same measurement cycle.
- A retrieval-only gain is insufficient when the matched answer-quality gate fails. Keep the
  observed development split immutable, complete its blind adjudication, and freeze a newly
  disclosed protocol before evaluating a materially different candidate.
- Synthetic evaluation data and public benchmark data must not include owner memory.
- No standard benchmark run creates a runtime cloud dependency for commit or recall.
- No new network listener, daemon, or multi-user boundary is implied by this roadmap.

## Parallel candidate-generation branch

`scamper-candidate-generation` runs parallel to `main` and applies a structured SCAMPER
sweep to generate replacement candidates after the context-bundling hypothesis closed with
none queued. It generates candidates only: nothing merges toward `main` on the ideation
record alone, and every candidate still requires its own frozen pre-registered contract
and explicit owner authorization before a measured run. See
[`scamper-methodology.md`](scamper-methodology.md) and the pass records under
[`scamper/`](scamper/).
