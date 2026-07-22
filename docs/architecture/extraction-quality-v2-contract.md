# Extraction Quality v2 Experiment

Last updated: 2026-07-20
Status: completed; two-pass and model alternatives rejected

## Objective and users

Improve the usefulness of explicit, review-only local extraction without weakening its authority
boundary. The users are the single local owner reviewing proposals and developers integrating the
Python/CLI workflow. The experiment does not enable background extraction, automatic acceptance,
MCP mutation, or a network service.

## Requirements and scale

- Preserve the existing single-pass `ollama` extractor as the measured baseline.
- Add a separately selectable `ollama-two-pass` extractor with a fact/preference/event pass and a
  summary-only pass for inputs containing at least two sources.
- Validate each pass independently before deterministic merge; a failed pass fails the case.
- A valid summary must cite at least two selected sources. When it exists, suppress atomic proposals
  whose complete source set is covered by that summary; retain unrelated atomic proposals.
- Keep exact immutable source-memory provenance and the existing proposal/bundle identities.
- Measure both variants on the same new frozen 50-case live corpus: 10 expected claims per kind and
  10 negative cases. Include a strict explicit-label offline track for evaluator regression.
- Run on the pinned loopback `llama3.1:8b` build first. Model comparison is the stop-rule fallback,
  not part of the initial architecture claim.

Expected personal scale is at most 20 selected source turns and 50 proposals per reviewed bundle.
Two-pass inference trades roughly one additional model call for multi-source inputs; latency is
telemetry, not a correctness gate.

## Security and privacy invariants

- Both passes use the existing unauthenticated loopback-only Ollama validation and reject redirects.
- Source data is untrusted in both prompts; neither pass receives tools or a write channel.
- Proposal generation creates no artifact and cannot call acceptance. The evaluator verifies memory
  count and exact source hash/status/content before and after every case.
- Every proposal cites only selected memory IDs. Summary proposals cite at least two; the normal
  canonical validator rechecks the merged response and exact scope.
- Invalid, unknown-kind, invented-source, oversized, duplicate-key, or incomplete output fails
  closed. There is one bounded structured-output retry per pass.
- The corpus is synthetic and contains no owner data. Reports remain owner-only and omit database
  paths, public memory IDs, and source-store identifiers.

Whole-source provenance remains the accepted granularity. Claude suggested source spans, but adding
offsets would change the storage/proposal contract and create normalization/staleness semantics not
needed to test the two-pass hypothesis. Immutable source hashes and exact source sets are retained.

## Success criteria

Absolute live gates remain at least:

- exact precision `0.75`;
- exact recall `0.65`;
- kind accuracy `0.80`;
- provenance accuracy `0.90`;
- summary fact-unit coverage `0.85`;
- forbidden proposals, duplicates, ambiguous matches, invalid cases, writes, and source mutations:
  `0`.

The two-pass variant must also improve summary coverage by at least `0.20` and exact recall by at
least `0.10` over the paired single-pass result, without more than `0.02` precision regression. A
pass never authorizes automatic acceptance.

## Corpus independence and stop rules

The new extraction-v2 corpus is authored before either model run. Blind Claude seeds and separate
Codex-authored cases use new entities, wording, and relations; no extraction-v1 source or anchor is
copied. Case IDs retain author provenance. Prompts and deterministic merge are frozen before the
corpus digest is measured. Labels/anchors may be audited before the first run but never edited in
response to results.

If either variant produces a forbidden proposal, invalid case, write, or source mutation, record the
full run and stop architecture promotion. If the two-pass variant misses its absolute or paired
gates, do not tune it on this corpus. Proceed to a same-prompt model comparison on a separately
approved corpus or treat the limitation as model-bound.

## Assumptions and trade-offs

- Separating tasks will reduce category competition observed in extraction-v1.
- A summary proposal is a reliable deterministic signal for suppressing covered atomic components;
  an incorrect summary can therefore reduce useful atomics, but remains visible for review.
- If the summary pass returns nothing, atomics remain. This favors partial review usefulness over
  silently discarding supported claims.
- Multi-source input is not always summary-worthy; the summary pass may return an empty array.
- Two calls increase latency and energy use on the M2 Mac mini. Narrower prompts and bounded output
  are expected to offset some cost, but correctness and review load take priority.
- One 50-case, two-author synthetic corpus is engineering evidence, not population-level proof.

## Options and decision

| Option | Benefit | Cost/risk | Decision |
| --- | --- | --- | --- |
| Dedicated two-pass plus deterministic merge | Directly tests category-overload hypothesis and isolates summary behavior | More calls; merge suppression can hide atomics | Selected for this slice |
| Existing prompt across installed models | Distinguishes model capability but keeps overloaded task | More model variance; does not fix task structure | Fallback if selected slice fails |
| More single-pass tuning on extraction-v1 | Lowest code change | Benchmark contamination and observed category instability | Rejected |
| Source-span provenance | Finer evidence | New schema, offset normalization, and stale-span policy | Deferred |
