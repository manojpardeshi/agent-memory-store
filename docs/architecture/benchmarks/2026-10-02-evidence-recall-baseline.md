# Evidence-Level Retrieval Baseline — Free Measurement

Date: 2026-10-02
Status: baseline established. **No model and no paid service involved.**
Tool: `scripts/analyze_evidence_recall.py`

## Why this exists now

On 2026-10-02 the owner stopped all spending on kimi-k3, hosted Mem0, and Supermemory. Answer
quality, which every candidate so far was judged on, needed a strong paid answerer and judge, and free
local models are not a substitute: `llama3.1:8b` produced 0 usable answers in 6 on these contexts.
From here, improvements are measured with free, deterministic signals, and **answer quality is no
longer measured**.

LongMemEval labels the exact answer-bearing turns with `has_answer: true` (10,960 labelled
messages). That allows a retrieval metric at the right granularity: did the specific answer-bearing
message reach the top-k context?

## Baseline, released store, 180 development questions, k = 10

174 questions have labelled evidence; 6 do not, consistent with abstention questions.

| Category | n | Evidence recall | All evidence present | Any evidence present |
| --- | ---: | ---: | ---: | ---: |
| single-session-assistant | 22 | 1.000 | 22 | 22 |
| single-session-user | 25 | 0.960 | 24 | 24 |
| knowledge-update | 26 | 0.846 | 20 | 24 |
| single-session-preference | 15 | 0.811 | 11 | 13 |
| temporal-reasoning | 43 | 0.705 | 26 | 34 |
| multi-session | 43 | 0.640 | 18 | 38 |
| **Total** | **174** | **0.793** | **121** | **155** |

Session-level Hit@10 on the same questions is about 97%. At the evidence level, 53 of 174 questions
are missing at least one answer-bearing message, concentrated in multi-session and temporal, the two
weakest answer categories. This is real retrieval headroom the old metric could not see.

## What it can and cannot say

The v1.2 context raised complete-evidence questions from 121 to 129 (multi-session 18 → 21, temporal
26 → 27), and answers moved by one. Complete evidence is necessary for a correct answer but not
sufficient. A gain on this metric is a retrieval improvement. It must never be reported as an answer
improvement.

## Use going forward

Primary free gate for retrieval candidates, alongside the internal synthetic suites, latency, and
footprint. The 120 design-blind questions are reported only in aggregate.
