# Embedding Migration Contract

Date: 2026-07-19
Status: accepted implementation baseline; quality policy remains evidence-bound

## Users and outcome

The operator is the one trusted owner of a local memory store, or a developer invoking the Python API. The outcome is a new SQLite store containing the same logical memories, scopes, lifecycle history, operation IDs, and provenance, but with every active memory embedded in one newly fingerprinted target space. The source is the rollback artifact and is never modified.

## Scale and constraints

- One local OS user, single-writer operation, at most 50,000 memories.
- Local embedders only; no cloud service, remote model call, daemon, or network listener.
- Source and destination are explicit paths. Destination must not exist and must differ from source.
- The caller must supply an embedder that exactly matches the source manifest and a distinct target embedder.
- Public memory and lineage IDs, timestamps, content, hashes, statuses, scopes, metadata, operation IDs, supersession links, and provenance relations are preserved.
- Vectors and active-row embedding processing state are regenerated. Vector bytes and the store ID are intentionally different.

## Preview and execution

Preview opens and validates the source, computes both embedding identities, loads the versioned synthetic quality dataset, and reports source/destination paths, memory/active/vector workload counts, logical source digest, dataset digest, and whether the destination is available. It creates no destination.

CLI execution is bound to the preview digest unless the operator explicitly accepts the current recomputed plan. Python is a trusted direct API. MCP is deferred: model migration is long-running, resource-intensive, and path-sensitive, so an agent-triggered execute tool would add prompt-injection, arbitrary-path, and denial-of-service risk without improving the personal workflow.

Execution first creates a consistent short-lived source snapshot, then recomputes the logical digest from that stable snapshot. It builds an owner-only temporary destination on the destination filesystem, copies the logical graph, embeds active rows in bounded batches, and verifies the result before atomic non-clobber publication. Publication uses same-filesystem hard-link creation, which fails atomically if another process created the destination after preview; the temporary name is then removed. The source stays available and writable after the short snapshot operation; model inference never holds its write lock. Any handled failure removes temporary databases and sidecars. Existing destinations are never overwritten.

## Structural success criteria

- Source and destination logical digests match when embedding state is excluded.
- Source digest and source file remain unchanged by migration.
- Destination manifest exactly matches the target behavioral identity and dimension.
- Every active row is `ready` with exactly one target vector; there are no orphan or missing vectors.
- Scope, correction, operation-ID, and provenance invariants are preserved.
- `PRAGMA integrity_check` is `ok`; database and report artifacts are owner-only.
- The receipt records source/target identities, digests, counts, timing, and verification results.

## Quality policy

The same versioned synthetic corpus is evaluated with both source and target embedders on the unchanged default path and with the explicit relative-gap 0.20 candidate. These measurements validate embedding behavior, not the private memories being migrated.

Two conclusions remain separate:

1. **Absolute product gate:** report each run against the corpus thresholds. The current source default is red and must remain labelled red; migration cannot launder it into a passing claim.
2. **Source-to-target regression gate:** by default, target recall and MRR may not decrease, distractor leakage may not increase, and scope violations must remain zero, on either retrieval configuration. Runtime is reported but not compared as a quality metric.

A regression blocks destination publication by default but still produces the quality report. A deliberately named override may publish the structurally valid target only with a written reason; the receipt records the reason, time, metrics, and trusted-local-user boundary. An absolute-gate failure alone is non-blocking while the accepted source baseline is already red.

## Security and failure boundaries

- CLI preview is non-writing; confirmation is explicit and digest-bound by default.
- Temporary files and the final database use mode `0600`; parent directories use `0700` where created.
- Source contents never enter prompts or quality fixtures. Evaluation uses synthetic data only.
- No overwrite, in-place vector rewrite, partial destination, or silent target-model substitution is permitted.
- The operation does not provide forensic erasure; failed temporary artifacts are unlinked but SSD snapshots and filesystem backups remain outside the claim.
- Migration is not resumable after process or machine failure. A retry starts from a fresh preview and snapshot. A hard crash may leave an owner-only hidden working directory that can be inspected and removed manually; it is never treated as a valid destination.

## Options and trade-offs

- **In-place re-embedding:** rejected because failure could leave mixed or incomplete vector state and destroys the immediate rollback path.
- **Direct source-to-destination copy during inference:** rejected because long model calls would hold a source snapshot or writer lock.
- **Snapshot plus temporary destination:** accepted; it adds temporary disk use but isolates source concurrency and permits atomic publication.
- **Absolute quality gate as publication blocker:** rejected for now because the accepted source default already fails it; this would make all migrations impossible or misstate the baseline.
- **Regression report only:** rejected as the default because it could silently publish a worse target. Explicit override preserves owner agency without weakening the default.
- **MCP execution:** deferred until a stronger out-of-band consent and path policy exists.

## Revisit triggers

Revisit for multiple users, more than 50,000 memories, remote embedders, insufficient free disk, schema-version migration, concurrent writers, accepted tombstones, or evidence that the synthetic regression gate does not predict useful migration outcomes.
