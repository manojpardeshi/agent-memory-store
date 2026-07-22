# Reconciliation of Claude MVP Review

Date: 2026-07-15

## Accepted Recommendations

- Keep domain logic independent from the MCP transport.
- Use exact rather than approximate nearest-neighbor retrieval for MVP scale, subject to a local benchmark.
- Pin the embedding model identity, revision, dimension, normalization, and distance metric in the store manifest.
- Use append-only supersession for corrections.
- Make derivation explicitly triggered and retryable; do not introduce a daemon or hidden job runner.
- Make scope filtering mandatory inside the core store API.
- Verify deletion after commit rather than equating a successful SQL statement with deletion correctness.
- Keep filesystem permissions and full-disk encryption as the documented v1 boundary.
- Avoid generic backend plugins, ANN, caching, query DSLs, and multi-model vector spaces.

## Modified Recommendations

### Raw Commit and Embedding

Claude proposed requiring every raw turn and vector to commit atomically. That conflicts with the accepted requirement that optional processing failure must not discard an acknowledged raw turn.

Decision direction: the raw memory row is authoritative. It commits with `embedding_status=pending`; synchronous best-effort embedding may immediately advance it to `ready`. A crash or model failure leaves a visible, retryable pending/failed record rather than losing source data.

### Provenance

Claude proposed JSON arrays of source IDs. JSON references cannot provide reliable foreign-key enforcement or simple cascade traversal.

Decision direction: use a normalized `memory_sources(child_memory_id, source_memory_id, relation)` table with foreign keys and explicit traversal during lineage deletion.

### Scope Shape

Claude's single-axis scope examples do not encode the accepted composite shape.

Decision direction: every scope is exactly one of:

- Private: `(subject, environment, agent_or_app)`
- Shared: `(subject, environment, shared_pool)`

Private is the write and recall default. Shared pools must be named explicitly on write and recall. Wildcards and hierarchy are not supported in MVP.

### MVP Boundary

Claude proposed deferring correction and shared pools beyond the first slice. Both are accepted product behaviors and directly validate the project's differentiation.

Decision direction: implement them minimally in the MVP. Automatic LLM extraction and summarization remain optional adapters; callers can create typed facts, preferences, and summaries directly without an extraction model.

## Rejected or Unproven Claims

- The assertion that exact `sqlite-vec` retrieval will be single-digit milliseconds at 50K records is not accepted without a benchmark on the reference machine.
- Byte-for-byte database comparison is not an appropriate backup correctness test because valid SQLite snapshots can differ physically. Logical export equality plus integrity checks is the acceptance test.
- A `deleted_at` tombstone is unnecessary for a transactional hard-delete operation and will not be added merely as a sequencing aid.
- Per-type extension tables are deferred. MVP type-specific data is limited to a constrained `role` column and validated metadata; extension tables become justified only when a type gains independently queried required fields.

## Round-Two Decisions

- Provenance is a DAG. Each memory stores a generation, and every source must have a lower generation. Cycles are rejected at write time.
- Corrections do not migrate provenance edges. A derived memory remains causally linked to the version from which it was produced.
- Deleting a lineage recursively deletes its causally derived descendants. A preview operation exposes the full blast radius before execution.
- Raw/typed memory commit and embedding are explicitly two transactions. Pending or failed embeddings are visible through direct inspection and export but excluded from semantic recall until processed.
- Superseded versions cannot appear in recall. Their vector rows are removed when the new version becomes the active correction.
- Scope enumeration uses the normalized `scopes` table. Recall fan-out is intentionally limited to a small number of explicitly allowed scopes and fetches candidates independently from each before global ranking.
- Vector rows, provenance edges, and memory rows are removed in one deletion transaction, followed by orphan checks.
- New stores enable incremental auto-vacuum. Deletion performs a WAL checkpoint and incremental vacuum as maintenance, without claiming forensic erasure.

## MVP Delete Guarantee

MVP guarantees **logical hard deletion from the active database**:

- Target rows, embeddings, provenance edges, and selected lineage rows are removed transactionally.
- Post-commit verification queries confirm absence.
- WAL is checkpointed after deletion.
- `PRAGMA secure_delete=ON` is enabled where supported.

This does not guarantee forensic erasure from SSD wear-leveling, filesystem snapshots, Time Machine, synced folders, exported JSON, or prior backups. Those copies are outside the active-database delete boundary and must be managed separately.

## Implementation Review Disposition

Claude's independent implementation review initially issued a no-ship recommendation for the portability surface. The findings were reconciled as follows:

- **Accepted and fixed:** logical export requires exactly one explicit scope, subject, or whole-store selector. MCP export is preview-and-confirm. Subject-wide and whole-store CLI exports require `--yes`.
- **Accepted and fixed:** restore requires CLI `--yes`, refuses every existing destination, never removes another database's WAL/SHM files, and cleans up a partial destination on failure.
- **Accepted and fixed:** databases are securely pre-created at `0600`; backup/export use `0600` temporary files and atomic replacement, eliminating the permissive creation window.
- **Accepted and fixed:** backup/export refuse overwrite by default; overwrite is explicit, and MCP backup is preview-and-confirm.
- **Accepted and fixed:** duplicate operation IDs that race at the unique constraint resolve to the committed record. Both remember and correction paths retry embedding if needed.
- **Accepted and fixed:** derived-memory sources must be active, preventing new derivations from corrected stale versions.
- **Accepted with deferred strengthening:** deletion recomputes the cascade at execution time. This favors complete privacy deletion over leaving newly derived descendants behind. At personal single-writer scale the race window is small, and the execution receipt contains the actual recomputed preview. A revision-bound confirmation token is required before claiming strict multi-process "delete exactly what was previewed" semantics.

The fixed behaviors are covered by the portability, MCP, store, and deletion tests. Claude did not edit the repository; its preserved review is advisory evidence in this log.

Claude's final follow-up changed its recommendation to **ship for private, single-user, single-writer use**. It requested explicit confirmation-abort and forced operation-ID race tests before widening scope; both were added immediately and pass. Public release remains governed by the separate public-release gate.
