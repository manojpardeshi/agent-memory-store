# MVP Architecture Contract

Date: 2026-07-19
Status: approved implementation baseline; not yet approved for public release

## Product Boundary

The MVP is a personal, local-first memory service for local LLM applications and agents. One trusted OS user stores at most tens of thousands of memories in one embedded database. It has no server process, network listener, cloud dependency, authentication system, multi-user authorization, document-ingestion pipeline, or UI.

The primary integration is MCP over stdio. A Python API and CLI expose the same core store.

## Integration Starter

The runnable example keeps memory orchestration in application code: recall before inference, bounded and explicitly untrusted context injection, model call, then raw-turn capture after success. Direct Python and MCP stdio clients have normalized deterministic lifecycle parity. Typed writes and corrections require explicit user commands; deletion remains preview/confirm. The optional model adapter is loopback-only Ollama, with deterministic offline CI and separately labelled single-run live evidence.

## Memory Contract

- Types: `turn`, `fact`, `preference`, `summary`, and `event`.
- Scopes: exact-match private application/agent scopes and explicitly named shared pools. Recall never expands scopes implicitly.
- Lifecycle: active memories may be superseded by an appended correction version. Superseded and expired versions are excluded from recall.
- Provenance: source and supersession relationships form a cycle-checked directed acyclic graph.
- Processing: the memory row commits first as `pending`; local embedding completes in a second transaction as `ready` or `failed`. Failed work is retryable.
- Retention: raw turns default to a 30-day TTL. Typed memories have no default TTL.

## Extraction and Summarization Contract

Optional processing is two-phase and application-owned. Exact active source IDs and an exact target scope produce a canonical owner-only JSON proposal artifact outside SQLite. Deterministic offline rules are the test baseline; an optional local generator may call only a validated loopback Ollama endpoint with no tools. Source text and model output are untrusted data.

Extraction performs no durable memory write. The complete response must pass strict kind, content, count, provenance, and identity validation before an artifact is created. Acceptance requires an exact bundle digest plus an explicit non-empty proposal selection; the CLI additionally requires `--yes`. It revalidates each selected source's active/expiry state and content hash before calling the existing typed-memory write path. Proposal identity supplies idempotency across retries and equivalent re-extraction, and accepted memories retain source DAG edges plus extractor metadata.

Python and CLI expose proposal/review/accept operations. MCP is deferred because an agent can calculate or echo a digest without demonstrating human approval. There is no background extractor, candidate database, auto-accept policy, fuzzy source re-anchoring, or automatic semantic duplicate/conflict discard.

## Recall Contract

Recall performs exact cosine KNN independently in each explicitly requested scope, merges the candidates, excludes non-active or expired rows, and combines 80% semantic relevance with 20% recency. Stores bound to the exact certified BGE-small-v1.5 or all-MiniLM-L6-v2 behavioral identities default to a relative semantic-gap of 0.20 and may return zero through the requested limit. Unknown or changed identities default to unfiltered. Python `None`, CLI `--no-relevance-filter`, and MCP `off` explicitly restore legacy unfiltered top-K behavior. The effective transport policy is observable. The default returned context budget is 4,000 characters. Returned content is labelled untrusted memory data and must not be interpreted as instructions.

## Deletion Contract

Deletion requires a preview and explicit confirmation at the CLI/MCP boundary. Deleting a memory removes:

1. every version in its correction lineage; and
2. every recursively derived descendant of those versions.

Deleting a derived memory does not delete its sources. Memory rows, vector rows, and provenance edges are removed transactionally and post-commit absence is verified. SQLite secure deletion, checkpoint, and incremental vacuum reduce residual active-store data, but the MVP does not promise forensic media erasure and cannot erase previously created backups or exports.

Expiry purge is a separate retention operation with narrower authority. One timezone-aware cutoff is captured for preview and execution. A row is purgeable only when it is expired at that cutoff and backward reachability from unexpired correction-lineage or derived descendants does not protect it. Consequently:

- a fully expired lineage or expired derived leaf can be removed;
- an expired source required by an unexpired descendant is retained and reported as blocked; and
- an unexpired source does not block removal of its expired derived child.

CLI and MCP preview by default and require explicit confirmation bound to the preview digest. A deliberately named force-current option permits automation to accept the recomputed set without a prior digest; the Python domain API remains trusted and directly callable. Execution recomputes with the same cutoff under an immediate transaction, atomically removes the safe set, records row/vector/provenance counts, and verifies absence. Empty batches succeed. No background scheduler or forensic-erasure claim is added.

## Portability and Compatibility

- SQLite's online backup API creates restorable live snapshots; restore runs an integrity check, requires explicit CLI confirmation, and only creates a new destination path.
- JSON export v2 is human-readable, preserves operation IDs and verified content hashes, declares out-of-selection provenance, and excludes derived vectors. Python/CLI import accepts v1/v2 only into a new compatible store, regenerates vectors, rejects missing sources by default, and atomically publishes after verification. SQLite backup/restore remains the byte-faithful operational restore mechanism.
- Export requires an explicit exact-scope, subject, or whole-store selector. MCP export/backup are preview-and-confirm operations, and artifact writes refuse overwrite by default.
- A store records the complete embedding identity plus a sentinel-vector behavioral fingerprint. An incompatible runtime refuses to open the store rather than mixing vector spaces.
- Embedding migration validates the source fingerprint, snapshots it, and builds a new owner-only destination in the target space. It preserves the logical graph, re-embeds every active row, verifies structure/vectors/identity and synthetic source-to-target quality, then publishes with an atomic no-clobber operation. Source remains unchanged. Python and CLI expose preview/confirmation; MCP migration is deferred.
- The default model is `BAAI/bge-small-en-v1.5` through FastEmbed. Its first use may download model assets; subsequent operation is local using the model cache.

## Security Boundary

The trusted boundary is the local OS account and machine. Store directories are mode `0700`; database and backup files are mode `0600`. The design relies on filesystem permissions and OS full-disk encryption. Same-account privileged processes, malicious MCP clients, storage forensics, and compromise of the host are outside the MVP protection claim.

## Known Deferrals

- Unattended extraction, managed review queues, and automatic duplicate/conflict decisions.
- Background scheduling and automatic retry.
- Multi-user, remote, or policy-based authorization.
- Broader or personalized evaluation corpora beyond the synthetic retrieval-v1 gate.

These deferrals are release-planning inputs, not implicit architecture promises.
