# Claude Review: JSON Import and Format Migration

Date: 2026-07-19

## Questions sent to Claude

Claude was asked to assess export-v2 fields and v1 migration, provenance behavior for partial exports, graph/collision validation, and safe product surfaces for importing untrusted JSON.

## Claude response

Claude recommended adding operation IDs and content hashes, verifying hashes, preserving public IDs, regenerating rather than trusting vectors, and checking the target embedder against the source manifest. It recommended an explicit missing-source policy rather than either silently broadening scope or silently losing provenance. It called for DAG, generation, correction-lineage, duplicate-ID, and dangling-edge validation.

For execution, Claude recommended Python and CLI while deferring MCP, binding confirmation to the exact file hash, using bounded input sizes, creating only a new destination, building in an owner-only temporary location, and atomically publishing after verification. It recommended excluding existing-store merge from the MVP.

## Reconciliation

The accepted design makes two stricter choices:

1. v1 operation IDs remain null and are reported missing. Synthesizing them would claim write provenance that the document does not contain and a single batch value would violate uniqueness.
2. Non-self-contained import rejects by default. `allow_missing_sources` is an explicit provenance-loss override recorded in the receipt. The current relational schema cannot retain a dangling reference, while dependency closure could disclose data outside the selected scope.

IDs are never remapped because import only targets a nonexistent database. Internal duplicates are treated as corruption. Format v2 records external source hash and generation so preview is auditable and generation validation remains possible. The complete accepted design is in `docs/architecture/json-import-contract.md`.

## Implementation review and reconciliation

Claude reviewed the completed v2 exporter, v1/v2 canonical validator, atomic importer, CLI, and 69-test evidence and returned **Ship** with no blockers. It asked to verify same-filesystem hard-link publication, clarify embedding drift and content-hash scope, and consider progress/interruption behavior at the 100,000-memory bound.

The temporary database is created under the destination directory, guaranteeing the same mount under normal filesystem semantics; an explicit cross-device diagnostic was added defensively. The contract now states that hashes cover exact UTF-8 content only, that import requires the export's behavioral embedding identity, and that model changes use the separate migration workflow. Batch progress is emitted to stderr, while interruption unwinds the owner-only temporary directory and publishes nothing; retry starts fresh.
