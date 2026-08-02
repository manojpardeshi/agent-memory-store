# LongMemEval-S Six-Category Adapter Smoke

Date: 2026-07-24
Status: adapter and retrieval path passed; end-answer evaluator failed; not a competitive baseline

## Purpose and frozen inputs

This diagnostic run exercised raw deterministic ingestion, exact per-question isolation, indexing,
search, local answer generation, local judging, checkpointing, and report generation with one
consecutive question from each LongMemEval-S category. It did not measure a population result and
must not be compared with published managed-platform scores.

- Agent Memory Store commit: `923cf75f5f5b8886200990aeeebd25a8212e7c23`, dirty with the
  uncommitted benchmark adapter and architecture changes.
- MemoryBench commit: `118209a746d97d0d85e5a7234267f0b6962857e9`, dirty only with the copied
  provider, provider registration, local evaluator base-URL support, and benchmark lifecycle work.
- Dataset: 277,383,467-byte LongMemEval-S file, 500 questions.
- Dataset SHA-256:
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- Runtime: Bun 1.3.14, macOS 15.6.1 (24G90), Apple M1, 8 GiB RAM, arm64.
- Store: Agent Memory Store raw-deterministic-v1, FastEmbed 0.8.0,
  `BAAI/bge-small-en-v1.5`, product-default `relative:0.20` relevance policy.
- Answerer and judge: local Ollama 0.32.1, `llama3.1:8b`, 8.0B Q4_K_M, digest
  `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`.
- Evaluator endpoint: loopback OpenAI-compatible API; no paid or hosted model API.
- Search depth and concurrency: 10 results, concurrency 1.
- Run ID: `llm-memory-store-longmemeval-smoke-v1`.

The dataset verifier passed immediately before evidence inspection with the frozen byte size,
digest, total question count, and all six category counts.

## Selection

| Category | Question ID |
| --- | --- |
| Single-session preference | `d24813b1` |
| Single-session user fact | `15745da0` |
| Multi-session reasoning | `gpt4_2f8be40d` |
| Temporal reasoning | `gpt4_483dd43c` |
| Knowledge update | `c7dc5443` |
| Single-session assistant fact | `89527b6b` |

The six questions contained 2,910 source episodes in total.

## Results

| Metric | Result |
| --- | ---: |
| Answer accuracy | 0/6 (0%) |
| Hit@10 | 1.000 |
| Precision@10 | 0.167 |
| Recall@10 | 1.000 |
| Retrieval F1@10 | 0.279 |
| MRR | 0.700 |
| NDCG | 0.663 |
| Average context tokens | 9,477 |
| Search mean / median / p95 | 26 / 26 / 37 ms |
| Ingest mean / p95 per question | 26,312 / 27,098 ms |
| Answer mean / p95 | 12,428 / 14,581 ms |
| Judge mean / p95 | 12,348 / 15,127 ms |
| Total mean / p95 | 51,115 / 53,651 ms |
| SQLite main-file bytes | 17,915,904 |
| Total provider-file logical bytes | 18,112,512 |

Every category had Hit@10 and Recall@10 of 1.0. Per-question reciprocal ranks were 1.0 for four
questions and 0.1 for the single-session-user and knowledge-update questions. This is encouraging
adapter evidence only: one observation per category cannot establish retrieval quality.

## Failure analysis and decision

The end-answer stage is not fit for the full baseline. Despite labeled support appearing in every
top-10 result set, the local 8B answerer produced six off-topic or non-responsive answers. It often
summarized raw memory JSON or discussed timestamps instead of answering the question. The local
judge consistently rejected those answers. This is not evidence that the store had zero useful
recall; it is evidence that this small local answerer plus 7,000–12,000 tokens of raw retrieved
context is not a trustworthy quality evaluator.

No ingestion, indexing, search, answer API, judge API, or dataset operation failed or retried.
MemoryBench saved all checkpoint, per-question, and report artifacts. After printing “Run
complete,” its process remained open because the pinned Provider interface had no shutdown hook;
the finished runner received one manual interrupt after files were flushed. A separate optional
provider lifecycle patch and adapter `close()` method were added after this measurement. A
report-only exit check then completed normally with status zero in 2.1 seconds.

Do not launch the 500-question answer-quality run with this answerer/judge configuration. First
freeze a trustworthy answering and judging pair and require a six-category evaluator pilot in which
the model demonstrably uses retrieved supporting context. Retrieval-only full-corpus measurement
may proceed separately if it is clearly labeled and the same search-depth change is applied to
every comparator. Product retrieval remains unchanged until that gate is resolved.

The machine-readable aggregate evidence is stored beside this document in
`2026-07-24-longmemeval-smoke.json`. Raw benchmark questions, retrieved contexts, databases, and
MemoryBench checkpoint files remain in ignored local working directories.
