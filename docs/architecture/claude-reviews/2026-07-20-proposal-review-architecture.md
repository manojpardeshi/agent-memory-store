# Claude Review: Deterministic Proposal Review

Date: 2026-07-20
Reviewer: Claude Code CLI through a bounded no-tools prompt

## Availability

The initial repository-reading prompt stalled without output and was stopped. Two bounded attempts
exhausted their turn limits without a response. A smaller no-tools architecture prompt completed and
is the review reconciled below. Failed attempts are not treated as advice.

## Claude recommendation

Claude supported a deterministic, read-only review stage, a total status order, no model or
embedding judge, content-hidden CLI defaults with an explicit reveal flag, and acceptance bound to
the exact proposal digest. It emphasized that review and acceptance must examine the same canonical
artifact and that mutation between them must fail closed.

Claude proposed exact-duplicate, replay, stale-source, structural-collision, and clean statuses. It
also recommended tests for deterministic duplicate/replay classification, changed sources, database
non-mutation, privacy-safe output, and digest mismatch before writes. Those directions are adopted
with the corrections below.

## Reconciliation

Claude placed duplicate and replay ahead of source staleness. The implementation instead retains
independent evidence axes and makes stale sources the primary blocking status. Existing acceptance
requires selected sources to remain active and unchanged, so a duplicate or replay cannot waive that
provenance invariant.

Claude defined replay from a previously adjudicated source tuple, including rejection. The product
does not have a persistent adjudication ledger. Replay is therefore limited to the existing exact
`extract:<proposal_id>` durable operation identity. A structurally mismatched operation record is an
operation collision; a valid accepted record can be active, superseded, or expired.

Claude suggested subset and overlapping-scope collisions. That is rejected because AD-018 defines
scopes as exact and non-hierarchical. The only additional structural indicator is identical normalized
content in the exact target scope under a different memory kind. It is labelled `kind_collision`, not
a semantic contradiction.

Claude suggested acceptance by proposal digest. The existing and stronger contract binds acceptance
to the bundle digest plus explicit proposal IDs and `--yes`; that contract remains unchanged.

## Accepted architectural influence

The final design uses content-hidden defaults, an explicit total primary-status precedence, separate
evidence axes, a reusable preflight before acceptance, and tests proving no review mutation. Claude's
broader semantic and scope claims are not implemented.

## Final implementation review

Claude's adversarial review asked whether redaction is applied to the persisted report and whether
0600 permissions exist from first creation. Both were already satisfied: the redacted report object
is serialized for both stdout and disk, tests inspect the artifact, and `secure_write_text` uses a
0600 temporary file plus atomic no-overwrite publication.

Claude also identified same-batch duplicates and the difference between read-only behavior and a
read-only database handle. The report now cross-indexes exact same-kind normalized content within
the proposal bundle, and CLI review opens SQLite with `mode=ro` plus `query_only=ON`. Exact
duplicates remain acceptance-ready because AD-041 preserves human authority; the system provides
evidence rather than silently rejecting an explicit selection.

Claude suggested stripping zero-width/default-ignorable Unicode. That is not adopted: such code
points can be meaningful in emoji and non-Latin scripts, and uniqueness is not a security or write
authorization boundary. NFC plus Unicode whitespace collapse remains the documented exact
comparison. A future broader canonicalization requires its own multilingual false-positive corpus.
