# JSON Import and Format Migration Contract

Date: 2026-07-19
Status: accepted implementation baseline

## Users and outcome

The user is the one trusted owner moving a human-readable memory export into a new local SQLite store, or a developer using the Python API. Import creates a new compatible database with preserved public identity, lifecycle, scopes, metadata, and provenance, and regenerated local vectors. It does not merge into or overwrite an existing store.

## Export format v2

Format v2 adds `operation_id` and `content_hash` to each memory. The content hash is SHA-256 over exact UTF-8 content only—not metadata—and is verified on import. Public memory IDs, lineage IDs, versions, roles, statuses, generations, timestamps, expiry, metadata, supersession, and source IDs remain explicit. Vectors remain excluded.

An export includes only provenance edges whose child and source are both selected. An edge from an exported child to an unselected source is recorded separately in `external_source_references`, including child ID, source ID, relation, source content hash, and source generation. Export never widens a requested scope implicitly.

## Format migration

Importer accepts format versions 1 and 2 and converts them into one canonical representation before any database is created.

- v2 hashes are verified and operation IDs are preserved.
- v1 hashes are computed from content and the report marks them as backfilled.
- v1 operation IDs remain `null` and the report marks them as irrecoverably absent. Inventing an operation identifier would create false provenance and can violate uniqueness.
- Unsupported versions and unknown required shapes fail closed.

The resulting store exports v2. Therefore a v1 → store → v2 round trip is a declared schema migration, not a byte-identical reproduction of the older document.

## Validation and collision policy

Before execution, the complete JSON is validated with bounded file, record, string, metadata, and graph sizes. Import rejects:

- duplicate memory IDs, duplicate lineage/version pairs, or duplicate non-null operation IDs;
- content-hash mismatches;
- invalid types, roles, scopes, timestamps, statuses, or metadata;
- lineages without exactly one active highest version, non-contiguous versions, or invalid supersession chains;
- provenance edges with missing children or undeclared missing sources;
- mismatches between per-memory source IDs and provenance entries;
- cycles or a child generation other than one plus the maximum source generation; and
- an export manifest incompatible with the selected local embedder.

IDs are never remapped. A fresh destination removes legitimate existing-store collision cases; conflicts inside the document are corruption and fail.

## Missing-source policy

A self-contained document imports losslessly. If `external_source_references` is non-empty, preview reports the affected children and default execution refuses publication. An explicit `allow_missing_sources` option may import the selected memories while omitting those unrepresentable edges. The receipt records every dropped reference and marks the import as provenance-loss accepted. No tombstone or dangling foreign key is fabricated.

Dependency-closure export and provenance tombstones remain separate future choices because either can widen disclosure or require a schema migration.

## Preview and execution

Preview is read-only and returns the resolved input/destination paths, exact file SHA-256, format migration, counts, source manifest, target identity, self-containment status, warnings, and a digest binding all choices. CLI execution requires that digest unless the user deliberately forces the current file. Python is a trusted direct API. MCP import is deferred because untrusted input paths and long embedding work should not be agent-triggered.

Execution reparses and revalidates the exact file, creates an owner-only temporary store beneath the destination directory (therefore on the same filesystem), inserts the canonical logical graph, regenerates all active vectors in bounded batches with CLI progress on stderr, verifies logical equivalence, target identity, vector completeness, and SQLite integrity, and atomically publishes with a no-clobber hard link. Destination must not exist. Any handled failure or interruption removes temporary artifacts and publishes nothing; import is rerun rather than resumed.

## Scale, security, and success criteria

- Maximum input: 100 MiB, 100,000 memories, 500,000 provenance references, and existing per-memory content/metadata limits.
- Database and report artifacts are `0600`; created parent directories are `0700`.
- Imported content and metadata are treated as untrusted data and are never executed or placed in model prompts during import.
- Source JSON is never modified; existing destinations are never overwritten.
- A v2 whole-store round trip preserves all logical fields including operation-ID idempotency.
- Tests must cover v2 round trip, v1 migration report, duplicate/collision rejection, hash tampering, cycles/generation, external-source default rejection and explicit loss, embedding failure, permissions, stale preview, concurrent destination creation, and cleanup.

## Trade-offs and deferrals

- Fresh-store-only import is less convenient than merge, but avoids ambiguous ID, operation, scope, and lineage conflicts.
- Strict self-containment preserves provenance by default; the explicit loss flag supports intentionally partial archives without pretending they are lossless.
- Regenerating vectors costs time but prevents incompatible or tampered vector reuse. Import requires the target behavioral identity to match the export manifest, so changing models belongs to the separately quality-gated embedding migration workflow.
- JSON is the human-readable interchange format; SQLite backup remains the byte-faithful operational restore mechanism.
- Merge import, dependency closure, tombstones, streaming JSON, remote files, and MCP execution are deferred.
