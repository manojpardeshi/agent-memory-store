# Supermemory Local vs the Store — Stratified Thirty, Free Local Models

Date: 2026-10-12
Status: **completed under the protocol frozen before the run** (`evaluation/memorybench/supermemory-local-comparison-v1.json`, commit 2c83423). Free: no hosted model, no paid API.
Questions: `evaluation/memorybench/longmemeval-stratified30-v1.json` (first five per category of the stratified sixty).
Scores: `demo-artifacts/supermemory-local-strat30-presence.json`. Checkpoints: `demo-artifacts/memorybench/upstream/data/runs/supermemory-local-strat30-seq-*/`.

## Configuration

- **Supermemory Local 0.0.8** on the M2 (Apple M2 Pro, 16 GB). Extraction by Ollama `qwen2.5:7b`
  (16k context, temperature 0) through its OpenAI-compatible endpoint. Local
  `Xenova/bge-base-en-v1.5` embeddings. Telemetry disabled; incoming connections blocked by the
  macOS firewall. Run through MemoryBench's unchanged Supermemory provider (hybrid search, limit
  30, threshold 0.3).
- **The store:** the existing completed run `llm-memory-store-longmemeval-stratified60-v1`
  (vector recall, top ten raw messages), restricted to the same thirty questions.

## Metric

Answer-content presence. The gold answer counts as present when its normalized text appears in the
retrieved context: exact containment for answers of at most two content tokens, otherwise at least
80% of answer tokens. This is a lexical floor on whether the answer is available. It is not answer
quality and cannot credit a paraphrase.

## Result

| Arm | Answer present | Median context | KU | MS | SSA | SSP | SSU | TR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Store, top 10** | **18 / 30** | **8,593 chars** | 5 | 1 | 5 | 1 | 5 | 1 |
| Supermemory Local, top 10 | 8 / 30 | 19,982 chars | 2 | 0 | 3 | 0 | 2 | 1 |
| Supermemory Local, full default (≤ 30 results) | 11 / 30 | 45,474 chars | 2 | 1 | 3 | 1 | 2 | 2 |

Categories are five questions each: KU knowledge-update, MS multi-session, SSA
single-session-assistant, SSP single-session-preference, SSU single-session-user, TR
temporal-reasoning.

Paired against the store:

| Comparison | Store only | Other only | Two-sided sign test |
| --- | ---: | ---: | ---: |
| vs Supermemory top 10 (matched depth) | 10 | 0 | **p = 0.002** |
| vs Supermemory full default | 9 | 2 | p = 0.065 |

## Data quality and sensitivity

- 1,374 of 1,420 sessions (96.8%) completed Supermemory's extraction. 46 failed, and none went
  unaccounted. One question lost 19 of 47 sessions and another 7 of 44. For three questions,
  search returned no memories despite completed indexing.
- Excluding those five damaged questions (sensitivity check, not part of the frozen protocol), the
  remaining 25 give store 15 vs Supermemory top 10: 8 (discordant 7–0, p = 0.016), and store 15
  vs Supermemory full default: 11 (discordant 6–2, p = 0.29).
- Single-session-preference gold answers are 220–450-character rubric descriptions, which
  lexical presence rarely matches in any arm. Read that column as uninformative.

## Execution record (disclosed)

- Two bulk attempts, each queueing all 1,420 sessions at once, ended when Supermemory Local's Bun
  runtime segfaulted under memory pressure after about two hours, with no question fully indexed.
  The owner's 4 GB Kali VM on the M2 was stopped to free memory; a state save of it crashed QEMU,
  and its disk checked clean.
- The completed run ingested one question at a time, with a per-question watchdog and at most two
  attempts. The server crashed sixteen times across the run. Three launcher defects were found and
  fixed along the way: stop matched the wrapper rather than the real binary; restart did not wait
  for the data-directory lock; a failed start aborted the sequence. Four questions completed on a
  resumed run whose sessions the server had already processed.
- A parallel attempt on free GitHub Actions CPU runners produced no usable data. The 7B model was
  too slow on CPU for Supermemory's internal memory-agent timeouts, and nearly every session was
  marked failed. Per the frozen split (`supermemory-local-cloud-split-v1.json`), all those
  questions use the M2 result. No cloud result is included.
- Extraction ran at about 60–100 s per session on the M2's GPU.

## Disclosed asymmetries

- Supermemory is designed for a strong hosted extraction model. This run measures it under a free
  local 7B model, as the earlier Mem0 OSS comparison measured Mem0.
- The store keeps raw messages and needs no extraction model. Supermemory embeds with bge-base
  (768-d), the store with bge-small (384-d).
- The store run predates this comparison and is reused unchanged.

## Claim

On these thirty LongMemEval-S questions, under free local models only, the store's top ten
contained the gold answer text in 18 cases and Supermemory Local's top ten in 8. The store did so
with less than half the context. Every question one arm found and the other missed went to the
store. Against Supermemory's full default output, which uses five times the store's context, the
gap narrows to 18 vs 11 and is not significant. This says nothing about Supermemory's hosted
service, about answer quality, or about other configurations.
