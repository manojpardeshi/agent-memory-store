# Claude Review: Relevance Calibration

Date: 2026-07-19

## Prompt sent to Claude

Act as a skeptical principal architect reviewing the next retrieval-quality change for a private, local-first LLM memory store. Use only the facts below. Recommend one bounded implementation slice, or recommend measurement-only if the evidence is insufficient. Return Verdict, Evidence interpretation, Option assessment, Decision, Acceptance criteria, and Risks. Do not inspect or edit files.

Current production recall performs exact KNN independently per explicitly allowed scope, merges results, scores 80% semantic similarity plus 20% recency, and always returns up to the requested limit (default five). It has no minimum relevance filter. Scope isolation is exact and passing.

Retrieval-v1 contains 50 wholly synthetic memories and 50 queries across private exact scopes and explicit shared pools. Every query has one expected item and one topically unrelated but accessible distractor. The initial default top-five baseline measured Recall@5 0.98, MRR 0.98, distractor leakage 0.24, and zero scope violations. Per-stratum random controls showed private distractor leakage 0.40 versus random 0.40, while shared leakage was 0.08 versus random 0.40. The quality ceiling is a normative 0.10.

We added diagnostic-only full ranking evidence without changing production behavior. Semantic-score distributions:

- Private expected items: min 0.634, median 0.751, max 0.821.
- Private distractors: min 0.284, median 0.434, max 0.646. Leaked distractors have median 0.493.
- Shared expected items: min 0.638, median 0.794, max 0.890.
- Shared distractors: min 0.307, median 0.520, max 0.692.

Offline simulations over the existing top-five rankings:

1. Absolute semantic floor 0.50: recall 0.98, MRR 0.98, leak 0.10, average 3.12 returned; private leak 0.16, shared 0.04.
2. Absolute floor 0.53: recall 0.98, MRR 0.98, leak 0.06, average 2.64; private leak 0.08, shared 0.04.
3. Absolute floor 0.65: recall 0.96, MRR 0.96, leak 0, average 1.96.
4. Relative cutoff keeping results whose semantic score is within 0.20 of the top result: recall 0.98, MRR 0.98, leak 0.06, average 2.34; private leak 0.08, shared 0.04.
5. Relative gap 0.25: recall 0.98, MRR 0.98, leak 0.12.

Constraints and trade-offs:

- The store supports a configurable FastEmbed model but binds each database to one fingerprinted embedding space. Raw semantic-score calibration may vary by model.
- A relative cutoff is more model-scale-neutral but can retain an irrelevant top result and discard a relevant lower result.
- An absolute floor can reject an entirely irrelevant result set but may be overfit to `BAAI/bge-small-en-v1.5`.
- Changing the default alters existing recall behavior by returning fewer than `limit`; adding optional parameters only would preserve compatibility but leave the default product gate failing.
- Recalled content is untrusted input to an LLM, so reducing irrelevant context is defense in depth, not an authorization control.
- Evidence comes from one synthetic corpus; no user-derived data or universal quality claim is allowed.

Assess absolute 0.53, relative gap 0.20, a hybrid, optional-only controls, or a measurement-only next step. If recommending a default change, specify how to expose it in Python, CLI, and MCP without silent incompatibility and how to record it in reports and architecture. Identify whether a second independent corpus is a blocker before default behavior changes.

## Claude response (preserved with minor copy-editing)

### Verdict

Ship a **bounded, opt-in relevance filter** (relative gap 0.20) exposed as an explicit parameter across Python/CLI/MCP. **Do not change the default** yet. The default-change question is evidence-insufficient: everything here is one synthetic corpus under one embedding model, and absolute 0.53 versus relative 0.20 are statistically tied. Theory alone should not drive a breaking default change.

### Evidence interpretation

- Baseline 0.24 leakage fails the stated 0.10 normative ceiling.
- Absolute 0.53 and relative gap 0.20 are indistinguishable on this corpus: recall 0.98, MRR 0.98, leak 0.06, and private/shared leak 0.08/0.04. Their small return-count difference is not a basis for choosing.
- The fingerprinted store supports multiple FastEmbed models, so the model-specific risk of an absolute threshold favors a relative-gap candidate. Relative portability remains asserted rather than measured until tested with another model.
- Absolute 0.65 rejects true expected items; relative 0.25 fails the leak ceiling; no hybrid was measured.
- Private-scope ranking remains a separate concern: filters compensate for the weak top-five set rather than fixing ranking.

### Decision

1. Implement relative-gap filtering with 0.20 as an explicit opt-in. Preserve default behavior exactly.
2. Block a default change pending a second independently constructed corpus and at least one additional FastEmbed model.
3. Use an explicit Python type, CLI syntax such as `relative:0.20`, and an optional MCP parameter whose description states that filtering may return fewer than the requested limit.
4. Record corpus, embedding identity, and filter configuration in evaluation reports.
5. Keep the default-path release gate red; do not imply the opt-in result fixes default retrieval.

### Acceptance criteria

- Unset recall returns the same count and ranking as before.
- Opt-in relative 0.20 reproduces recall 0.98, MRR 0.98, and leak at most 0.06.
- Python, CLI, and MCP tests cover unset and filtered behavior.
- Documentation states opt-in status and shortened-result semantics.
- No default-path release claim changes.

### Risks

- Corpus and model overfit remain possible.
- Relative 0.20 is close to the 0.25 failure point.
- Shipping an opt-in filter could create a false sense that private-scope ranking is fixed.
- An LLM MCP caller may misunderstand a shortened result unless the tool description is explicit.

## Reconciliation

Accepted and implemented without changing defaults. `RelevanceFilter` is an explicit validated type; `None` preserves current ranking and result-count behavior. Python callers can use `RelevanceFilter.relative(0.20)`, while CLI and MCP accept `relative:0.20`. Filtered CLI/MCP responses identify the active filter and warn that fewer than `limit` items may be returned.

Evaluation reports now record the complete filter configuration. The real offline filtered run passes retrieval-v1 at Recall@5 0.98, MRR 0.98, distractor leakage 0.06, and zero scope violations. A separate default report remains failed at 0.24 leakage. Tests cover typed validation and both unset/filtered paths through the store, CLI, MCP subprocess, and evaluator.

The default-change block is documented: no default relevance filter until a second independently authored corpus and another embedding model validate portability. The private-scope ranking weakness remains open rather than being relabeled as fixed.

## Follow-up prompt sent to Claude

We implemented your bounded recommendation. `RelevanceFilter` is a validated explicit Python type with strategy `relative_semantic_gap`; `None` is the unchanged default. `MemoryStore.recall(..., relevance_filter=RelevanceFilter.relative(0.20))` applies filtering after ordinary ranking and may return fewer than `limit`. CLI and MCP accept only an explicit string such as `relative:0.20`; filtered responses record the active filter and a shortened-results warning. The MCP tool description contains that warning. Evaluation reports record filter configuration and default-versus-opt-in status.

Two separate real offline reports are preserved. Default remains failed: recall/MRR 0.98/0.98, distractor leak 0.24, private/shared leak 0.40/0.08, zero scope violations. Opt-in relative 0.20 passes: recall/MRR 0.98/0.98, distractor leak 0.06, private/shared leak 0.08/0.04, zero scope violations. Documentation and AD-030 say the filtered candidate does not close the default release gate; a default change requires a second independent corpus and another embedding model. Forty-eight tests pass, covering both unset and filtered store, CLI, MCP subprocess, and evaluation paths; lint and package build pass. Are any concrete blockers left before committing this opt-in slice? Reply with Verdict, Remaining blockers, and Next action only. Do not inspect or edit files.

## Claude follow-up response

### Verdict

No concrete blockers. The opt-in slice is internally consistent: bounded type, `None` default preserved, gate unchanged, two real offline reports, 48 tests, and green lint/build. It is ready to commit.

### Remaining blockers

None technical. Stage implementation, documentation, AD-030, evidence, and tests together so the commit is complete.

### Next action

Commit the complete opt-in slice as one coherent change.
