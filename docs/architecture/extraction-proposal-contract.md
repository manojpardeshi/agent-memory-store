# Extraction Proposal Contract

Last updated: 2026-07-19
Status: accepted for the first implementation slice

## Outcome

Optional extraction and summarization may turn explicitly selected, active memories into reviewable typed-memory proposals. Extraction never writes a memory. A separate acceptance operation writes only the proposal IDs selected by the caller after validating the proposal artifact and its sources again.

This is application-owned processing, not a daemon, queue, or autonomous agent behavior. Failure cannot change or remove a source memory.

## Users and scale

- One trusted person on one trusted local machine.
- Python applications and terminal users are the first consumers.
- At most 20 explicitly selected sources, 50 proposals, 40,000 source characters, and 2,000 characters per proposed memory.
- Deterministic offline extraction is the required test path. Loopback Ollama is optional evidence.

## Proposal workflow

1. The caller supplies exact active source memory IDs and an exact target `Scope`.
2. The extractor receives bounded source content marked as untrusted data.
3. The complete model response is parsed and strictly validated before any proposal artifact is written.
4. A canonical, tamper-evident JSON bundle is written as a new owner-only file. It is not a database record and has no durable-memory authority.
5. Review is read-only and displays proposal content, type, provenance, and bundle digest.
6. Acceptance requires the artifact, its digest, and an explicit non-empty selection of proposal IDs. CLI execution additionally requires `--yes`.
7. Acceptance revalidates the artifact, checks each selected source is still active with the recorded content hash, and creates the selected typed memories through the existing store transaction path.

## Canonical identity

Canonical JSON uses UTF-8, Unicode NFC strings, sorted object keys, compact separators, and sorted unique source IDs. Semantic content is trimmed and internal whitespace is collapsed; letter case is preserved because it can carry meaning.

A proposal identity is SHA-256 of these identity fields:

- proposal schema version;
- extractor provider, model, revision, and prompt version;
- exact target scope;
- memory kind, normalized content, sorted source IDs, and provenance relation.

The proposal ID excludes generation time, confidence, raw response, and bundle ID. Re-running the same extractor contract over the same evidence and result therefore has the same identity.

The bundle digest is SHA-256 of the canonical bundle body excluding only `bundle_digest`. The body includes schema version, extractor identity, target scope, source IDs and content hashes, proposals, and creation time. The digest consequently identifies the exact review artifact, while proposal identity remains reproducible across equivalent runs.

Edits are not in-place mutations. A reviewer who wants different kind, content, scope, relation, or sources must create a new validated proposal bundle. This keeps the accepted memory tied to exactly what was reviewed.

## Bundle fields

- `schema_version`
- `created_at`
- `extractor`: `provider`, `model`, `revision`, `prompt_version`
- `target_scope`
- `sources`: ordered objects containing `memory_id`, `content_sha256`, `kind`, and `role`
- `proposals`: ordered objects containing `proposal_id`, `kind`, `content`, `source_memory_ids`, `source_relation`, and optional `confidence`
- `bundle_digest`

Raw source contents and raw model responses are intentionally not copied into the artifact. Reviewers can inspect sources in the authoritative store by ID. This reduces sensitive-data duplication and prevents an unverifiable raw response from becoming a second source of truth.

## Validation and failure semantics

- Kinds are limited to `fact`, `preference`, `summary`, and `event`; raw `turn` is never proposed.
- Content, array, source-count, and response-byte limits are checked before acceptance.
- Ollama uses its cross-version JSON output mode with the complete schema supplied in the prompt; deterministic local validation, not the model runtime, is the authority. Unknown fields, missing fields, duplicate proposals, duplicate source IDs, non-finite confidence, and hallucinated source IDs reject the whole extraction response.
- Every proposal must cite at least one selected source. `summary` uses `summarizes`; other kinds use `derived_from`.
- Source text is delimited and labelled untrusted. The extraction model has no tools, file paths, database handle, or shell capability.
- An HTTP Ollama endpoint must be unauthenticated loopback with no path, query, fragment, credentials, or redirects.
- Network, timeout, invalid JSON, invalid schema, excess output, or model errors produce no artifact and no database mutation.
- Acceptance checks the expected bundle digest and re-parses canonical identities. A changed artifact is rejected.
- A deleted, expired, or superseded source rejects that selected proposal. No fuzzy re-anchoring is attempted; the caller must extract again. An unselected stale proposal does not block an otherwise valid selected proposal.
- All selected proposals are preflighted before the first write. Acceptance is failure-atomic for validation. Embedding failures retain the existing store guarantee: the raw typed memory remains authoritative with failed/pending processing state.

## Idempotency and receipt

Each durable write uses a deterministic operation ID derived from the reproducible proposal ID. Replaying the same acceptance or accepting the same proposal from an equivalent later bundle returns the same memory ID. Selecting additional proposal IDs later is allowed and does not duplicate earlier selections. The receipt still records the exact accepted bundle digest.

The acceptance receipt records the bundle digest, selected proposal IDs, resulting memory IDs, replay status, acceptance time, and verification that every result is active and has the expected type, content, target scope, and source IDs. Receipts are returned to the caller; the proposal artifact plus stored provenance remain the durable audit trail.

## Interfaces

- Python: generate/load/review/accept functions are exposed.
- CLI: `propose-extraction`, `review-proposals`, and `accept-proposals`; acceptance requires `--yes`, `--expected-digest`, and at least one `--proposal-id`.
- MCP: deferred. An agent can compute or echo a digest, so digest confirmation alone does not prove human consent. A future MCP workflow needs a trusted host-mediated approval token or an equally strong consent boundary.

## Security and privacy

Proposal artifacts are sensitive and are created with owner-only permissions and no overwrite by default. The database and OS user remain the trust boundary. Memory and proposal text are untrusted model input/data and must never be interpreted as instructions by consuming applications.

## Success criteria

- Deterministic extraction creates useful typed proposals with zero memory writes before acceptance.
- Selected acceptance preserves exact provenance and is idempotent.
- Tampered bundles, stale sources, malformed model output, and remote Ollama endpoints fail closed without partial writes.
- CLI and Python behavior are covered by deterministic tests.
- An optional labelled `llama3.1:8b` run proves the real loopback adapter can produce a validated proposal; it is evidence, not a quality guarantee.

## Trade-offs and assumptions

- Whole-source hashing is stricter and simpler than span re-anchoring; harmless source changes require re-extraction.
- Proposal files avoid a schema migration and review queue, but the product does not manage their retention or lifecycle.
- Exact normalized-content deduplication is deterministic. Embedding-based near-duplicate/conflict decisions remain deferred: the retrieval default is certified for two identities, but no extraction-quality evidence yet justifies automatic discard or conflict resolution.
- Strict whole-response rejection sacrifices partial salvage for an auditable, deterministic boundary.
- Human review is enforced in the provided CLI, while a Python host remains responsible for its own consent UI.
