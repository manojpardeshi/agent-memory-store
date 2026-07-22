# Proposal Review Personal-Scale Benchmark

Date: 2026-07-20
Result: passed

The repeatable synthetic benchmark scanned 100,001 active rows in one exact target scope and
reviewed one proposal in 1.110027 seconds against the accepted two-second ceiling. Python
`tracemalloc` measured 56,749,450 peak bytes during review. SQLite `total_changes` was unchanged.

The fixture contains generated identifiers and synthetic content only. It uses the deterministic
64-dimension test embedder; review itself performs no embedding or model call. The benchmark measures
one local reference run, not a distributed-service SLO or a population latency claim.

Reproduce with:

```console
uv run python scripts/benchmark_proposal_review.py
```

Machine-readable evidence is stored beside this file in
`2026-07-20-proposal-review-personal-scale.json`.
