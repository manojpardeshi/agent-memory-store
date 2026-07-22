# Extraction Quality v1

Date: 2026-07-20
Status: offline gate passed; live `llama3.1:8b` target failed

## Scope

The frozen `evaluation/extraction_v1.json` corpus has SHA-256
`4e9cd4bb85b3dc29eab259571ea83a3be55fc7207fb5ef44e9b84018c1213167`. It
contains 12 explicit offline cases and 50 natural-language live cases, with 10 expected facts,
preferences, events, and summaries plus 10 negative cases. All content is synthetic. The same
corpus and preregistered thresholds were used for every live run.

The model was local Ollama `llama3.1:8b`, pinned to content digest
`46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`, at a
validated loopback endpoint. Proposal generation had no tool or acceptance channel.

## Offline result

The deterministic track passed all 12 cases: 8/8 exact proposals, 1.00 precision/recall/kind/
provenance/summary coverage, zero forbidden/duplicate/invalid proposals, and zero write or source
mutation violations.

## Live comparison

| Metric | v1 baseline | v2 conservative | v3 rejected |
| --- | ---: | ---: | ---: |
| Exact precision | 0.537 | 0.500 | 0.367 |
| Exact recall | 0.725 | 0.250 | 0.275 |
| Exact F1 | 0.617 | 0.333 | 0.314 |
| Kind accuracy | 0.967 | 1.000 | 1.000 |
| Provenance accuracy | 1.000 | 1.000 | 1.000 |
| Summary fact-unit coverage | 0.400 | 0.300 | 0.450 |
| Forbidden proposals | 4 | 0 | 0 |
| Invalid cases | 4 | 0 | 0 |
| Durable write/source mutation violations | 0/0 | 0/0 | 0/0 |
| Runtime seconds | 151.3 | 70.8 | 97.7 |

V1 met aggregate recall but extracted every preregistered adversarial claim and returned four
invalid responses. V2 added explicit negative rules, category definitions, a bounded completion,
and one structured-output retry. It eliminated forbidden and invalid outputs, but over-omitted
valid facts/preferences and still failed summaries. V3 attempted to restore mandatory affirmed
facts and linked two-source synthesis. It restored facts but destabilized events and continued to
split summaries, so it was rejected.

The product retains v2 as the safer local-Llama prompt. This is not a passing quality claim: v2
fails precision, recall, and summary coverage. It is selected because safety is prioritized for a
review queue, it creates fewer false-review items than v3, and it never gains commit authority.
Automatic acceptance remains prohibited.

## Interpretation and next action

The result shows that prompt-only multi-kind extraction is not reliable enough on this model.
Facts, events, preferences, and multi-source summaries compete for classification behavior, while
strict negative rules trade recall for safety. More tuning against this one corpus would risk
overfitting.

The next extraction-quality slice should compare either a separately prompted summary pass or a
stronger local model against a new frozen multi-author corpus. It must retain v2's zero-tolerance
negative rules, exact provenance, structured retry, review-only boundary, and no-write invariant.
The current result is directional engineering evidence, not a population or provider benchmark.

Machine-readable evidence:

- `2026-07-20-extraction-quality-v1-llama3.1-8b.json`
- `2026-07-20-extraction-quality-v2-llama3.1-8b.json`
- `2026-07-20-extraction-quality-v3-llama3.1-8b.json`
