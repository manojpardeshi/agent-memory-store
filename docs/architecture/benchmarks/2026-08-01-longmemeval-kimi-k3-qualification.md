# LongMemEval-S Kimi K3 Evaluator Qualification

Date: 2026-08-01
Status: **answerer and judge qualified for the frozen development protocol**

## Outcome

Exact API model `kimi-k3` passed the automated mechanics, the independent human answer-quality
gate, and every pre-registered judge-concordance gate on frozen development-only evidence. The two
human audits have different scopes: Kimi answered the 20-item answer-quality packet and scored
17/20, while Kimi judged 30 `claude-opus-5` answers and agreed with the human on 28/30. Together
they qualify Kimi as both answerer and judge for the frozen protocol. This does not constitute a
sealed benchmark result; no sealed-validation or reserve question has been opened.

| Gate | Result | Threshold |
| --- | ---: | ---: |
| Retrieved-context majority accuracy | 15/20 (75%) | at least 70% |
| Empty-context majority accuracy | 1/20 (5%) | at most 10% |
| Memory-attributable accuracy uplift | 70 percentage points | diagnostic |
| Judge-vote unanimity | 58/60 (96.7%) | at least 95% |
| Answer-repeat pairwise agreement | 58/60 (96.7%) | at least 90% |
| Questions stable across all three answers | 19/20 (95%) | diagnostic |
| Judge audit on Opus answers | 28/30 agreement (93.3%) | at least 27/30 |
| Human audit of Kimi answers | 17/20 (85%) | at least 14/20 (70%) |

The three retrieved-context answer passes scored 75%, 80%, and 75%. Majority voting produced
15/20. The one empty-context hit was a multi-session question; its three judges were unanimous.
This control prevents attributing every correct answer to memory retrieval.

## Frozen protocol

- Selection: 20 development questions, deterministically selected from the already observed
  stratified 60; no validation or reserve question was opened.
- Model: exact `kimi-k3` through `https://api.moonshot.ai/v1/chat/completions`.
- Answerer: high reasoning, 4,096 maximum completion tokens, three repeats.
- Judge: low reasoning, 1,024 maximum completion tokens, strict JSON Schema, three votes per answer.
- Context control: one answer and three judge votes per question with an empty retrieved-context
  array and otherwise identical question, date, prompts, and judge rubric.
- Credentials came from macOS Keychain and were never written to the repository or evidence.

The selection manifest has SHA-256
`e8d024d1cc5f9bb11ede9f722f018073147c200d0e036dc780775dcf5002ed76`.
The frozen source checkpoint has SHA-256
`7955578d87193549f09c202cce8028d9c336716c00af072dd19770976066bbf3`.
Ignored raw retrieved evidence has SHA-256
`833f1cc1df854526c50730fcf55a321eebb7ce752b83c419244a4d9433fb3d47`;
ignored empty-context evidence has SHA-256
`dead47d690d5b4dea5d297d9fba9f6b7049bad325153e6666fa15679ec264027`.

## Accuracy by category

| Category | Retrieved | Empty context |
| --- | ---: | ---: |
| Knowledge update | 2/3 | 0/3 |
| Multi-session | 2/3 | 1/3 |
| Single-session assistant | 3/3 | 0/3 |
| Single-session preference | 3/4 | 0/4 |
| Single-session user | 4/4 | 0/4 |
| Temporal reasoning | 1/3 | 0/3 |
| **Overall** | **15/20** | **1/20** |

This small sample qualifies evaluator behavior; it is not a product score or category estimate.

## Cost and operation

| Stage | Calls | Cost |
| --- | ---: | ---: |
| Retrieved-context answers | 60 | $0.832327 |
| Retrieved-context judges | 180 | $0.457940 |
| Empty-context answers | 20 | $0.032835 |
| Empty-context judges | 60 | $0.136624 |
| **Total** | **320** | **$1.459725** |

One empty-context judge call received HTTP 429 after its preceding checkpoint. The resumable runner
later continued from the exact missing vote; there was no duplicate recorded result, invalid
response, secret disclosure, or budget violation.

## Independent human judge audit

A deterministic blind packet contained `claude-opus-5` answers: all 13 frozen Claude-judge misses
from the prior 60 plus 17 hash-selected Claude-judge passes. It hid question IDs and all model
scores. The human independently scored all 30 before the key or any Kimi audit judgment was opened.

Claude Opus 5 then froze five integer gates before Kimi judged the packet. Kimi used three votes
per item and passed all five:

| Gate | Result | Required |
| --- | ---: | ---: |
| Overall Kimi–human agreement | 28/30 | at least 27/30 |
| Agreement on human-positive items | 16/17 | at least 15/17 |
| Agreement on human-negative items | 12/13 | at least 11/13 |
| Absolute positive-count drift | 0 | at most 3 |
| Unanimous three-vote items | 28/30 | at least 27/30 |

Kimi and the frozen Claude judge agreed on 30/30. Each agreed with the human on 28/30. This
supports Kimi judge consistency on Opus answers. It says nothing about how many questions Kimi can
answer correctly. The Kimi audit cost $0.245987; the threshold consultation cost $0.046000 and
disclosed auxiliary Haiku usage. Total Kimi mechanics and judge-audit spend was $1.705712.

## Independent human answer audit

The owner independently scored a separate 20-item packet containing actual Kimi answers. The
packet used answer repeat zero from the frozen qualification run, exactly one answer per unique
development question, and no validation or reserve questions. Reproducible provenance validation
matched all 20 packet answers exactly to raw model `kimi-k3` output.

| Category | Human-correct Kimi answers |
| --- | ---: |
| Knowledge update | 3/3 |
| Multi-session | 3/3 |
| Single-session assistant | 3/3 |
| Single-session preference | 3/4 |
| Single-session user | 4/4 |
| Temporal reasoning | 1/3 |
| **Overall** | **17/20 (85%)** |

The misses were K03, K12, and K13. Two were temporal-reasoning questions, so the small audit
supports protocol qualification but also reinforces temporal reasoning as a development risk. The
17/20 result passes the frozen minimum of 14/20. Human scoring reused existing answers and added
no API cost.

Machine-readable aggregate and answer-audit evidence is stored beside this file in
`2026-08-01-longmemeval-kimi-k3-qualification.json` and
`2026-08-01-longmemeval-kimi-k3-answer-human-audit.json`.
