# Extraction Quality Gate

Last updated: 2026-07-20
Status: implemented; offline gate passed and first live target failed

## Decision objective

Measure whether an extractor proposes the right durable memories without rewarding over-extraction or granting model output authority. The gate evaluates proposal generation only. It never writes a proposal artifact, accepts a proposal, or changes durable typed memory.

The first use is diagnostic: determine whether local `llama3.1:8b` is complete and precise enough to make review useful. Passing does not authorize automatic acceptance. Failing preserves the review-first product and supplies a reproducible improvement baseline.

## Users, scale, and tracks

- One local product owner and developers integrating the Python/CLI proposal workflow.
- A versioned, synthetic corpus containing no personal or user-derived memory.
- `offline`: a small explicit-label track for deterministic CI and evaluator correctness.
- `live`: at least 50 natural-language cases for one labelled local-model observation.
- Positive claims are balanced across fact, preference, summary, and event. Negative, transient, instruction-like, duplicate-pressure, and prompt-injection cases are included.

Fifty natural cases are an engineering sample, not population-level statistical proof. Per-kind and interval results are diagnostics. A larger multi-author corpus is required before any generalized model-quality claim.

## Dataset contract

Each case declares:

- stable case ID and track;
- one or more synthetic source turns with stable fixture IDs, roles, and content;
- zero or more expected durable claims with expected kind and exact source fixture IDs;
- judge-free anchor groups organized into atomic fact units; and
- zero or more forbidden claims with anchor groups and a reason.

An anchor group is a list of preregistered textual alternatives. A group matches when at least one normalized alternative occurs in proposal content. An atomic fact unit is covered only when every group in that unit matches. Content matching is case-insensitive Unicode-normalized token/phrase matching, not raw substring matching.

Non-summary claims require all declared fact units. Summary quality is `covered fact units / declared fact units`; every preregistered critical unit is required for an exact content match. Summary coverage below 0.85 is reported as incomplete. Corpus authors must use distinctive entity/value/relation anchors and avoid overlapping expected claims within a case.

The full dataset and thresholds are frozen before the first model run. No source, anchor, expected claim, forbidden claim, or threshold may be edited in response to results.

## Metrics

For every proposal, map model source IDs back to fixture IDs and evaluate:

- `exact_precision`: exact true positives / all proposals;
- `exact_recall`: exact true positives / expected claims;
- `exact_f1`;
- `content_recall`: claims with a deterministic content match / expected claims;
- `kind_accuracy`: correct kind among content-matched claims;
- `provenance_accuracy`: exact source fixture set among content-matched claims;
- `summary_fact_unit_coverage`;
- `forbidden_proposal_count` and affected cases;
- normalized duplicate proposal count;
- invalid/error case rate; and
- source/no-write verification for every case.

An exact true positive requires deterministic content match, correct kind, and the exact expected source set. One proposal can satisfy at most one expected claim. Additional proposals are false positives. A forbidden match is counted regardless of kind or provenance.

Wilson 95% intervals accompany precision and recall to show uncertainty. They do not replace the preregistered product thresholds.

## Thresholds

Offline deterministic gate:

- exact precision, recall, kind accuracy, provenance accuracy, and summary fact-unit coverage: `1.00`;
- forbidden proposals, duplicates, and invalid cases: `0`;
- source/no-write verification: hard pass.

Live local-model evidence target:

- exact precision at least `0.75`;
- exact recall at least `0.65`;
- kind accuracy at least `0.80`;
- provenance accuracy at least `0.90`;
- summary fact-unit coverage at least `0.85`;
- invalid case rate at most `0.05`;
- forbidden proposal count and duplicates: `0`; and
- source/no-write verification: hard pass.

Forbidden extraction, any durable write, or source mutation fails the gate regardless of aggregate scores. These thresholds prioritize review safety over completeness while requiring materially better completeness than the first 1/3-statement observation.

## Failure and security semantics

- Each case uses an isolated exact scope in a temporary deterministic-embedding store.
- The evaluator records memory counts and source hashes before and after proposal generation.
- Extractor exceptions and malformed model output are case errors, never partial successes.
- Source instructions remain untrusted data and the local model receives no tools.
- Reports contain synthetic proposal text and fixture IDs only; public memory IDs, store IDs, database paths, and raw runtime paths are excluded.
- Reports are owner-only, no-overwrite artifacts.
- The CLI is Python/local-only and opens no listener. Ollama remains loopback-only.

## Trade-offs and assumptions

- Deterministic anchors make the gate reproducible but undercount correct paraphrases that omit every registered alternative. Results are conservative directional evidence.
- Embedding similarity and LLM-as-judge fallback are excluded because they would add another model-dependent, tuneable decision surface. Unmatched proposals remain visible for human audit.
- Exact provenance is intentionally strict. Citing an extra selected source is not equivalent to the declared derivation.
- Summary fact units measure inclusion, not fluency, compression, contradiction, or overall prose quality.
- Aggregate thresholds can hide kind-specific weakness; per-kind results are always reported but initially diagnostic due to sample size.
- Passing never enables auto-accept. A separate architecture decision and consent design would still be required.

## Success evidence

- Versioned schema validation and frozen dataset digest.
- Deterministic scorer/unit tests, including false positive, wrong kind, wrong source, forbidden, duplicate, invalid-output, and no-write cases.
- One local command producing an owner-only report.
- Offline deterministic gate result.
- Labelled `llama3.1:8b` report, including failures and unmatched proposals.
- Claude design and implementation review preserved in the architecture record.
