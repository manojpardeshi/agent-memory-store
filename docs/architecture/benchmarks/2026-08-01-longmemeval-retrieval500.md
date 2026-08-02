# LongMemEval-S 500-Question Retrieval Baseline

Date: 2026-08-01
Status: **retrieval-only baseline complete; matched comparator and full answer quality pending**

## Outcome

The released raw deterministic store completed local ingestion, indexing, and top-10 search for all
500 LongMemEval-S questions. The public dataset's labeled answer-session diagnostic measured 97.0%
Hit@10, 92.1% answer-session recall@10, and 0.910 MRR@10.

| Category | Hit@5 | Hit@10 | Answer-session recall@5 | Answer-session recall@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Knowledge update | 97.4% | 98.7% | 91.0% | 98.1% | 0.976 |
| Multi-session | 95.5% | 97.7% | 76.8% | 89.2% | 0.916 |
| Single-session assistant | 100% | 100% | 100% | 100% | 0.988 |
| Single-session preference | 90.0% | 93.3% | 90.0% | 93.3% | 0.804 |
| Single-session user | 91.4% | 95.7% | 91.4% | 95.7% | 0.859 |
| Temporal reasoning | 92.5% | 95.5% | 75.3% | 85.8% | 0.884 |
| **Overall** | **94.6%** | **97.0%** | **84.1%** | **92.1%** | **0.910** |

These metrics compare retrieved source-session IDs with LongMemEval's public labeled answer-session
IDs. They are deterministic diagnostics, not MemoryBench's separate LLM-labeled relevance metric
and not answer accuracy.

## Frozen configuration

- Provider: `agent-memory-store` Track A raw deterministic ingestion.
- Embedder: product-default `BAAI/bge-small-en-v1.5` through FastEmbed 0.8.0.
- Relevance: product-default identity-scoped relative semantic-gap policy; search request depth 10.
- Dataset: LongMemEval-S 500-question source, SHA-256
  `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`.
- MemoryBench revision: `118209a746d97d0d85e5a7234267f0b6962857e9`.
- First checkpoint: observed stratified 60, SHA-256
  `7955578d87193549f09c202cce8028d9c336716c00af072dd19770976066bbf3`.
- Complement checkpoint: frozen remaining 440, SHA-256
  `48ffc063c75bd143059e05c7da6cda77b1c2a661ed87510a998c3476dcba2d94`.
- Complement manifest: SHA-256
  `44f9b6486da950ea29614d83f059fa81cf224a5ca1704cc7029eaf14d538909a`.

Only aggregate 500-question evidence is committed. Per-question results remain in ignored local
artifacts so sealed validation and reserve cases are not made convenient tuning targets.

## Runtime and scale

| Metric | Result |
| --- | ---: |
| Questions | 500 |
| Ingested episodes | 246,299 |
| Returned results, mean / minimum / maximum | 9.978 / 4 / 10 |
| Search latency, mean / p50 / p95 / maximum | 132.6 / 147 / 173 / 250 ms |
| Hosted API cost | $0 |

The complement ran serially and offline after the pinned FastEmbed files were placed in an explicit
cache. Ingestion and indexing completed without failed questions.

## Protocol recovery

Search stopped after six complement questions because one source message contained Unicode line
separator U+2028. Python emitted that character literally inside a valid JSON string, while Node's
line reader treated it as a JSON-lines record boundary and discarded the three fragments. The
checkpoint remained intact.

The bridge now writes protocol JSON through a dedicated stdout descriptor, redirects later native
stdout diagnostics to stderr, and ASCII-escapes JSON strings. Decoding preserves the exact Unicode
content; storage, embeddings, scoring, and ranking did not change. A regression test injects U+2028
and proves that the response remains one JSON-lines record. The same run ID resumed from 440/440
ingested and 6/440 searched, then completed the remaining 434 searches.

## Interpretation

The full retrieval diagnostic confirms the provisional bottleneck. A relevant answer session is
usually present in the top 10, but multi-session and temporal questions have the weakest coverage:
their answer-session recall rises from 76.8% to 89.2% and from 75.3% to 85.8% when depth expands
from five to ten. The next paired development experiment remains provider-neutral session-diverse
context bundling. It should change context selection only, preserve the released store ranking,
and be selected on development questions before one sealed-validation comparison.

Machine-readable aggregate evidence is stored beside this file in
`2026-08-01-longmemeval-retrieval500.json`.
