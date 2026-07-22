# Claude Review: Embedding Migration

Date: 2026-07-19

## Questions sent to Claude

Claude was asked to review three bounded decisions without inspecting or editing the repository:

1. A snapshot-based, new-destination workflow that validates source and target fingerprints, preserves the complete logical graph, re-embeds active rows, verifies compatibility, and atomically publishes only to a nonexistent destination.
2. A quality policy when the source default path already fails the absolute distractor gate but the opt-in relative filter passes.
3. Whether Python, CLI, and/or MCP should expose the migration.

## Claude response

### Structural versus quality success

Keep structural migration and quality approval separate. Migration correctness is established through data integrity, counts, checksums, complete re-indexing, and target identity. Retrieval behavior is a distinct measured conclusion.

Target evaluation should run before publication. Use both absolute gates and comparison with the source, but do not make the already-failed absolute distractor gate the sole blocker: doing so would either prevent every migration or falsely recast the source baseline. A source-to-target regression should block by default; absolute failure remains explicitly reported. A valid outcome may therefore read: structurally migrated, no regression, absolute gate still failing.

### Surfaces

Ship Python and CLI first; defer MCP execution. Migration is path-sensitive, model-loading intensive, and potentially minutes long. An agent-triggered MCP action increases arbitrary-path, resource-exhaustion, and prompt-injection exposure. Preview should show paths, models, record workload, and confirmation data before execution.

### Source safety

Claude agreed with new-destination publication and emphasized stable input, a target that never becomes visible before verification, complete cleanup on failure, and exact preservation of non-vector state. One attempted follow-up review was discarded because the Claude CLI returned an unrelated tool-state warning rather than analysis; no decision relies on that response.

## Reconciliation

Accepted with two refinements. Human CLI paths are not restricted to an artificial application root: safety comes from explicit paths, valid source fingerprint, nonexistent destination, owner-only creation, and no overwrite. Quality regression is checked on both the unchanged default retrieval configuration and the opt-in relative-gap 0.20 candidate. Exact metric regressions block by default because the corpus and embeddings are deterministic; a deliberate override remains visible in the receipt rather than silently relaxing the gate.

The full accepted contract is in `docs/architecture/embedding-migration-contract.md`. Implementation must not be presented as closing the public-release gate: a second independently authored corpus is still required before any default relevance change.

## Implementation review and reconciliation

Claude approved the implemented preview, snapshot, copy, evaluation, verification, and atomic-publication chain with no blocking finding. It requested confirmation that publication cannot clobber a destination created after preview, that crash recovery is documented, that concurrent publishers are tested, and that regression overrides retain an audit trail.

The review exposed a real check-then-`os.replace` race, so the implementation was tightened before commit. Final publication now uses atomic same-filesystem hard-link creation, which fails if the destination name exists; a simulated competing publisher test proves its file is preserved. Crash recovery is explicitly fresh-run rather than resume. A regression override now requires a written reason and records it with the metrics, timestamp, and trusted-local-user boundary.
