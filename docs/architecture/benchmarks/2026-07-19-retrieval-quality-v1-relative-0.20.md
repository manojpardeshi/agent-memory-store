# Retrieval Quality v1: Opt-In Relative Filter

Date: 2026-07-19
Status: **candidate passes; default-path release gate remains failed**

## Configuration

- Corpus: `personal-retrieval-v1`
- Dataset SHA-256: `a5360cc957e9defe51363b20b5e179668dad553365d6f4bf8ae056202f450889`
- Embedding: `BAAI/bge-small-en-v1.5`, FastEmbed 0.8.0, 384 dimensions
- Retrieval limit: five
- Opt-in filter: `relative_semantic_gap`, maximum gap 0.20 from the top-ranked result's semantic score
- Runtime: local cached model only

The filter is applied after ordinary ranking and may return fewer than the requested limit. It does not change scope authorization and is not enabled by default.

## Measured comparison

| Metric | Default path | Opt-in relative 0.20 | Gate |
| --- | ---: | ---: | ---: |
| Recall@5 | 0.98 (49/50) | 0.98 (49/50) | ≥ 0.90 |
| MRR | 0.98 | 0.98 | ≥ 0.85 |
| Designated distractor leakage | 0.24 (12/50) | 0.06 (3/50) | ≤ 0.10 |
| Private distractor leakage | 0.40 (10/25) | 0.08 (2/25) | diagnostic |
| Shared-pool distractor leakage | 0.08 (2/25) | 0.04 (1/25) | diagnostic |
| Inaccessible-scope violations | 0 | 0 | 0 |
| Runtime | 0.48 s | 0.63 s | ≤ 60 s |

## Decision

Ship the filter as an explicit compatibility-preserving option. Do not enable it by default and do not mark the default-path release gate fixed. Evidence is limited to one synthetic corpus and one embedding model; relative-gap portability is a hypothesis, not a demonstrated property.

A default change requires both:

1. a second independently authored corpus with a different distractor design; and
2. validation against at least one additional FastEmbed embedding model.

Machine-readable evidence is in `2026-07-19-retrieval-quality-v1-relative-0.20.json`.
