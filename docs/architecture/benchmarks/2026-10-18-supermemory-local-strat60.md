# Supermemory Local vs the Store — Stratified Sixty, Free Local Models

Date: 2026-10-18
Status: **completed under protocols frozen before each run.** The first thirty used
`supermemory-local-comparison-v1.json` (commit 2c83423). The second thirty used its Kaggle extension
`supermemory-local-comparison-v1-extension-kaggle.json` (commit 3d1b7ec). Free throughout: no hosted
model and no paid API.
Scores: `demo-artifacts/supermemory-local-strat60-presence.json` (all sixty) and
`demo-artifacts/supermemory-local-strat30b-presence.json` (second thirty).
First thirty in detail: `2026-10-12-supermemory-local-strat30.md`.

## Configuration

- **Supermemory Local 0.0.8:** Ollama `qwen2.5:7b` extraction (digest `845dbda0…`, 16k context,
  temperature 0), local `bge-base` embeddings, telemetry off, and MemoryBench's unchanged provider
  (hybrid search, limit 30, threshold 0.3).
  - Questions 1–5 of each category: the M2 (Apple M2 Pro).
  - Questions 6–10 of each category: Kaggle's free notebooks (2 × Tesla T4). Each question ran
    alone on a fresh server, with the same pins checked at start-up.
- **The store:** the completed run `llm-memory-store-longmemeval-stratified60-v1`, vector recall, top
  ten raw messages.

## Metric

Answer-content presence in the retrieved context. This is a lexical floor on whether the answer is
available. It is not answer quality.

## Result — all sixty

| Arm | Present | Median context | KU | MS | SSA | SSP | SSU | TR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Store, top 10** | **35 / 60** | **8,769 chars** | **9** | 2 | **10** | 2 | **10** | 2 |
| Supermemory Local, top 10 | 15 / 60 | 16,974 chars | 2 | 1 | 7 | 0 | 4 | 1 |
| Supermemory Local, full default | 22 / 60 | 37,033 chars | 2 | 2 | 7 | 2 | 4 | **5** |

Each category has ten questions: KU knowledge-update, MS multi-session, SSA
single-session-assistant, SSP single-session-preference, SSU single-session-user, TR
temporal-reasoning.

Paired against the store (two-sided sign test on discordant questions):

| Comparison | Store only | Other only | p |
| --- | ---: | ---: | ---: |
| vs Supermemory top 10 (matched depth) | 20 | 0 | **1.9 × 10⁻⁶** |
| vs Supermemory full default | 17 | 4 | **0.0072** |

## Replication

The second thirty, run on different hardware, reproduce the first:

| Set | Store | Supermemory top 10 | Supermemory full | Matched-depth discordance |
| --- | ---: | ---: | ---: | ---: |
| First thirty (M2) | 18 | 8 | 11 | 10–0 |
| Second thirty (Kaggle T4) | 17 | 7 | 11 | 10–0 |

## Data quality and sensitivity

- **Second thirty:** 1,388 of 1,436 sessions completed extraction, and none went unaccounted.
  - Two questions ran out of Kaggle's 12-hour window. They were rerun to completion on the same
    frozen runner (notebook `sm-local-strat30b-c`) with every session processed.
  - Five questions are damaged under the frozen rule (more than 10% of sessions failed, or the
    search returned nothing): four empty searches, and one with 6 of 55 sessions failed.
- **First thirty:** five damaged questions, as recorded in the earlier document.
- **Sensitivity check (not part of the frozen protocol):** excluding all ten damaged questions
  leaves fifty. There the store finds 29 against Supermemory top 10's 14 (discordant 15–0,
  p = 0.0001), and against Supermemory full default's 21 (12–4, p = 0.077).
- Supermemory's extraction varies from run to run even at temperature 0. On the smoke question
  `08e075c7`, one run returned 16 memories and another 25. Each question is scored from exactly
  one run, and the machine is recorded for each.
- Single-session-preference gold answers are long rubric descriptions that lexical presence rarely
  matches. That column is uninformative.

## Reading

- **Matched depth:** the store's ten raw messages contain the answer far more often than
  Supermemory's ten extracted memories (35 vs 15). It never misses an answer that Supermemory
  finds, and it uses about half the context. The pattern held on two independent halves and two
  machines.
- **Full default:** at about four times the store's context, Supermemory still trails, 22 vs 35
  (p = 0.007). The gap is not significant once damaged questions are removed.
- **Temporal reasoning is the exception.** There Supermemory's full output finds the answer in 5
  of 10 against the store's 2. Its extracted memories carry document and event dates, which
  answers to "when" questions need. This matches the store's known weakness and points to the next
  product work: date-aware recall.
- **What this measures.** Supermemory was run under a free local 7B model. This says nothing about
  its hosted service or about answer quality.
