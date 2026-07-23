# Product Roadmap

Last updated: 2026-07-23
Status: active; ordered by dependency and risk

## Product direction

Improve the private, personal-scale memory store through small independently shippable slices. Preserve the local/offline core, exact scope isolation, explicit destructive-operation confirmation, and model-neutral storage contract. Each retrieval-affecting enhancement must pass the retrieval-quality gate before it can ship.

## Ordered enhancements

| Order | Enhancement | Outcome | Entry condition | Exit evidence |
| ---: | --- | --- | --- | --- |
| 1 | Retrieval-quality gate (OQ-009) | One local command measures Recall@K, MRR, irrelevant-memory leakage, and scope isolation on a versioned synthetic corpus. | Existing retrieval implementation and pinned embedding identity. | At least 50 queries, written thresholds, deterministic metric tests, real FastEmbed report. |
| 2 | Physical expiry purge | Expired rows, vectors, and relevant provenance are previewed and physically removed on demand. | Lifecycle semantics reviewed; independent of retrieval ranking. | Lifecycle contract, deletion-safety tests, purge receipt and verification. **Implemented.** |
| 3 | Embedding migration | A user can migrate a snapshot into a new fingerprinted embedding space without corrupting the original store. | Retrieval evidence and safe backup path. | Preview, atomic new-destination migration, compatibility and source/target quality reports, rollback instructions. **Implemented.** |
| 4 | JSON import and schema migration | Human-readable v1/v2 exports can be imported into a new compatible database. | Stable versioned export schema. | Round-trip, collision, provenance, permission, and failure-atomicity tests. **Implemented.** |
| 5 | Real-application starter | Python and MCP examples demonstrate capture, recall, context injection, correction, and deletion. | Retrieval usefulness demonstrated. | Runnable local Llama example and integration contract test. **Implemented.** |
| 6 | Extraction and summarization proposals | Optional local extraction proposes typed memories without silently committing unreviewed model output. | Retrieval gate, import/backup safety, and explicit extraction acceptance policy. | Review/confirmation, provenance, failure handling, and a frozen quality gate. **Implemented; live Llama quality target failed.** |
| 7 | Extraction quality v2 | Improve safe completeness without tuning further on extraction-v1. | Frozen v1 baseline, prompt comparison, and zero forbidden/write invariants. | New two-author corpus and paired architecture/model matrix. **Completed; every candidate failed and no alternative was promoted.** |
| 8 | Proposal review ergonomics | Make low-volume manual review safer and faster while model quality remains below automation gates. | Review-only proposal workflow and two independent failed quality matrices. | Source-aware local review, deterministic exact conflict/duplicate indicators, selected acceptance, and no new model authority. **Implemented.** |
| 9 | Public-release readiness | Publish a privacy-scrubbed, legally clear, reproducibly packaged first release. | Completed bounded product slices and Codeberg canonical remote. | Privacy/security scan, license and contribution policy, reproducible package/install check, release notes, and tagged Codeberg release. |

## Current cycle status

Retrieval-v1 and independent retrieval-v2 certify relative-gap 0.20 for the recorded BGE-small-v1.5 and MiniLM identities. Physical expiry purge, embedding migration, JSON portability, the real-application starter, review-first extraction, and deterministic proposal review are implemented. Extraction-v2 adds a second independent 50-case corpus. Llama single-pass remained the least-bad safe candidate but failed recall and summary gates; a two-pass design, Qwen 2.5, and Qwen3 all failed and were not promoted. The Ollama adapter safely handles the documented optional thinking field without persisting it. Proposal review now revalidates sources, distinguishes durable replay state, exposes exact duplicate/kind indicators without semantic claims, hides content by default, and scanned 100,001 exact-scope rows in 1.110 seconds without writes. Public-release readiness is in progress: content/history, logging, synthetic provenance, Apache-2.0 policy, package metadata, minimal artifact, Twine, vulnerability, SBOM/checksum, release-note, and CPython 3.11–3.14 clean-wheel gates pass. The canonical Codeberg repository is seeded from the reviewed tree with a noreply identity, and the reproducible release gate plus token-minimizing PyPI runbook are implemented. Remaining actions are the interactive TestPyPI/PyPI credential step, tag 0.1.0, and publication of the verified artifacts.

## Working rules

- A failed quality gate is recorded, not tuned away during the same measurement cycle.
- Live-model observations remain informational unless a separate repeatable benchmark is approved.
- Synthetic evaluation data must not be derived from personal memories.
- No new network listener, cloud dependency, daemon, or multi-user boundary is implied by this roadmap.
- Architecture decisions and Claude reviews are preserved alongside each completed slice.
