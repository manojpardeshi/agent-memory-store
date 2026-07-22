# Claude Review: Physical Expiry Purge

Date: 2026-07-19

## Prompt sent to Claude

Act as a skeptical principal architect reviewing a bounded physical-expiry-purge feature for a private, local-first, single-user, single-writer LLM memory store. Use only the facts below. Return Verdict, Semantic decision, API contract, Safety invariants, Acceptance criteria, and Risks. Do not inspect or edit files.

Current design:

- SQLite plus sqlite-vec, one portable database, exact scopes, no daemon or network listener.
- Memories can have timezone-aware `expires_at`. Recall already lazily excludes active rows at or before the current UTC time, but expired rows, vectors, and provenance remain physically stored.
- Corrections create a new version in the same lineage and mark the previous version superseded. Corrected versions currently inherit the old expiry timestamp.
- Provenance is a DAG in `memory_sources(child_id, source_id, relation)`. Hard-delete of a selected memory expands to all versions in its lineage and recursively deletes derived descendants. Deleting a derived memory does not delete its sources.
- Existing hard deletion previews exact public memory IDs, lineage IDs, and kind counts. Execution removes provenance edges, vectors, and memory rows in one immediate transaction; post-commit checks verify absence; then WAL checkpoint and incremental vacuum run. CLI and MCP require an explicit confirmation flag, while the Python store method is a trusted domain API.
- SQLite foreign keys prevent dangling provenance edges. `secure_delete=ON` is enabled. The product does not promise forensic erasure of free pages, backups, exports, or media.

Proposed bounded slice:

1. Add `preview_expiry_purge(as_of=None)` and `purge_expired(as_of=None)` to Python. `as_of` is an explicit timezone-aware UTC-normalized timestamp; omitted means one captured current UTC instant.
2. The preview selects every memory whose own `expires_at <= as_of`, regardless of active/superseded state, then reuses the existing lineage-plus-derived-descendant closure. This means a live unexpired descendant derived from an expired source is included, preserving the existing rule that physical removal cannot leave a provenance-dependent child without its source. A single expired version causes all versions in that lineage to be selected, matching hard-delete lineage semantics.
3. Preview records the cutoff, directly expired seed IDs, full cascaded memory IDs, lineage IDs, kind counts, expired-seed count, total purge count, and cascaded non-expired count. It performs no write.
4. Execution must consume the preview's captured cutoff and re-resolve the selection inside one immediate transaction to avoid deleting rows that were corrected or changed between preview and execution. The receipt records cutoff, counts for memories/vectors/provenance edges, and verifies no selected memories, vectors, or touching provenance edges remain.
5. CLI `purge-expired [--as-of ISO]` returns a preview unless `--yes`; MCP `memory_purge_expired(as_of?, confirm=false)` behaves likewise. The confirmation boundary is explicit, with no background scheduler.
6. Empty purges are successful and verified. Invalid or naive timestamps fail. The operation does not delete unexpired unrelated memories and does not delete source ancestors of an expired derived memory.

Major options:

- A: Cascade from expired seeds through the existing lineage-and-descendant hard-delete closure (proposed). Strong provenance consistency and semantic continuity with hard delete; may remove unexpired descendants earlier than their own TTL.
- B: Delete only rows whose own timestamp expired and remove touching provenance edges. Less data loss but silently strips provenance from live descendants and may partially delete correction lineages.
- C: Block purge when expired memories have unexpired descendants and require manual resolution. Safest against surprise cascading but makes routine TTL cleanup unreliable and operationally burdensome.
- D: Detach or snapshot provenance into tombstones before deleting seeds. Preserves live descendants but introduces a schema/migration and a new tombstone lifecycle, beyond a bounded slice.

Review whether A is the correct MVP semantic choice. Pay special attention to time-of-check/time-of-use behavior, whether execution should accept a preview token/digest or simply recompute using the same cutoff, how confirmation should work across Python/CLI/MCP, and whether the receipt fields are sufficient. Identify concrete blockers before implementation.

## Claude response

### Verdict

Reject the proposed automatic cascade into unexpired descendants. Hard deletion and expiry purge represent different authority: hard deletion is an explicit request to destroy a lineage, while expiry is a per-record retention policy and does not authorize early deletion of durable derived memories.

### Semantic decision

An expired memory is purge-safe only when removing it cannot orphan or implicitly delete an unexpired descendant. When a durable summary still depends on an expired raw turn, leave the raw turn physically present, report the dependency, and reconsider it on a later purge. Tombstones could eventually preserve provenance without retaining payloads, but require a separate schema and lifecycle decision.

An expired derived child remains purgeable when its source ancestor is unexpired. Removing the child and its provenance edge neither deletes nor orphans the source and matches the existing rule that deleting a derived memory does not delete its ancestors.

### API contract

- Capture one timezone-aware cutoff and reuse it verbatim for preview and confirmation.
- Preview by default in CLI and MCP; require explicit confirmation for execution.
- Recompute eligibility under `BEGIN IMMEDIATE` with the same cutoff.
- Return a digest over the cutoff and sorted candidate sets. A confirming caller may supply it to abort if intervening writes changed the preview.
- A batch may report blocked expired candidates while atomically deleting the complete safe set. It must never partially commit the safe set.
- The receipt should include the cutoff/digest, deleted memory/vector/provenance counts, a commit timestamp, and verification.

### Safety invariants

- Do not delete or orphan an unexpired descendant during routine expiry cleanup.
- Do not expand the cutoff from preview time to execution time.
- Do not leave a partial committed purge if deletion or verification fails.
- Do not introduce a scheduler or tombstone schema in this bounded slice.

### Acceptance criteria

- Safe expired leaves and fully expired correction lineages are physically removed.
- Expired sources with unexpired descendants remain and are reported with blockers.
- Unexpired ancestors of expired derived memories do not prevent safe child removal.
- A stale expected digest aborts without deleting anything.
- Invalid or timezone-naive cutoffs fail.
- Empty purges succeed with a verified zero-count receipt.

### Risks

- Blocked expired payloads remain on disk until descendants expire, are explicitly deleted, or a future tombstone design is accepted.
- A caller that confirms without a digest intentionally accepts the recomputed current safe set at the fixed cutoff.
- Preview lists can become large at the upper end of personal scale.

## Reconciliation

Claude's objection changed the implementation decision. The original cascade option was rejected for retention cleanup because it could delete an unexpired curated summary merely because its raw source reached TTL. The implemented algorithm starts from unexpired rows and walks backward through correction lineages and provenance parents, protecting every expired row whose deletion graph reaches live memory. The remaining expired set is safe and is deleted atomically.

The broader suggestion to block on unexpired source ancestors was narrowed after follow-up review: ancestors are unaffected when an expired derived child is removed, so they do not block it. This retains the accepted directional deletion rule.

Preview includes the normalized cutoff, expired, purgeable, blocked, and blocking IDs, purge lineage/kind counts, and a SHA-256 digest. Execution recomputes under an immediate transaction, optionally compares the digest, removes rows/vectors/edges, verifies absence before commit, checkpoints the WAL, and runs incremental vacuum. CLI and MCP preview unless explicitly confirmed; there is no scheduler. Tests cover safe and blocked graphs, correction lineages, stale preview rollback, invalid cutoffs, empty batches, CLI, and MCP.

## Claude implementation review

After implementation, Claude reviewed the graph rule, immediate-transaction recomputation, optional digest, atomic row/vector/edge deletion, post-delete verification, and the 55-test result.

### Verdict

Approve; no concrete correctness or security blocker. Reverse reachability encodes the live-dependency invariant, recomputation under `BEGIN IMMEDIATE` closes the safety-relevant time-of-check/time-of-use race, and transactional verification provides strong consistency.

### Non-blocking finding

If CLI/MCP permit confirmation without a digest, recomputation remains safe but can execute a plan different from the one the user believes they reviewed. Claude recommended making preview binding the default and retaining an explicit force option for automation.

### Final reconciliation

The finding was tightened before commit. CLI execution now requires either the prior `--expected-digest` or the deliberate `--force-current` override. MCP likewise requires either `expected_digest` or `force_current=true` whenever `confirm=true`. Supplying both is rejected. Python remains the trusted direct domain API and keeps its optional digest. Confirmation-without-binding tests were added for CLI and MCP.
