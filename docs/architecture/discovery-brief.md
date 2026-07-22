# Architecture Discovery Brief

## Status

Discovery is substantially complete for the product boundary. No detailed solution architecture has been approved. High-level constraints are accepted; component selection, schema, APIs, and retrieval behavior remain to be evaluated.

Last updated: 2026-07-15

## Problem Statement

LLM applications and agents are stateless across sessions and silo memory by provider. The product is a personal, local-first memory layer that lets different LLM applications on one trusted machine reuse durable context without depending on any provider's proprietary memory feature.

Expected value:

- Continuity across sessions.
- Personalization based on prior facts and preferences.
- Less repeated context in prompts.
- Portability across chat-model providers and machines.

## Users and Stakeholders

One person fills every role:

| Role | Responsibility |
| --- | --- |
| End user and data subject | Supplies the preferences, history, and context being remembered. |
| Integrator | Connects personal agents and applications to the memory server. |
| Operator | Starts, upgrades, backs up, restores, inspects, and troubleshoots the local store. |
| Product owner | Prioritizes features and accepts trade-offs. |

There are no external tenants, purchasers, governance teams, or support operators in v1.

## Functional Requirements

Requirement terms use **must**, **should**, and **may** intentionally.

### Memory Model

The system must store typed memories rather than treating all content identically.

| Class | v1 behavior |
| --- | --- |
| Episodic | Raw messages/turns with a configurable short TTL. |
| Semantic | Extracted facts and entities, with provenance. |
| Preference | Long-lived user preferences, with provenance and correction history. |
| Summary | Rolling summaries derived from sessions or other memories. |
| Tool result/event | Optional in v1; only salient results should be stored. |
| Document | Reference a local file or URL; do not ingest or own the document corpus. |
| Procedural | Out of scope for v1. |

Every derived memory must retain provenance sufficient to identify its source turn or event and extraction method/version.

### Commit

- The caller must be able to persist a raw turn synchronously.
- An acknowledged commit must survive a normal process restart.
- Fact extraction, summarization, and embedding must be pluggable.
- Derived processing may be synchronous or explicitly invoked later; it must not require an always-running daemon or remote LLM.
- Upsert behavior must be deterministic and idempotent for a caller-supplied operation ID.
- Failures in optional derived processing must not silently discard the committed raw turn.

### Recall

- The caller supplies a query and an explicit scope.
- Recall must support semantic similarity and recency as ranking signals.
- Recall must filter by scope before returning content.
- Results must be returned as a small, provider-neutral context bundle containing plain text and metadata.
- The consuming application, not the memory store, is responsible for provider-specific prompt rendering.
- Results should expose score components and provenance so retrieval can be debugged.
- Expired, deleted, or superseded memories must not be returned by default.

### Correct and Forget

- A memory can be corrected by creating a new version that supersedes the old version.
- Superseded versions retain provenance for inspection but are excluded from normal recall.
- The caller can hard-delete a memory, subject, scope, or test dataset.
- Hard deletion must remove both row data and associated vector entries in one logical operation.
- Deletion must be idempotent and return enough information to verify its effect.
- The exact interaction between hard deletion and retained correction history remains open; see OQ-005.

### Export and Inspection

- The caller can export a subject or scope as versioned JSON, including provenance and embedding-model metadata.
- A minimal CLI or inspector must support list, inspect, export, delete, backup, restore, and health/version operations.
- A full graphical UI is out of scope.

## Scope and Isolation

Each memory must carry an explicit scope with these axes:

- `subject`: whose memory it is.
- `agent_or_app`: the private agent/application namespace.
- `environment`: for example, development, test, or personal production.
- `shared_scope`: optional, explicit membership in a pool readable by more than one agent/application.

Private agent/application scope is the default. Sharing is opt-in. The organization/tenant axis is intentionally absent in v1.

The exact wildcard, inheritance, and shared-scope authorization semantics must be specified before schema or API approval.

## Scale and Performance

| Dimension | v1 target |
| --- | --- |
| Human users | 1 |
| Agents/applications | A handful |
| Read/write rate | Single digits per minute during active use |
| Stored records | Low thousands initially; tens of thousands over years |
| Embedding dimension | Approximately 384 for the initial model; final choice open |
| Recall latency | p95 under 200 ms on the reference machine |
| Database size | Expected to remain in the MB-to-low-hundreds-of-MB range |

At 384 float32 dimensions, 20,000 raw vectors occupy about 30.7 MB before table, text, index, and database overhead. The complete-file size must be measured rather than assumed to stay below 100 MB.

There is no requirement for sharding, queues, replication, distributed coordination, or horizontal scaling.

## Reliability, Backup, and Recovery

- Availability means the stdio server starts on demand when a client starts it.
- A successfully acknowledged database transaction must not be lost after a normal restart.
- No point-in-time recovery or replicated failover is required.
- RPO equals the last successful snapshot.
- RTO is the time to replace the database with a validated snapshot and restart the process.
- Backup must produce one portable, internally consistent artifact.
- Copying a live SQLite main file directly is not guaranteed to include a consistent WAL state. The supported backup operation must either stop/checkpoint the database or use a database-aware snapshot mechanism such as SQLite's backup API or `VACUUM INTO`.
- Restore must validate schema version, integrity, and embedding-model compatibility before serving recall.

## Security, Privacy, and Trust

### Threat Model

The v1 trust boundary is the local operating-system user account on one trusted machine.

- Filesystem permissions and full-disk encryption are the primary controls.
- MCP stdio is the only v1 transport, so there is no network listener and no transport authentication.
- Application-level at-rest encryption, customer-managed keys, formal audit controls, data residency controls, and compliance certification are out of scope.
- If a network transport is introduced later, its authentication, authorization, encryption, origin exposure, and rate limits require a new threat model and architecture decision.

### LLM-Specific Safety

Local data is not automatically trusted content. A memory may contain prior prompt injection, inaccurate extraction, stale facts, or malicious text copied from a tool result.

- Provenance and memory type must be included in recall metadata.
- Recalled text must be treated as data, not executable instructions.
- Tool results and external content should not be promoted to durable facts without an explicit extraction/validation policy.
- Memory writes must have size limits and validated structured metadata.
- The evaluation set must include poisoned, stale, and conflicting-memory cases.

### Deletion and Portability

- Hard-delete and JSON export are required for personal control, testing, and migration.
- Basic personally identifiable information may be stored because the operator and subject are the same person.
- Logs must not contain full memory bodies or embeddings by default.

## Lifecycle

- Retention is configurable by memory class.
- Raw turns default to a short TTL; facts and preferences may be long-lived.
- A pin/no-expire flag may be included if it does not complicate deletion semantics.
- Expiration and optional recency decay are separate: expiration controls eligibility, while decay affects rank.
- Corrections create a superseding version rather than silently overwriting history.
- Expired records may be lazily excluded and later physically purged; no background daemon is required.
- Export format and database schema both require explicit versions and migrations.

## Delivery and Technology Constraints

- Personal, greenfield project maintained by one developer.
- Python is the implementation language.
- Primary integration surface is an MCP server over stdio.
- A thin in-process Python API/SDK is required for direct use and testing.
- No HTTP transport, cloud service, paid API, authentication server, or always-on process in v1.
- Embeddings must run locally and be hidden behind a swappable interface.
- A store has one active embedding model/version/vector dimension at a time. Re-embedding must be explicit; vectors from incompatible models must never be compared.
- The datastore must be embedded and portable. A server-based PostgreSQL deployment is out of scope for v1.
- Prefer permissive MIT, Apache, or BSD dependencies.
- Target recurring infrastructure cost is approximately zero.
- Prototype target is a few weekends; usable MVP target is a few weeks, with no fixed external deadline.

## Source Publication and Distribution

The project will use a staged open-source publication model:

1. Develop privately through the first end-to-end security and packaging milestone.
2. Review and sanitize the complete repository and Git history.
3. Publish the canonical public repository on Codeberg under a permissive open-source license.
4. Distribute installable Python releases through PyPI.
5. Optionally maintain a read-only GitHub mirror for discovery; Codeberg remains authoritative for source, issues, and contribution workflow.

Public and private artifacts have a strict boundary:

| Public project artifacts | Private/local artifacts |
| --- | --- |
| Source code, schemas, migrations, MCP definitions, CLI, and Python API | Personal memory database files and snapshots |
| Architecture and user documentation | Real memory exports and personal evaluation cases |
| Synthetic fixtures and reproducible tests | Logs containing personal content or machine details |
| Public evaluation harness and synthetic benchmark cases | Local configuration, credentials, and environment files |
| Release metadata and checksums | Downloaded model caches unless redistribution is explicitly permitted |

The public project must not require GitHub-specific APIs or workflows. CI and release automation should remain portable across Codeberg/Forgejo-compatible runners and local execution.

The exact permissive license remains an open decision. Candidate licenses are Apache-2.0 and MIT; dependency compatibility and the desired patent grant must be reviewed before selection.

## Dependency Status Verified on 2026-07-10

- `sqlite-vec` is an active successor to `sqlite-vss`, implemented in C with Python bindings and MIT/Apache-2.0 licensing.
- Its stable release line remains pre-v1 and explicitly warns that breaking changes should be expected.
- Exact KNN search is available; newer approximate-index work is alpha/experimental and unnecessary at the target scale.
- The official MCP Python SDK supports stdio clients and servers.

Consequences: `sqlite-vec` is a credible candidate, not yet a final choice. The data layer must isolate extension-specific SQL, pin a tested version, and provide migration/export tests.

## Success Criteria

### North Star

On a small, versioned personal evaluation set, memory-enabled agents improve task completion or answer quality over the same agents without memory.

### MVP Acceptance Measures

| Measure | Proposed acceptance condition | Status |
| --- | --- | --- |
| Cross-model portability | The same stored memories improve at least two different chat-model families on the evaluation set. | Informational live evidence passes; repeatability threshold remains future work |
| Retrieval usefulness | Recall@5 ≥ 0.90, MRR ≥ 0.85, designated distractor leak ≤ 0.10, and zero scope violations on retrieval-v1. | Gate defined; first baseline fails distractor leakage |
| Forget correctness | Deleted memories and vectors are absent from recall, direct inspection, and export. | Required, deterministic test |
| Correction correctness | Superseded values are excluded from normal recall and the active version is traceable to provenance. | Required, deterministic test |
| Isolation correctness | Private memories never appear outside their exact permitted scope; shared memories appear only in declared scopes. | Required, deterministic test |
| Latency | Recall p95 is under 200 ms on the named reference machine and representative dataset. | Target accepted; benchmark fixture open |
| Durability | An acknowledged write survives process restart and database integrity validation. | Required, deterministic test |
| Portability | Export/import and backup/restore round trips preserve all supported logical content. | Required, deterministic test |
| Cost | Core commit and recall operate offline with no paid API or recurring infrastructure. | Required |

Continued personal use is a useful product signal but is not sufficient as the only acceptance test.

## Non-Goals for v1

- Document ingestion or a general RAG knowledge base.
- Fine-tuning or training models from memory.
- Multi-user, multi-tenant, cloud-hosted, or networked deployment.
- Paid or custom embedding models.
- Procedural memory.
- Distributed scaling, queues, replication, or background daemons.
- Sophisticated automatic conflict resolution beyond explicit versioning and a simple deterministic active-version rule.
- Full UI, formal compliance program, application-level encryption, or authentication service.

## Assumption Register

| ID | Assumption | Impact if wrong | Validation | Status |
| --- | --- | --- | --- | --- |
| A-001 | The product is a reusable, model-agnostic memory store for local LLM applications and agents. | Product scope changes substantially. | Confirmed by product owner. | Confirmed |
| A-002 | The project is greenfield with no existing system or infrastructure to preserve. | Hidden integration or migration work would change design. | Confirmed by product owner. | Confirmed |
| A-003 | The local OS account and machine are trusted; other local processes with the same privileges are outside the v1 threat model. | Filesystem-only controls would be inadequate. | Revisit before sharing the machine/account or adding network access. | Confirmed for v1 |
| A-004 | Exact vector search over at most tens of thousands of records can satisfy the 200 ms p95 target on the reference machine. | An ANN index or different storage path may be needed. | Re-run the benchmark if scale or dimensions change materially. | Confirmed: 12.98 ms p95 at 20,000 x 384 dimensions |
| A-005 | One embedding space per store is acceptable; model changes can trigger an explicit migration/re-embedding operation. | Multiple vector spaces or live dual-read migration would be needed. | Design the migration command before changing the default model. | Confirmed for MVP |
| A-006 | Lazy expiration/purge is sufficient without a scheduler. | Expired data could remain on disk longer than desired. | Confirm physical purge timing expectations. | Proposed |
| A-007 | Typed memory creation can be caller-driven in the MVP; automatic extraction is not required for the first useful workflow. | A local extractor or resumable work queue may be needed. | Validate usefulness with real personal workflows. | Accepted for MVP |

## Major Trade-offs

| Trade-off | Current direction | Benefit | Cost/risk | Status |
| --- | --- | --- | --- | --- |
| Embedded versus server database | Embedded, single-file | No service operations; portable and cheap | Single-writer constraints; extension/migration considerations | Accepted boundary |
| SQLite built-in scan versus `sqlite-vec` | `sqlite-vec`, isolated behind the store API | Vector types, partitioned KNN, compact implementation, future headroom | Pre-v1 dependency and migration risk | Accepted after benchmark and integration tests |
| Exact KNN versus ANN | Exact KNN | Deterministic, simple, appropriate for personal scale | Query cost grows linearly | Accepted after 20,000-vector benchmark |
| Raw history versus derived memory | Store short-lived raw turns plus selected derived types | Traceability and continuity without retaining everything forever | Extraction errors, duplication, lifecycle complexity | Accepted product direction |
| Sync versus deferred derivation | Raw write synchronous; derivation pluggable and optionally deferred | Acknowledged source data is safe; no mandatory daemon | Deferred work needs explicit state/retry behavior | Accepted direction; mechanics open |
| Versioned correction versus overwrite | Versioned supersede | Debuggable provenance and historical understanding | More schema and deletion complexity | Accepted |
| Strong transaction versus partial commit | Memory row commits first; vector completes in a second visible transaction | Preserves source writes when inference fails | Callers must understand `pending` and `failed` states | Accepted |
| Private versus shared scope | Private default, explicit shared pools | Minimizes accidental cross-agent recall | Scope semantics and tests are more complex | Accepted |
| One embedding space versus multiple | One active, fingerprinted embedding identity per store | Comparable vectors and simpler ranking | Model upgrades require re-embedding/migration | Accepted for MVP |
| App encryption versus OS protection | OS permissions/full-disk encryption | Minimal complexity and key management | Database is readable by same-account processes and exposed if disk controls fail | Accepted for v1 |
| stdio versus HTTP | MCP stdio only | No listener/auth/control plane | Only local process-spawn integrations | Accepted for v1 |

## Open Questions Before Architecture Approval

| ID | Question | Why it matters |
| --- | --- | --- |
| OQ-001 | What exact reference machine and dataset define the 200 ms benchmark? | Performance claims need a reproducible fixture. |
| OQ-002 | Resolved for MVP: `BAAI/bge-small-en-v1.5` through FastEmbed, with a behavioral compatibility fingerprint. | A future model change requires an explicit re-embedding workflow. |
| OQ-003 | Resolved for MVP: callers submit typed memories; automatic LLM extraction is deferred. | Keeps the MVP deterministic and avoids a second model dependency. |
| OQ-004 | Resolved for MVP: exact private scopes plus explicitly named shared pools; no wildcard or hierarchical reads. | Prevents implicit cross-agent recall. |
| OQ-005 | Resolved for MVP: delete the selected correction lineage and recursively derived descendants; never delete sources merely because a derived memory is deleted. | Defines an executable and previewable deletion boundary. |
| OQ-006 | Partly resolved: raw turns default to 30 days; typed memories are long-lived; expired records are hidden lazily. Physical purge timing remains open. | The MVP does not claim forensic erasure of expired bytes. |
| OQ-007 | Resolved: the CLI uses SQLite's online backup API and verifies restored database integrity. | Live snapshots are safe without copying WAL state manually. |
| OQ-008 | Resolved for MVP defaults: 4,000-character bundle; 80% semantic plus 20% recency with a 30-day half-life. | Retrieval-quality evaluation may change these defaults. |
| OQ-009 | Resolved for retrieval-v1: Recall@5 ≥ 0.90, MRR ≥ 0.85, designated distractor leak ≤ 0.10, zero scope violations, and runtime ≤ 60 seconds on a 50-query synthetic corpus. | The first FastEmbed baseline passes recall, rank, scope, and runtime checks but fails distractor leakage at 0.24, so the quality gate remains closed. |

## Architecture Gate

The architecture baseline is approved for MVP implementation. Scope and deletion semantics are covered by executable tests; datastore, vector search, MCP, real-model inference, and backup/restore spikes pass. OQ-009 now has a versioned fixture and numeric contract, but the first baseline fails its distractor-leak threshold, so product-release approval remains closed. Physical expiry purge and automated extraction are documented post-MVP decisions, not hidden assumptions.

## Public Release Gate

The repository must remain private until all of the following are true:

1. End-to-end commit, recall, correction, hard-delete, export, and backup/restore tests pass using synthetic data.
2. `.gitignore` excludes environment files, credentials, databases, SQLite WAL/SHM files, exports, backups, logs, model caches, and machine-local configuration.
3. The entire Git history has been scanned for credentials, personal memories, local attachment paths, and other sensitive data.
4. Default logging excludes memory bodies, embeddings, prompts, and secrets.
5. Synthetic fixtures contain no transformed or pseudonymized personal memories.
6. The license, `SECURITY.md`, contribution policy, threat model, and support expectations are published.
7. Installation and offline operation are reproducible on a clean reference machine.
8. Release artifacts and dependencies have machine-readable versions and checksums.
9. If repository history cannot be confidently sanitized, publication starts from a new clean repository rather than changing the existing repository's visibility.
