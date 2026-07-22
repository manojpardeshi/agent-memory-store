# Claude Review: Extraction Proposal Boundary

Date: 2026-07-19
Reviewer: Claude Sonnet through Claude CLI, stateless review-only prompts
Scope: proposal lifecycle, untrusted Ollama output, interface exposure, and content identity

## Review outcome

Claude agreed with separating untrusted generation from trusted mutation through a canonical proposal bundle and explicit acceptance. The reviewer recommended per-proposal source validation, deterministic idempotency, fail-closed digest validation, loopback-only Ollama, strict structured output, and no automatic source re-anchoring.

The first review attempts returned tool-call intentions instead of opinions. They are not treated as evidence. The prompts were repeated with all tools disabled and a review-only system instruction; only those direct answers informed this record.

## Advice adopted

- Exclude `created_at`, confidence, and bundle identity from proposal identity.
- Include extractor/schema identity, exact target scope, kind, normalized content, source evidence, and relation in the proposal hash.
- Hash the exact proposal bundle separately so a reviewer confirms the artifact actually accepted.
- Reject deleted, inactive, or content-changed sources and require a fresh extraction instead of fuzzy re-anchoring.
- Make retry acceptance an idempotent success.
- Bound source count, input/output size, proposal count, and content length.
- Treat sources and model output as untrusted data; provide the model no tools or side-effect channel.
- Restrict Ollama to a validated loopback endpoint and reject redirects.
- Test malformed/truncated JSON, invented provenance, excess output, remote endpoints, timeout/model failure, and no partial mutation.
- Require exact digest and explicit confirmation for CLI acceptance.

## Advice modified or deferred

- Claude suggested a database candidate queue. This was rejected for this slice: transient owner-only proposal files provide review without a database migration or new lifecycle state.
- Claude suggested span offsets and span-level staleness as an option. Whole-source hashes are accepted because existing memories are immutable versions and the simpler rule is easier to audit.
- Claude suggested embedding similarity for duplicate detection and semantic conflict detection. These are deferred because the retrieval gate is still red and model-dependent automatic discard could hide valid proposals. V1 rejects exact duplicates within a bundle and otherwise leaves judgment to review.
- Claude suggested MCP extraction and digest-gated acceptance. MCP is deferred entirely for this slice. A digest can be computed or echoed by the same agent, so it is integrity evidence, not proof of human consent.
- Claude suggested source contents or raw model response details in proposal persistence. The accepted contract stores source IDs/hashes and extractor identity but avoids duplicating raw source text or model output.
- Claude suggested a bundle-level idempotency key for the selected set. The implementation uses one operation ID per reproducible proposal ID, allowing later partial acceptance and equivalent re-extraction without duplicating earlier selections while receipts retain the exact bundle digest.

## Major trade-offs recorded

- Strict stale-source rejection favors auditability over incremental convenience.
- External artifacts avoid schema complexity but need caller-managed cleanup.
- Whole-response rejection avoids ambiguous partial validation but may require another model call.
- Deterministic normalization must remain conservative; over-normalization can merge distinct claims.
- Python can only provide an explicit acceptance primitive; the host application owns the actual human-consent experience.

## Implementation gate

The feature may proceed only if tests demonstrate no durable write before acceptance; exact source provenance; idempotent retries; owner-only/no-overwrite artifacts; and fail-closed behavior for tampering, stale sources, invalid output, and non-loopback endpoints.

## Implementation review and resolution

Claude's first two attempts to inspect the working tree with read-only Claude CLI tools returned no text and were not counted as reviews. A no-tools review of the concrete implementation behavior identified three blockers:

- publicly constructible in-memory bundles had to pass the same canonical parser as file artifacts;
- duplicate JSON object keys and pathological nesting had to fail closed on every JSON boundary; and
- deterministic operation-ID replay had to verify extraction metadata in addition to kind, content, scope, and source provenance.

Claude also identified a correction/write time-of-check/time-of-use risk. The implementation now resolves active provenance sources and their generation inside SQLite `BEGIN IMMEDIATE`, so another writer cannot supersede a source between resolution and derived-memory insertion. File reads are bounded, duplicate keys are rejected for artifacts and both Ollama JSON layers, in-memory bundle writes/acceptance reparse canonical identities and digest, and replay verification requires the proposal and extractor audit metadata. New tests cover each finding.

After those changes, Claude's final stateless review returned: **No blocking findings.** It classified symlink races and process-level rate limiting as non-blocking under the accepted single trusted OS-user threat model, because an actor able to exploit them already controls the same filesystem and processes.
