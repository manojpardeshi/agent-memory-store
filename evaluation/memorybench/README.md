# MemoryBench Adapter

This directory contains the first competitive-baseline adapter. It targets MemoryBench revision
`118209a746d97d0d85e5a7234267f0b6962857e9` and the contract in
`docs/architecture/competitive-benchmark-contract.md`.

## Current status

- The Python stdio bridge implements raw deterministic ingestion, synchronous indexing, exact
  container isolation, product-default recall, and explicit cleanup.
- `provider.ts` implements the pinned MemoryBench `Provider` interface.
- Deterministic bridge tests do not download models or benchmark data.
- A one-question-per-category smoke completed on 2026-07-24. Retrieval found every labeled support
  item in the top 10, but the local 8B evaluator produced 0/6 usable answers. See
  `docs/architecture/benchmarks/2026-07-24-longmemeval-smoke.md`.
- A 60-question stratified Opus 5 diagnostic completed on 2026-07-30 at 47/60 for $9.108015. See
  `docs/architecture/benchmarks/2026-07-30-longmemeval-opus5-stratified60.md`.
- The local, API-free 440-question complement completed. Combined with the prior 60, the released
  store's 500-question session-label diagnostic measured 97.0% Hit@10 and 92.1% answer-session
  recall@10. This is retrieval evidence, not answer accuracy or MemoryBench LLM relevance.
- Exact direct-API `kimi-k3` passed the automated 20-question mechanics and empty-context controls.
  Its judge behavior passed every pre-registered blind human audit gate on 30 Opus-generated
  answers, and actual first-pass Kimi answers separately passed the frozen human answerer gate at
  17/20. Mechanics/judge-audit spend was $1.705712, excluding the earlier $0.002172 connectivity
  probe; human answer scoring reused existing outputs at no API cost.
- A full LongMemEval-S answer-quality run and matched local comparator runs have not yet completed.
- Default-off `session-diverse-v1` passed every frozen retrieval gate on the 180-question
  development split: answer-session recall@10 rose from 92.80% to 95.74%, temporal recall from
  83.48% to 90.72%, and mean formatted context bytes fell 13.2%.
- The subsequent matched 60-question Kimi answer run failed at 45/60 baseline versus 40/60
  candidate. Its completed blind audit passed at 100% intrarater and 88.46% human–judge agreement,
  then authoritatively rescored baseline 47/60 versus candidate 41/60. The candidate remains
  default-off and rejected; sealed validation and reserve are unopened.
- The reproducible discordance diagnostic found that session diversity increased 30→69 across the
  11 disputed questions while labeled answer-session messages fell 90→37. Seven of eight candidate
  losses pruned the direct answer-bearing message. This is diagnosis-only evidence.
- A new 60-case fictional density/diversity corpus has been independently authored, cross-reviewed,
  assembled, and checked for zero LongMemEval 12-token overlap. Its score-gated two-swap contract
  was **closed without execution on 2026-08-02** under the context-bundling abandonment criterion:
  the candidate ceiling was one to three answers on sixty questions, below the noise floor, while
  twelve of thirteen observed answer errors fell in multi-session and temporal-reasoning whose
  retrieval already succeeds. No baseline runner was built and no paid call was made. The corpus is
  retained unfrozen as a reusable screening instrument. See AD-053.
- **Matched local comparator runs are now the active work and the only unmet Phase 1 exit
  condition.** Until Mem0 and Supermemory are measured on this machine, dataset, and depth, no
  competitive statement about this store is supportable in either direction.

Do not describe the adapter smoke test as a competitive baseline.

## Fresh session-density corpus draft

Reproduce the independently reviewed 60-case corpus and its LongMemEval overlap check with:

```bash
uv run python scripts/build_session_density_corpus.py \
  --author-a evaluation/memorybench/session-density-author-a-v1.json \
  --author-b evaluation/memorybench/session-density-author-b-v1.json \
  --review-a-of-b evaluation/memorybench/session-density-author-a-review-of-b-v1.json \
  --review-b-of-a evaluation/memorybench/session-density-author-b-review-of-a-v1.json \
  --longmemeval-dataset /path/to/longmemeval_s_cleaned.json \
  --output evaluation/memorybench/session-density-development60-v1.json
```

The output status is `independently-reviewed`, not frozen. The adjacent v2 gates file is explicitly
`draft-blocked-not-frozen`; do not implement or execute the candidate until its remaining
prerequisites are satisfied.

## Prepare the external checkout

Clone and pin MemoryBench outside this repository:

```bash
git clone https://github.com/supermemoryai/memorybench.git
cd memorybench
git checkout 118209a746d97d0d85e5a7234267f0b6962857e9
```

Copy `evaluation/memorybench/provider.ts` from this repository to
`src/providers/llm-memory-store/index.ts` in the MemoryBench checkout. Then apply the frozen
registration patch:

```bash
git apply /absolute/path/to/agent-memory-store/evaluation/memorybench/register-provider.patch
git apply /absolute/path/to/agent-memory-store/evaluation/memorybench/provider-lifecycle.patch
```

The lifecycle patch adds an optional provider shutdown hook so the stdio bridge exits with a
successful run. The copied provider and benchmark patches intentionally remain visible in the
external checkout; preserve its dirty diff with the run evidence.

## Environment

```bash
export LLM_MEMORY_STORE_REPO=/absolute/path/to/agent-memory-store
export LLM_MEMORY_BENCH_DATA_DIR=/private/benchmark/work/stores
export LLM_MEMORY_BENCH_CACHE_DIR=/private/benchmark/work/fastembed-cache
export LLM_MEMORY_BENCH_OFFLINE=1
```

`LLM_MEMORY_BENCH_OFFLINE=1` requires the pinned FastEmbed model to exist in the local cache. Omit it
for the first model download. Use the explicit cache directory because FastEmbed's default macOS
temporary cache can be cleaned between runs. Benchmark data, model cache, and provider stores
belong in ignored working directories, never in Git.

Before running MemoryBench, verify its downloaded dataset:

```bash
uv run python scripts/verify_longmemeval_dataset.py \
  /path/to/memorybench/data/benchmarks/longmemeval/datasets/longmemeval_s_cleaned.json
```

Start with one question from each of the six categories. Freeze the answering/judge configuration
before expanding. `run-search-sample.ts` prepares a consecutive per-category sample without
MemoryBench's all-500 ingest command, and `longmemeval-stratified60-v1.json` freezes the completed
ten-per-category selection.

The public dataset's labeled answer-session retrieval diagnostic is reproducible without a hosted
judge:

```bash
uv run python scripts/analyze_longmemeval_retrieval.py \
  /path/to/longmemeval_s_cleaned.json \
  /path/to/run/checkpoint.json
```

This output is not MemoryBench's LLM-labeled relevance evaluation.

The session-diverse candidate is benchmark-explicit and default-off:

```bash
export LLM_MEMORY_BENCH_CONTEXT_POLICY=session-diverse-v1
```

It retrieves the unchanged top 50, caps each provenance session at two single-message results,
returns ten slots, and backfills in original rank order. Do not enable it for a baseline run or
describe the development result as sealed or shipped product evidence.

## Optional local Ollama evaluator smoke

The pinned MemoryBench revision assumes hosted provider endpoints. For a diagnostic loopback
OpenAI-compatible endpoint, apply:

```bash
git apply \
  /absolute/path/to/agent-memory-store/evaluation/memorybench/ollama-openai-base-url.patch
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
```

The 2026-07-24 smoke used `llama3.1:8b` for both answering and judging. That configuration validated
the mechanics but failed the evaluator-quality gate; do not use its 0/6 answer score as competitive
evidence or expand it to 500 questions.

## Evaluator history and current gate

Exact model `claude-opus-5`, resolved from the Claude CLI `opus` alias with Claude Code 2.1.219,
passed the six-category evaluator pilot at 5/6 for $1.024665. Do not rely on the mutable alias in
recorded evidence. Reproduce the budget-bounded pilot with
`scripts/run_memorybench_claude_pilot.py`; raw results belong under ignored `demo-artifacts`.

The planned Opus complementary expansion was superseded after the owner supplied Kimi API credit
and reserved Claude for architecture work. The prior Opus 60 remains diagnostic evidence and must
not be merged with Kimi scores.

The current exact `kimi-k3` runner is resumable, direct-API, and budget bounded. Its 20-question
development mechanics use three answer repeats and three judge votes, plus an empty-context
control. Its judge audit on Opus answers passed at 28/30 overall human agreement, 16/17
human-positive agreement, 12/13 human-negative agreement, zero positive-count drift, and 28/30
unanimous votes. That judge audit used Opus-generated answers. A separate blind audit of 20 actual
first-pass Kimi answers scored 17/20 and passed the frozen 14/20 answerer gate; all 20 candidates
were provenance-matched to raw `kimi-k3` output. No sealed-validation question has been opened.

For the paired session-diverse development audit, fill only `left_human_score`,
`right_human_score`, and optional note fields in
`demo-artifacts/memorybench/kimi-k3-session-diverse-paired-human-audit-v1.json`. Do not inspect the
separate key while scoring. Then apply the authoritative labels and rerun every frozen gate:

```bash
uv run python scripts/adjudicate_kimi_paired_human_audit.py \
  --packet demo-artifacts/memorybench/kimi-k3-session-diverse-paired-human-audit-v1.json \
  --key demo-artifacts/memorybench/kimi-k3-session-diverse-paired-human-audit-key-v1.json \
  --machine docs/architecture/benchmarks/2026-08-02-longmemeval-kimi-k3-session-diverse-paired-development.json \
  --contract evaluation/memorybench/kimi-paired-answer-development-gates-v1.json \
  --raw demo-artifacts/memorybench/kimi-k3-session-diverse-paired-development60-v1.json \
  --checkpoint demo-artifacts/memorybench/upstream/data/runs/llm-memory-store-longmemeval-stratified60-v1/checkpoint.json \
  --output docs/architecture/benchmarks/2026-08-02-longmemeval-kimi-k3-session-diverse-paired-human-audit.json
```

The adjudicator verifies packet/key/source provenance, duplicate consistency, judge-human
agreement, and every post-substitution automated gate. A non-passing result exits nonzero.
