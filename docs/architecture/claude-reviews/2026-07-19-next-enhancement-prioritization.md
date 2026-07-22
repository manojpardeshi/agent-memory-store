# Claude Review: Next Enhancement Prioritization

Date: 2026-07-19

## Prompt sent to Claude

Act as a skeptical principal software architect and product engineer. Prioritize the next enhancement cycle for a private, local-first personal LLM memory store that already has:

- Python API, CLI, and stdio MCP interfaces over SQLite plus sqlite-vec.
- FastEmbed local embeddings with a pinned behavioral fingerprint.
- Private exact scopes and explicit shared pools.
- Typed turns, facts, preferences, summaries, and events.
- Versioned correction, provenance, hard-delete preview/cascade/verification, JSON export, and SQLite backup/restore.
- A real provider interoperability demo across Claude, hosted GPT through Codex CLI, and local `llama3.1:8b` through loopback Ollama.
- 29 passing tests, a measured 20,000-vector retrieval benchmark, and a private Codeberg repository.

The unresolved product/release items are:

1. A representative, versioned retrieval-quality evaluation set and numeric usefulness threshold (the explicit public-release blocker OQ-009).
2. Automatic fact/preference extraction and summarization, previously deferred because caller-created typed memories are deterministic.
3. Physical purge of expired rows.
4. Embedding-model migration/re-embedding.
5. JSON import and cross-schema migration.
6. A clearer integration starter for real applications.
7. An irrelevant-memory negative control for the model-switching evaluation.

Constraints: one trusted OS user, local/offline core, tens of thousands of memories, no network listener, no multi-user auth, no daemon, and no silent model fallback. Changes must remain independently testable and must not weaken explicit scope isolation or deletion semantics.

Recommend an ordered product roadmap, then choose exactly one first implementation slice that can ship independently in this cycle. Define its user outcome, non-goals, measurable acceptance criteria, security/privacy implications, and architectural trade-offs. Identify blockers honestly. Do not inspect or edit files. Return the complete review now.

## Claude response

### Roadmap (ordered)

1. **Retrieval-quality eval harness + numeric threshold (OQ-009), with irrelevant-memory negative controls folded in** — the only item that's an explicit release blocker, and every downstream item (migration, extraction) needs a quality gate to measure against. Ships first or nothing after it is trustworthy.
2. **Physical purge of expired rows** — pure data-hygiene correctness, low blast radius, no new product surface. Do this before anything that grows the corpus (extraction), since a bigger corpus with stale rows makes purge harder to retrofit later.
3. **Embedding-model migration/re-embedding** — high blast radius (touches every row), only defensible once you can measure "did quality regress" via #1.
4. **JSON import + cross-schema migration** — completes the export/import loop and gives you a rollback path before you introduce schema-affecting features.
5. **Integration starter for real applications** — DX/adoption work. Don't invite real usage until #1 tells you the retrieval is actually good.
6. **Automatic fact/preference extraction and summarization** — last, deliberately. It's the riskiest item: it breaks the deterministic "caller-created memory" invariant, introduces LLM-in-the-loop non-determinism into what's currently a clean typed store, and pollutes exactly the corpus that #1 measures. It should be built *against* an existing eval harness, not before one exists.

Item 7 (negative control) is a design requirement of a correct evaluation set, so it is merged into item 1 rather than sequenced separately.

### Chosen first slice: retrieval-quality eval harness (OQ-009 + negative controls)

**User outcome**

Running one local command scores retrieval against a fixed, versioned dataset and returns pass/fail against a documented numeric threshold—giving the maintainer a defensible answer to "is this good enough to make the repo public," and a regression gate for every future retrieval-affecting change.

**Non-goals**

- No retrieval-algorithm tuning—a failing score is a finding, not something this slice fixes.
- No automatic extraction/summarization.
- No CI wiring—this is a manual pre-release gate for a single-user offline tool, not a daemon.
- No claim of statistical rigor—approximately 50 single-user queries are a heuristic bar, not a scientific benchmark, and should be labeled as such.

**Acceptance criteria**

- Versioned dataset, at least 50 queries spanning private-exact and shared-pool scopes and all five typed-memory kinds, each with expected-relevant IDs and at least one negative-control distractor ID that must not appear in top K.
- Harness computes Recall@K, MRR, and distractor-leak rate; threshold is a written specification, not a docstring.
- Fully offline after the pinned model is cached, deterministic, and bounded to under 60 seconds for 50 queries.
- Ten to fifteen deterministic tests covering metric computation and threshold logic.
- Negative-control assertions double as scope-isolation regression coverage.
- A written pass/fail decision record checked into the repository.

**Security/privacy implications**

- The evaluation corpus must be synthetic/maintainer-authored, never real personal memory content.
- No new interfaces or listeners; it remains a local command.
- Negative controls add isolation regression coverage.

**Architectural trade-offs**

- Store the evaluation fixture as an isolated dataset and run it through a standalone evaluation command so it does not slow ordinary tests.
- Keep metrics simple and dependency-free rather than adding an evaluation framework.
- Do not start embedding migration in parallel; it depends on this quality gate.

**Blockers, honestly**

- "Representative" is judgment-based for a single-user store; scope v1 to the use cases already demonstrated and version it for growth.
- There is no existing quality baseline, so build the harness and dataset, run them, then set a threshold from observed results plus margin rather than inventing one first.
- Curating 50 or more query/expected-result pairs is manual work and should not be automated using the extraction capability that remains deferred.
- Passing this gate does not by itself complete every public-release requirement.

## Reconciliation

Accepted. The implementation order is recorded in the product roadmap. This cycle is limited to OQ-009 plus negative controls; it does not tune retrieval or introduce automatic extraction. Thresholds will be set only after the first real FastEmbed baseline is measured.
