# Independent Retrieval Quality Matrix

Date: 2026-07-19
Status: passed for a model-scoped default relevance filter; engineering evidence, not statistical proof

## Pre-registered decision

The existing `relative:0.20` filter could become the default only if both frozen corpora passed with both certified model families, every filtered cell met the written absolute gate, scope violations remained zero, and Recall@5/MRR regressed by no more than 0.02 from its paired unfiltered cell. No threshold, query, expected memory, distractor, or control was changed after an embedding result was observed.

## Independent corpus

- Dataset: `evaluation/retrieval_v2.json`
- Dataset SHA-256: `67fd5c4b2779a2dab42dca545cbd8a7a8a0a9a604d83cda0c8b54d60134956bf`
- 60 synthetic memories and 60 queries; exactly 12 each of turn, fact, preference, summary, and event.
- Two exact private scopes with 20 eligible items each and one explicit shared pool. Shared queries have 40 eligible items.
- Each query has one expected memory, one accessible non-answer, and one exact-scope-inaccessible control selected before evaluation.
- Content domains are a fictional maritime museum, alpine observatory, and civic robotics club. No personal memories or user-derived text are present.

Fresh stateless Claude sessions authored the memory/query pairs without access to previous fixture contents or evaluation results. Initial 20-item prompts returned blank and produced no data; successful output was collected in ten-item batches. The deterministic build script preserves the authored content, normalizes schema/key variations, and assigns distractors by a fixed +7 rotation before any embedding run. Codex validated schema and scope controls but did not edit the corpus in response to model behavior.

This is independent authorship for a product acceptance gate, not a representative user sample. One authoring model still creates one linguistic style; 12 queries per kind are too few for per-kind statistical claims; and two small English bi-encoders do not represent embedding models generally.

## Certified matrix

Both models are FastEmbed passage/query adapters run from local cache:

- `BAAI/bge-small-en-v1.5`, behavior fingerprint `36d7909e...d5e27c87`
- `sentence-transformers/all-MiniLM-L6-v2`, behavior fingerprint `d448bfe0...8958bcde`

| Corpus | Model | Mode | Recall@5 | MRR | Distractor leakage | Scope violations | Gate |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| v1 | BGE small v1.5 | unfiltered | 0.980 | 0.980 | 0.240 | 0 | Fail |
| v1 | BGE small v1.5 | relative 0.20 | 0.980 | 0.980 | 0.060 | 0 | Pass |
| v2 | BGE small v1.5 | unfiltered | 1.000 | 0.894 | 0.183 | 0 | Fail |
| v2 | BGE small v1.5 | relative 0.20 | 1.000 | 0.894 | 0.100 | 0 | Pass |
| v1 | MiniLM L6 v2 | unfiltered | 0.980 | 0.960 | 0.400 | 0 | Fail |
| v1 | MiniLM L6 v2 | relative 0.20 | 0.980 | 0.960 | 0.060 | 0 | Pass |
| v2 | MiniLM L6 v2 | unfiltered | 0.983 | 0.947 | 0.167 | 0 | Fail |
| v2 | MiniLM L6 v2 | relative 0.20 | 0.983 | 0.947 | 0.050 | 0 | Pass |

All four filtered cells passed their corpus thresholds. Filtering removed 5, 9, 7, and 17 designated distractor hits respectively while changing neither Recall@5 nor MRR in any paired cell. Exact scope isolation remained invariant.

The full query-level reports are preserved beside this document. Runtime values are informational because model warmup/cache state differs by cell; all remained far below the 60-second product limit.

## Decision and limits

`relative:0.20` becomes the default only for stores bound to either certified model identity. It may return zero to the requested limit instead of filling top K with weak candidates. Python callers can explicitly pass `relevance_filter=None`; CLI callers use `--no-relevance-filter`; MCP callers use `relevance_filter="off"`. Every response makes the effective filter observable.

Unrecognized embedding models remain unfiltered by default. Adding or changing a model family requires this paired corpus/filter evidence again. Revert a certified default if a frozen or newly approved corpus shows more than 0.02 absolute Recall@5/MRR regression, leakage above its written ceiling, or any scope violation. The product collects no remote telemetry; re-evaluation reports and explicit user evidence are the feedback mechanisms.

## Claude review

Claude found no blocker for the pre-0.1 private product, given 60–85% relative leakage reductions in three cells, a 45% reduction in the fourth, flat recall/MRR, and zero scope violations. It required an explicit opt-out, documentation that filtered recall can be empty, model-specific certification, a re-certification trigger, and a rollback rule. Those constraints are adopted. Claude's suggestion of staged production telemetry is not applicable to a private local-only library with no analytics service.
