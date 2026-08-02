# LongMemEval-S Opus 5 Evaluator Pilot

Date: 2026-07-24
Status: six-category evaluator gate passed; full 500-question run not authorized

## Configuration

The pilot reused the exact six search artifacts from
`llm-memory-store-longmemeval-smoke-v1`. It did not ingest, index, search, or change product
retrieval again. The runner reconstructed the pinned MemoryBench answer and judge prompts and
recorded prompt hashes rather than committing raw public-dataset contexts.

- Answerer and judge: exact `claude-opus-5`.
- Claude Code: 2.1.219, non-persistent print mode, low effort, tools disabled.
- Per-call ceiling: $1.00; total pilot ceiling: $5.00.
- Frozen selection: one consecutive question from each of six LongMemEval-S categories.
- Readiness threshold: at least five of six answers judged correct, with every judge response valid.
- Raw resumable result: ignored local artifact with SHA-256
  `a79cf1366def695f4eef1c8bbfa5b6674ecedfa103a6a0a5c512cf830df5a2fa`.

Although every final response used Opus 5, Claude Code reported $0.062795 of auxiliary
`claude-haiku-4-5-20251001` usage across the 12 CLI calls. The runner requested disabled prompt
suggestions and no tools; OAuth-backed Claude Code still used the auxiliary model internally. This
is an evaluation-infrastructure asymmetry and must remain disclosed.

## Result

| Metric | Result |
| --- | ---: |
| Correct | 5/6 |
| Accuracy | 83.3% |
| Gate | Pass |
| Answer cost | $0.980525 |
| Judge cost | $0.044140 |
| Total cost | $1.024665 |
| Answer mean / max | 4.709 / 6.719 s |
| Judge mean / max | 2.841 / 3.091 s |

Opus answered preference, single-session user, temporal, knowledge-update, and single-session
assistant questions correctly. On the multi-session wedding question, it correctly answered
“three” but listed the sister's wedding instead of Rachel and Mike's. The judge rejected the
partially wrong response. The failure therefore reflects context/reasoning quality rather than the
non-responsive evaluator behavior seen with local Llama.

The pilot passes the evaluator-readiness threshold. It does not establish product accuracy: it has
one question per category, uses the same model for answering and judging, and reuses only one
provider's retrieval artifacts.

## Full-run budget decision

Linear extrapolation from this small sample estimates about $85.39 for 500 answer-plus-judge pairs.
A 20% uncertainty margin is $102.47, above the claimed $100 usage credit. Context sizes vary, so the
point estimate is not a safe spending cap. Serial ingestion is separately projected at roughly 3.65
hours, followed by about 63 minutes of evaluator calls.

Do not start the full 500-question Opus run without a new explicit budget decision. The safer next
measurement is a stratified 60-question run (10 per category), expected near $10.25 from this pilot,
followed by a revised full-run estimate. No product retrieval tuning is authorized by this pilot.

Machine-readable aggregate evidence is stored beside this file in
`2026-07-24-longmemeval-opus5-pilot.json`.
