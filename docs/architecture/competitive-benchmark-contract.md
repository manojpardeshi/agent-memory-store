# Competitive Benchmark Contract

Date: 2026-07-30
Status: accepted protocol; retrieval and Kimi evaluator qualification complete; comparators pending

## Purpose

Establish a reproducible standard-benchmark baseline before changing product retrieval. The
benchmark is competitive evidence, not a replacement for the deterministic synthetic safety and
regression gates.

The bounded claim under evaluation is:

> The store can provide retrieval quality non-inferior to matched local memory systems while
> preserving inspectable single-file storage, exact scope isolation, provenance, verified lifecycle
> operations, and an offline-capable core.

This contract does not authorize an unqualified claim that the project is “better than” another
memory system.

## Frozen external inputs

| Input | Frozen value |
| --- | --- |
| Benchmark | LongMemEval-S, 500 questions |
| Dataset URL | `https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json` |
| Dataset bytes | `277383467` |
| Dataset SHA-256 | `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442` |
| MemoryBench repository | `https://github.com/supermemoryai/memorybench` |
| MemoryBench revision | `118209a746d97d0d85e5a7234267f0b6962857e9` |
| Question categories | 70 single-session-user, 56 single-session-assistant, 30 single-session-preference, 133 multi-session, 133 temporal-reasoning, 78 knowledge-update |

The dataset is downloaded into an ignored working directory and is never vendored into this
repository. A run must fail before ingestion if its byte size or digest differs.

Competitive context was checked against the official
[Mem0 repository](https://github.com/mem0ai/mem0),
[Mem0 benchmark suite](https://github.com/mem0ai/memory-benchmarks),
[Supermemory repository](https://github.com/supermemoryai/supermemory), and
[MemoryBench documentation](https://supermemory.ai/docs/memorybench/overview) on 2026-07-24.
Published managed-platform scores remain claims by their respective projects, not matched local
results for this contract.

## Tracks

### Track A: raw deterministic ingestion

This track isolates the released store's retrieval path from its known extraction-quality failure.
Each benchmark message becomes one `turn` memory in a question-specific exact private scope.
The stable formatted content contains the session identifier, role, and source-session timestamp
before the message body. The source timestamp and message index also remain metadata. Benchmark
turns have no TTL. A source message whose body is empty or whitespace-only becomes the explicit
placeholder `[empty source message]`, retains its original message index, and records
`source_content_empty=true`; non-string bodies remain invalid.

The adapter uses the product-default embedder and relevance policy. It must not add lexical,
temporal, reranking, query-rewriting, or diversity logic that the product does not ship.

### Track B: review-first extraction

This diagnostic track will feed the same raw sources through the released proposal workflow and a
separately pinned extractor. It remains non-comparable to automatic competitor ingestion unless the
acceptance policy is specified. Track B is not part of the first adapter slice and must never be
merged with Track A results.

## Isolation and lifecycle

- Each MemoryBench `containerTag` maps through SHA-256 to a separate SQLite database.
- The unhashed container tag does not become a filesystem path.
- Search uses only that container's exact private scope.
- Ingestion is idempotent by session and message index.
- The adapter exposes explicit clear behavior for benchmark artifacts only.
- The adapter is a stdio JSON-lines bridge. It does not add a network listener or a shipped runtime
  service.
- Diagnostics go to stderr; stdout contains protocol messages only.

## Comparison protocol

1. Publish or commit the adapter, configuration, and this contract before product tuning.
2. Run a small deterministic smoke sample spanning all six question categories.
3. Require the frozen answerer/judge pair to use retrieved support correctly in a six-category
   pilot, then run all 500 questions for the released store without modifying retrieval.
4. Run matched local comparator configurations on the same machine. Managed-platform headline
   scores are context only and cannot be placed in the comparison table as equivalent results.
5. Use identical MemoryBench dataset files, question selection, search depth, answering model,
   judge model, prompts, and concurrency where provider constraints permit.
6. Record every unavoidable asymmetry, including ingestion and embedding models.
7. Repeat any nondeterministic answer/judge stage or report uncertainty; do not select the best run.

The benchmark evaluator may use a hosted answering or judge model over the public dataset. That is
evaluation infrastructure only and does not change the offline product boundary. Credentials and
raw benchmark work files remain outside the repository.

## Required report fields

- Repository commit and dirty-state flag.
- Dataset and MemoryBench identities from the frozen-input table.
- Provider name, version, configuration, and ingestion track.
- Hardware and operating-system summary.
- Embedding, answering, and judge model identities.
- Question selection and per-category counts.
- Search depth and effective product relevance policy.
- Per-category and overall answer accuracy.
- Retrieval metrics reported by the pinned framework.
- Context-token counts.
- Ingest/index/search/answer/judge latency, including search p50 and p95.
- SQLite and total provider on-disk bytes after ingestion.
- Failed operations, retries, and any deviations from this contract.

## Pre-registered interpretation

The initial non-inferiority candidate is Recall@5 no more than five percentage points below the best
matched local comparator at equal or fewer average context tokens. MemoryBench revision
`118209a...` currently fixes its standard search request to ten results, so Recall@5/Recall@10
reporting requires a shared framework change or a separate retrieval pass applied identically to
all providers before this candidate can be evaluated.

Privacy and correctness remain independent hard gates:

- Zero inaccessible-scope results in the internal suite.
- No regression beyond the existing Recall@5, MRR, distractor, and latency floors.
- Full provenance for every result returned by the store.
- Existing deletion, correction, import/export, backup/restore, and migration tests pass.

No threshold is changed after observing the baseline. If the first full run cannot compute the
pre-registered comparison fairly, it is reported as diagnostic and the protocol is amended before
product tuning.

The 2026-07-24 loopback `llama3.1:8b` smoke passed the adapter and retrieval path but failed this
evaluator gate: all six labeled support sets appeared in the top 10, while the answerer produced
zero usable answers. The configuration is frozen as diagnostic evidence and is not expanded to a
full answer-quality run.

Exact model `claude-opus-5`, resolved from the Claude CLI `opus` alias with Claude Code 2.1.219,
passed the budget-bounded six-category evaluator pilot at 5/6 correct for $1.024665. The alias
itself is not a frozen identity. The CLI reported auxiliary Haiku 4.5 usage even with tools and
prompt suggestions disabled, and the same Opus model answered and judged. Those asymmetries remain
mandatory report fields. A linear full-run estimate plus 20% margin exceeds the available $100
credit, so the pilot does not authorize the full 500-question run.

The frozen 60-question stratified diagnostic subsequently completed at 47/60 (78.3%) for
$9.108015 with Claude Code 2.1.220. Its labeled answer-session diagnostic measured 95% hit@10 and
92.6% answer-session recall@10; these are not MemoryBench's separate LLM-labeled retrieval metrics.
Multi-session accuracy was 3/10 and temporal accuracy was 5/10, while the other four categories
were 39/40 combined. An identically configured complementary paid Opus run was initially approved
as the only valid way to extend that result without rerunning the observed 60.

That Opus expansion plan was later superseded when the owner supplied direct Kimi API credit and
reserved Claude for architecture work. The completed Opus 60 remains a separate diagnostic and
must not be merged with Kimi results as one score. The 440-question complement may be run locally
without an answerer to complete retrieval evidence for the released store.

Exact direct-API `kimi-k3` passed automated evaluator mechanics on a deterministic 20-question
development sample: 15/20 majority answer accuracy, 96.7% judge-vote unanimity, 96.7% pairwise
answer-repeat agreement, and 1/20 on an empty-context control for $1.459725 total. Since the same
base model answered and judged, Claude Opus 5 froze five judge-concordance gates before Kimi saw 30
human-scored `claude-opus-5` answers. Kimi passed at 28/30 overall human agreement, 16/17
human-positive, 12/13 human-negative, zero positive-count drift, and 28/30 unanimous. This
qualifies Kimi judge behavior only. A separate independent blind audit then scored actual
first-pass `kimi-k3` answers at 17/20, above the frozen 14/20 gate; exact provenance validation
matched all 20 answers to the raw Kimi run. These separate audits qualify the frozen Kimi answerer
and judge protocol. Development, sealed validation, and reserve manifests are disjoint; no
validation or reserve question may be inspected during product selection.

The released store subsequently completed local retrieval for all 500 questions by combining the
observed 60 checkpoint with its frozen 440 complement. The deterministic public session-label
diagnostic measured 97.0% Hit@10, 92.1% answer-session recall@10, and 0.910 MRR@10. Multi-session
and temporal answer-session recall were weakest at 89.2% and 85.8% at depth ten. These are not
MemoryBench's LLM relevance metrics and do not complete answer-quality or comparator evidence.

The first retrieval candidate was frozen before execution as `session-diverse-v1`: unchanged
ranked pool 50, at most two single-message results per provenance session, ten original-order
slots, and original-order backfill. On the 180-question development split it passed every frozen
retrieval and operational gate. Answer-session recall@10 improved from 92.80% to 95.74%, temporal
recall from 83.48% to 90.72%, and mean formatted context bytes fell 13.2%, with no question-level
recall loss. The candidate remains default-off pending matched development answer-quality evidence.
Sealed validation and reserve remain unopened.

The matched 60-question development answer run subsequently failed the frozen automated gates.
Exact `kimi-k3` scored the released baseline at 45/60 and `session-diverse-v1` at 40/60, with 3
candidate-only correct answers and 8 baseline-only correct answers. The candidate did not improve
the combined multi-session and temporal target and regressed single-session-user by three answers.
Mean context bytes and answer-call cost fell, but those efficiency gains do not override answer
quality. Total spend was $4.147215. The blind audit of 13 unique disputed or non-unanimous
questions plus 3 reliability duplicates passed its human gates at 100% intrarater and 88.46%
human–judge agreement. Authoritative substitution rescored the baseline at 47/60 and candidate at
41/60, with 1 candidate win and 7 losses. All five answer-quality gates remained failed. The
candidate is rejected; sealed validation and reserve remain unopened.

A reproducible non-tuning diagnostic then examined only the 11 machine-judge-discordant development
questions. Distinct retrieved sessions increased from 30 to 69, while messages belonging to labeled
answer sessions fell from 90 to 37 even though full answer-session coverage remained 11/11 in both
arms. Seven of eight candidate losses directly pruned the answer-bearing message; one additional
loss was an unsupported inference after context perturbation. This explains why session-level recall
was an insufficient gate.

A possible follow-up is documented only as a blocked draft. It starts from the released top ten and
permits at most two new-session swaps with no more than 0.03 composite-score loss per swap, retaining
at least eight original messages. Those bounds were selected after observing development evidence
and are disclosed as post-hoc. A separate fictional 60-case density/diversity corpus has been
independently authored and checked for zero normalized 12-token overlap with LongMemEval; its
cross-review is incomplete because the density repair invalidated the earlier review of the author-B
half. Neither the policy nor its draft contract is frozen or authorized for execution. The
completed v1 human audit resolves one prerequisite; the outstanding cross-review, the frozen
fresh-corpus baseline, and an explicit freeze review remain prerequisites.

That corpus is a **screening instrument, not promotion evidence.** It is self-authored, and its
message/session topology was deliberately revised so that a two-swap policy has room to operate — the
first revision was rejected precisely because 4–8-message cases made top-ten retrieval exhaustive.
A corpus shaped to let a candidate act cannot demonstrate superiority; it can only demonstrate
non-harm on its 40 dense-evidence cases plus targeted benefit on its 20 diversity-required cases.
This is an epistemic downgrade from `session-diverse-v1`, which was judged on an external public
benchmark. A Stage 1 or Stage 2 pass therefore authorizes only a request to run one LongMemEval
sealed comparison, which remains the sole promotion evidence.

## Cumulative paid-evaluation ledger

Each run enforces its own hard ceiling; this table is the roadmap-level total. It records evaluator
spend only. Human audit stages are unpaid.

| Run | Evaluator | Cost (USD) |
| --- | --- | ---: |
| Six-category evaluator pilot | `claude-opus-5` | 1.024665 |
| Stratified 60-question diagnostic | `claude-opus-5` | 9.108015 |
| Kimi qualification, empty-context control, and judge-concordance audit | `kimi-k3` | 1.705712 |
| `session-diverse-v1` paired answer run | `kimi-k3` | 4.147215 |
| **Total spent to date** | | **15.985607** |
| Requested but unauthorized: `session-density-v2` Stage 2 | `kimi-k3` | ≤ 5.000000 |

To date this spend has produced one qualified answerer/judge protocol, a complete retrieval baseline,
and two rejected candidates. That is the intended outcome of baseline-before-tuning, but a third
consecutive negative result should trigger the abandonment criterion in the product roadmap rather
than another paid run against the same hypothesis. Approval is per run and does not carry forward.

## Decision rule for the next product slice

- Predominantly entity, identifier, number, or exact-phrase misses: evaluate SQLite FTS5/BM25 plus
  vector fusion.
- Predominantly temporal-reasoning or knowledge-update misses: evaluate explicit temporal/update
  retrieval before lexical fusion.
- High relevant recall with excessive or redundant context: evaluate context-bundle diversity and
  budget control.
- Large gap between Track A and Track B: extraction is the bottleneck; do not tune retrieval to hide
  ingestion loss.

Only one material memory-system variable changes in the first paired improvement.

**Superseded by AD-052.** The stratified evidence originally pointed to provider-neutral
session-diverse context bundling: eleven of thirteen wrong answers had at least one labeled answer
session in the top 10, while multi-session recall fell from 80.5% at 10 to 59.0% at 5. That
provisional selection was executed as `session-diverse-v1`, failed its human-adjudicated answer gate
at 41/60 versus 47/60, and was rejected. It never reached sealed validation and must not be re-read
as live guidance.

The residual evidence relocates the failure from session diversity to message selection: seven of
eight paired losses pruned the specific answer-bearing message while full answer-session coverage was
preserved in both arms. One bounded follow-up (`session-density-v2`) is drafted under the
context-bundling abandonment criterion in the product roadmap. If it fails, selection returns to the
decision rule above and evaluates a materially different mechanism.

## Explicit non-goals

- Reproducing proprietary managed-platform scores.
- Adding connectors, document RAG, graph memory, multimodal ingestion, or a consumer application.
- Retuning extraction prompts on the existing frozen corpora.
- Shipping MemoryBench, LongMemEval, or evaluator dependencies in the Python distribution.
- Using owner memory, telemetry, or private conversations in competitive evidence.
- Implementing retention tombstones during this phase.
