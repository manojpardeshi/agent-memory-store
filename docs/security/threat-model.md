# Threat Model

Last reviewed: 2026-07-22
Status: public-release baseline

## System and trust assumptions

LLM Memory Store is a personal, single-user component. It runs as a Python library, CLI, or MCP stdio
server and stores data in a local SQLite database. It does not expose an HTTP listener, authentication
service, daemon, or multi-user authorization boundary. The local OS account, filesystem permissions,
and full-disk encryption are trusted.

The consuming application and MCP host are trusted to request operations for the local user. Recalled
memory, imported artifacts, extraction-model output, and model-generated text are untrusted data even
when they originate on the same machine.

## Assets

- Memory bodies, roles, types, scopes, correction history, and provenance.
- Embeddings and behavioral model identities.
- SQLite databases, WAL/SHM state, exports, backups, proposal bundles, and review reports.
- Queries, prompts, recalled context bundles, and local-model responses.
- Destructive-operation previews, digests, and receipts.

## Trust boundaries and mitigations

| Threat | Boundary and mitigation |
| --- | --- |
| Cross-agent or shared-pool disclosure | Reads use normalized exact-match private scopes and explicitly selected shared pools. Scope-isolation tests are release invariants. |
| Prompt injection through recalled memory | Context bundles label memory as untrusted data and are bounded. Applications must not convert recalled instructions into tool authority. |
| Unreviewed model output becoming durable memory | Extraction produces tamper-evident proposals only. Selected acceptance is explicit, digest-bound, provenance-linked, and source-revalidated. |
| Destructive deletion or stale confirmation | Hard deletion and expiry purge expose previews and verification receipts. CLI/MCP confirmation is bound to reviewed digests or an explicit force-current choice. |
| Arbitrary-file overwrite or export exfiltration | Export, backup, restore, import, and migration require explicit paths and selectors, use owner-only permissions, avoid overwrite by default, and publish new destinations atomically. |
| Embedding-space corruption | Each store is bound to a fingerprinted embedding identity. Migration creates and verifies a distinct destination rather than rewriting the source. |
| Malicious or malformed import/proposal data | Inputs are bounded, schema-validated, hash-checked, cycle-checked, and rejected atomically on unknown or inconsistent state. |
| MCP protocol leakage | The server uses stdio; protocol data goes to stdout and application diagnostics must use stderr without memory bodies. No network transport is enabled. |
| Retention beyond logical expiry | Recall excludes expired data immediately. Physical purge is explicit and refuses to cascade through an unexpired descendant. Backups and filesystem snapshots require separate retention controls. |
| Dependency or model supply-chain compromise | Python and dashboard dependencies are locked with versions and hashes. Embedding identity is behaviorally fingerprinted. Initial package/model downloads still trust their configured registries and TLS path. |
| Local resource exhaustion | Input sizes, proposal counts, nesting, and context bundles are bounded. Personal-scale exact search is measured; hostile multi-tenant workloads are out of scope. |

## Security properties not claimed

- Protection after compromise of the trusted OS account or consuming application.
- Encryption independent of the operating system or full-disk encryption.
- Remote authentication, authorization, rate limiting, or tenant isolation.
- Forensic erasure from SSD media, backups, snapshots, synced copies, or model-provider systems.
- Safety of arbitrary remote Ollama endpoints; supported model calls are loopback-only.
- Automatic semantic detection of contradictions, paraphrase duplicates, or malicious memory content.

## Release verification

Public releases require synthetic end-to-end lifecycle tests, scope and deletion invariants, clean
artifact installation, a full-history/publication-tree privacy scan, dependency and artifact hashes,
and review of any change to logging or trust boundaries. See `docs/architecture/discovery-brief.md`
and `docs/release/privacy-audit-2026-07-22.md`.
