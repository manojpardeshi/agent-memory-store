# Hybrid Recall in the Product — Measurement

Date: 2026-10-02
Status: **shipped opt-in (`retrieval="hybrid"`); vector stays the default.** Free, local measurement only.
Code: `MemoryStore.recall(..., retrieval="hybrid")`, `database.ensure_keyword_index`.
Harness: `scripts/evaluate_hybrid_recall.py`; synthetic gates through `llm-memory evaluate-retrieval --retrieval`.
Prototype and frozen choice: `2026-10-02-hybrid-retrieval-prototype.md`, `evaluation/memorybench/hybrid-rrf-v1-frozen.json`.

## What shipped

- An FTS5 keyword index (`memory_keywords`, porter stemming) over `memories.content`. It is an
  external-content index kept in sync by triggers, so every write path stays consistent, including
  correction, forget, expiry purge, import, and migration. It is additive and needs no
  `SCHEMA_VERSION` change. A store from an earlier version is backfilled the first time it is opened
  writable. A read-only open of an unindexed store keeps vector recall and refuses hybrid with a
  clear error.
- FTS5 `secure-delete` is mandatory. Forgetting a memory physically removes its terms, which a test
  verifies against both the term vocabulary and the raw database bytes. On SQLite older than 3.44
  the index is not created and hybrid is unavailable, rather than weakening deletion.
- Hybrid recall fuses the vector ranking and a BM25 ranking by reciprocal rank fusion with the
  frozen parameters: k = 60, equal weights, depth max(50, 5 × limit). Scope isolation, the
  active/expired rules, and the relevance filter are unchanged. The filter keeps its vector-mode
  anchor, the top vector-ranked semantic score. Keyword-only results carry their true vector
  distance. Results gain a `fusion_score`, and vector-mode output is byte-for-byte unchanged.
- Query terms are always double-quoted, so query text cannot inject FTS5 syntax.

## LongMemEval-S evidence recall (questions with every answer-bearing message in the top ten)

| Set | Vector | Hybrid, benchmark header stripped | Hybrid, header indexed |
| --- | ---: | ---: | ---: |
| Tuning, stratified sixty (57 scored) | 41 | **47** | 44 |
| Held-out 120, aggregate only (117 scored) | 80 | **91** | 89 |

The benchmark adapter writes a `[longmemeval-source]` JSON header (dates, month names, role,
session id) into every stored message. Real users store only the message, and the header's shared
words are keyword noise. The diagnostic therefore strips it in each scratch copy; stored embeddings
are untouched, so the vector column is identical in both conditions. With the header stripped, the
shipped code reproduces the prototype exactly on both sets. The certified default relevance filter
changed no count in any arm.

## Internal synthetic gates (certified default filter)

| Suite | Mode | Recall@k | MRR | Distractor leak | Scope violations | Gate |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| retrieval_v1 | vector | 0.980 | 0.980 | 0.060 | 0 | pass |
| retrieval_v1 | hybrid | 0.980 | 0.980 | 0.060 | 0 | pass |
| retrieval_v2 | vector | 1.000 | 0.894 | 0.100 | 0 | pass |
| retrieval_v2 | hybrid | 0.967 | **0.834** | 0.083 | 0 | **fail (MRR < 0.85)** |

retrieval_v2 is deliberately paraphrastic: its queries avoid the answer's words ("old captain's
logs" for "ship logbooks", "large sea creature display" for "whale skeleton exhibit"). Keyword
matching there scores incidental shared words such as "museum" or "vessel" and demotes the answer.
Eleven queries got worse and five better.

## Cost

| Measure | Value |
| --- | --- |
| Recall latency, p50 (including query embedding) | 5.4 → 6.5 ms |
| Recall latency, p95 | 8.8 → 10.6 ms (held-out, stripped) |
| Database growth from the index | about 8–10% |
| First-open index build, ~500-message store | about 20 ms |

## Decision

Hybrid helps when the query repeats exact words from the evidence, which is typical of
conversational recall: +11 complete-evidence questions held out, with no category losing. It hurts
paraphrase-heavy queries, failing one internal gate. A default must not fail a standing gate, so
vector stays the default and hybrid is an explicit option in the library, CLI (`--retrieval
hybrid`), and MCP tool (`retrieval="hybrid"`). Making it default needs a change that passes
retrieval_v2 without being tuned on it, for example evidence from a new, independently authored
paraphrase suite. Answer quality is not measured and no answer-quality gain is claimed.
