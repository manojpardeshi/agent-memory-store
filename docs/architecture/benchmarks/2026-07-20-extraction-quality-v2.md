# Extraction Quality v2 Independent Matrix

Date: 2026-07-20
Status: all live candidates failed; no extractor promotion

## Corpus and controls

The new `evaluation/extraction_v2.json` corpus was frozen at SHA-256
`4ac553601c2e9c1dd7a8617d547fafb2fc054d0f0c9defaef137ed594cc692a8`
before any model run. Its live track has 50 cases: 10 expected facts, preferences, events, and
summaries plus 10 negatives. Eight blind seed cases were authored by Claude and 42 independently by
Codex. No extraction-v1 source or anchor was copied. The 12-case deterministic offline track passed
with perfect metrics and zero write/source-mutation violations.

All live runs used the same corpus, evaluator, strict thresholds, loopback endpoint, and
`extraction-v2` prompt except the explicitly labelled experimental Llama two-pass run. Model tags
are bound to content digests in the machine reports.

## Results

| Candidate | Precision | Recall | F1 | Summary coverage | Forbidden | Invalid | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Llama 3.1 8B single pass | 0.765 | 0.325 | 0.456 | 0.25 | 0 | 0 | 70.5s |
| Llama 3.1 8B two pass | 0.255 | 0.300 | 0.276 | 0.60 | 1 | 1 | 206.6s |
| Qwen 2.5 7B single pass | 0.450 | 0.225 | 0.300 | 0.25 | 0 | 0 | 104.3s |
| Qwen3 4B before thinking compatibility | 1.000* | 0.000 | 0.000 | 0.00 | 0 | 50 | 224.0s |
| Qwen3 4B compatible single pass | 0.476 | 0.250 | 0.328 | 0.15 | 1 | 25 | 167.8s |

`*` The pre-fix precision value is the evaluator's empty-proposal convention and is not a useful
quality result. Every case was invalid because the adapter rejected Ollama's documented top-level
`thinking` response field.

Llama single-pass was the only candidate to meet precision, kind, provenance, forbidden, and invalid
gates, but it failed recall and summary coverage. Its exact per-kind recall was fact 0.20,
preference 0.00, event 1.00, summary 0.10.

The two-pass hypothesis is rejected. It improved summary coverage by 0.35, but regressed precision
by 0.509, recall by 0.025, and kind accuracy to 0.571, while introducing a forbidden retracted claim
and an invalid corrected case. Its implementation and CLI option were removed before publication;
only the evidence is retained.

Qwen 2.5 improved fact recall to 0.70 but classified no exact events or preferences and was worse
overall. Qwen3 initially exposed an adapter compatibility defect. Official Ollama documentation
defines `think` on generate requests and a separate `thinking` response field. The adapter now sends
`think: false`, accepts an optional bounded string field, ignores it, and continues to use only the
structured `response`. After that fix, Qwen3 still invented source IDs in 25 cases and extracted one
quoted malicious claim, so it is not selected.

## Decision

No candidate passes the preregistered 0.75 precision, 0.65 recall, 0.85 summary-coverage, and hard
safety gates. Automatic acceptance remains prohibited. Llama single-pass remains the configured
review-only default because it is the least-bad safe measured option, not because it is certified.
Further tuning on extraction-v2 is prohibited.

The next product slice should improve manual proposal-review ergonomics and explicit conflict/
duplicate handling, where quality can be improved deterministically while local generative model
capability remains the limiting factor. Another model-quality cycle requires a newly approved corpus
and a materially stronger general-purpose local model.

Machine-readable reports:

- `2026-07-20-extraction-quality-v2-single-pass-llama3.1-8b.json`
- `2026-07-20-extraction-quality-v2-two-pass-llama3.1-8b.json`
- `2026-07-20-extraction-quality-v2-single-pass-qwen2.5-7b.json`
- `2026-07-20-extraction-quality-v2-single-pass-qwen3-4b.json`
- `2026-07-20-extraction-quality-v2-single-pass-qwen3-4b-compatible.json`

Protocol references:

- <https://docs.ollama.com/api/generate>
- <https://docs.ollama.com/capabilities/thinking>
