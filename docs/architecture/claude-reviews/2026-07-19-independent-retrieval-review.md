# Claude Review: Independent Retrieval Evidence

Date: 2026-07-19
Reviewer: Claude Sonnet through stateless Claude CLI prompts

## Evaluation-design review

Claude classified the proposed two-corpus/two-model matrix as a sound engineering acceptance gate but not statistical proof. It recommended blind authorship, explicit scope-isolation checks, preselected distractors, diagnostic-only per-kind results, a clearly bounded model claim, and re-certification when the model set changes. It warned that 12 queries per kind have wide uncertainty and that BGE/MiniLM remain correlated small bi-encoders.

Zero scope violations remains an invariant rather than a noise-tolerant metric. The hard per-cell gate is intentionally conservative for a private pre-release product; no population-level significance claim is made. The 0.20 candidate came from v1, so v1 is development evidence and the blind-authored v2 corpus is the independent confirmation.

## Corpus authoring

Large parallel Claude authoring prompts returned blank and were discarded. Six smaller stateless batches produced the 60 memory/query pairs. The authoring prompts named only a synthetic domain, type balance, semantic-query requirement, IDs, and JSON fields; they did not provide model choice, scores, thresholds, old fixture content, or retrieval results. Codex mechanically normalized schema deviations and froze deterministic distractor/control assignment before model execution.

## Final decision review

After receiving exact paired results, Claude returned **No blocker**. It recommended:

- explicit Python, CLI, and MCP opt-out semantics;
- documenting that filtered results can contain zero through K items;
- recording the default-cardinality change as breaking behavior;
- applying the default only to certified models;
- re-certifying materially new embedding models; and
- reverting on recall/MRR regression, failed leakage targets, scope violations, or credible user evidence of missing results.

The implementation retains the existing typed `RelevanceFilter` API rather than replacing it with a raw float. Python uses explicit `None` to disable, CLI uses `--no-relevance-filter`, and MCP uses the discoverable string `off`. Unknown model identities remain unfiltered.

## Implementation review

After the identity allowlist, opt-outs, effective-policy transport fields, report identity, and tests were implemented, Claude returned **No blocking findings**. Two non-blocking watch items remain: plain Python recall returns records rather than a policy envelope, so callers should inspect `store.default_relevance_filter` or `store.status()` after an identity/runtime change; and MCP policy strings are transport syntax, while Python accepts only `"default"`, a typed `RelevanceFilter`, or explicit `None`. The Python docstring and README preserve that distinction. No background analytics or logging dependency is added.
