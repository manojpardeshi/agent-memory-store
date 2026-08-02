# LongMemEval-S Opus 5 Stratified Measurement

Date: 2026-07-30
Status: 60-question diagnostic complete; full 500-question baseline not yet authorized

## Outcome

The released raw deterministic retrieval path answered 47 of 60 questions correctly (78.3%).
Performance was strong on single-session and update questions, while multi-session aggregation and
temporal reasoning were the dominant gaps.

| Category | Correct | Accuracy |
| --- | ---: | ---: |
| Knowledge update | 10/10 | 100% |
| Multi-session | 3/10 | 30% |
| Single-session assistant | 10/10 | 100% |
| Single-session preference | 9/10 | 90% |
| Single-session user | 10/10 | 100% |
| Temporal reasoning | 5/10 | 50% |
| **Overall** | **47/60** | **78.3%** |

This is a stratified diagnostic, not the pre-registered 500-question baseline and not a matched
competitor comparison. No accuracy gate was registered for this expanded sample.

## Frozen configuration

- Repository base commit: `923cf75f5f5b8886200990aeeebd25a8212e7c23`; working tree dirty
  with the benchmark implementation and evidence.
- Provider: `agent-memory-store` Track A raw deterministic ingestion, product-default
  `BAAI/bge-small-en-v1.5` FastEmbed identity and relative semantic-gap policy.
- MemoryBench: `118209a746d97d0d85e5a7234267f0b6962857e9`.
- LongMemEval-S: 500-question source with SHA-256
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Selection: ten consecutive questions from each framework-loaded category; manifest SHA-256
  `38391ce30303a228090dadda178fb02ebb46c7707960b685ac55b8324be458cf`.
- Search request depth: 10; the product policy returned a mean 9.9 results and a minimum of 4.
- Answerer and judge: exact `claude-opus-5`, same model for both roles.
- Claude Code: 2.1.220, non-persistent print mode, low effort, tools disabled.
- Hardware: Apple M1, 8 GiB RAM, arm64; macOS 15.6.1.

The raw resumable evaluator result remains ignored and has SHA-256
`322d2f3f0f0497d5bd6a6255ff6e7c2013a8fd3d85df408ac77a50d1e2597d6d`.
The source MemoryBench checkpoint has SHA-256
`7955578d87193549f09c202cce8028d9c336716c00af072dd19770976066bbf3`.

## Retrieval diagnostic

The pinned MemoryBench relevance evaluator would make a third hosted-model call for every question.
That call was outside the approved two-call cost scope and was not run. Instead, the reproducible
`scripts/analyze_longmemeval_retrieval.py` diagnostic compares result session IDs with the public
dataset's labeled answer-session IDs. These numbers are session-label diagnostics, not
MemoryBench's LLM-labeled retrieval metrics.

| Category | Hit@10 | Answer-session recall@5 | Answer-session recall@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| Knowledge update | 100% | 100% | 100% | 1.000 |
| Multi-session | 90% | 59.0% | 80.5% | 0.900 |
| Single-session assistant | 100% | 100% | 100% | 1.000 |
| Single-session preference | 100% | 100% | 100% | 0.950 |
| Single-session user | 100% | 100% | 100% | 1.000 |
| Temporal reasoning | 80% | 70.0% | 75.0% | 0.636 |
| **Overall** | **95%** | **88.2%** | **92.6%** | **0.914** |

Eleven of the thirteen incorrect answers still had at least one labeled answer session in the top
10. Six incorrect answers had incomplete answer-session recall@10. One correct answer had no
labeled answer session in the top 10, showing that the dataset session labels and answer accuracy
are related but not equivalent.

The evidence therefore does not support a simple lexical-recall conclusion. The sharper signal is
insufficient coverage across multiple answer sessions, repeated turns consuming the context
budget, and weak temporal interpretation. The safest first paired experiment is a provider-neutral
session-diverse context bundle, measured without changing storage or embeddings; a temporal-aware
retrieval experiment should follow separately if the residual temporal gap remains.

## Cost, tokens, latency, and storage

| Metric | Result |
| --- | ---: |
| Answer cost | $8.643139 |
| Judge cost | $0.464876 |
| Total cost | $9.108015 |
| Approved ceiling | $12.50 |
| Opus 5 reported cost | $8.452215 |
| Auxiliary Haiku 4.5 reported cost | $0.655800 |
| Opus answer input tokens, total / mean | 784,836 / 13,080.6 |
| Opus answer output tokens | 7,398 |
| Opus judge input / output tokens | 37,111 / 3,153 |
| Answer latency mean / p95 / max | 4.112 / 7.670 / 10.210 s |
| Judge latency mean / p95 / max | 3.150 / 3.898 / 6.353 s |
| Ingested episodes | 29,378 |
| Ingest latency total / p50 / p95 | 1,857.115 / 30.290 / 38.447 s |
| Index-finalization latency total | 0.613 s |
| Search latency mean / p50 / p95 / max | 29.45 / 27 / 40 / 65 ms |
| SQLite main files | 60 files, 180,752,384 bytes |
| All provider database files | 180 files, 182,718,464 bytes |

Claude Code routed internal work to `claude-haiku-4-5-20251001` even though every final answer and
judgment used Opus 5 and tools and prompt suggestions were disabled. The Opus and Haiku token
counters are different internal routes and must not be added as though they were one prompt.

## Deviations and recovery

- The first preparation attempt stopped before writes when FastEmbed's default macOS temporary
  cache had been cleaned. The model was downloaded once into an explicit ignored cache and the run
  resumed offline.
- Preparation stopped safely after 22 questions when one source session contained four empty
  message bodies. The bridge now preserves their positions with `[empty source message]` plus
  `source_content_empty=true`; non-empty message behavior did not change. The same run then resumed.
- Answering and judging completed without invalid responses, per-call budget violations, retries,
  or question failures.
- No product ranking, embedding, or storage behavior was tuned after viewing results.

## Revised full-run decision

The observed mean answer-plus-judge cost was $0.15180025 per question. A fresh 500-question pass
projects to $75.90, or $91.08 with a 20% margin. Known evaluator experiments have already spent
$10.170657 of the claimed $100 credit, so rerunning all 500 with margin is not safely funded.

The completed 60 can be reused without selecting a best run. Running only the frozen complementary
440 questions projects to $66.79, or $80.15 with a 20% margin, which fits the approximately $89.83
remaining after known spend. That complementary run requires a separate explicit authorization
and should preserve this exact provider, prompts, models, CLI settings, and evaluator protocol.

Machine-readable aggregate evidence is stored beside this file in
`2026-07-30-longmemeval-opus5-stratified60.json`.
