# Changelog

All notable changes to this pre-release project are documented here.

## Unreleased

### Added

- Versioned synthetic retrieval-quality evaluation with Recall@K, MRR, distractor, random-control, and scope-isolation evidence.
- Explicit opt-in relative semantic-gap filtering through Python, CLI, MCP, and the evaluation command.
- On-demand physical expiry purge through Python, CLI, and MCP, with a stable cutoff, preview digest, blocked-dependency reporting, transactional receipts, and post-delete verification.
- Previewed Python/CLI embedding migration into a distinct, atomically published destination, with preserved logical identity, rebuilt vectors, synthetic source/target quality evidence, regression blocking, and rollback through the untouched source.
- JSON export format v2 with operation IDs, verified content hashes, and explicit external provenance references, plus validated v1/v2 Python/CLI import into a new atomically published store.
- Runnable real-application chat starter with interchangeable direct-Python/MCP memory, deterministic-offline/loopback-Ollama models, bounded untrusted context injection, lifecycle commands, exact handoff metrics, and live local-Llama evidence.
- Two-phase extraction and summarization proposals through Python/CLI, with deterministic content identity, owner-only tamper-evident artifacts, strict untrusted Ollama JSON validation, explicit selected acceptance, source revalidation, exact provenance, and idempotent replay.
- Independently authored retrieval-v2 corpus with 60 balanced synthetic queries and a paired BGE/MiniLM default-versus-filtered evidence matrix.
- Judge-free extraction-quality evaluation with strict dataset validation, 12-case deterministic and 50-case live tracks, exact kind/provenance scoring, summary fact units, forbidden/duplicate/invalid controls, Wilson intervals, and hard no-write/source-preservation checks.
- Conservative Ollama extraction-v2 prompt with explicit injection/retraction/uncertainty exclusions, bounded generation, and one structured-output retry; frozen local-Llama evidence remains failed and automatic acceptance remains prohibited.
- Independent two-author extraction-v2 corpus and paired local matrix rejecting a noisy Llama two-pass design plus Qwen 2.5/Qwen3 alternatives; failed candidates are documented and not exposed.
- Store-aware, read-only proposal review through Python/CLI with explicit source lifecycle states,
  valid/inactive replay detection, operation-collision blocking, exact-scope duplicate and kind
  indicators, content-hidden defaults, owner-only review reports, and a browser-only selection view.

### Changed

- **Breaking behavior:** relative semantic-gap `0.20` is now the default for the exact certified BGE-small-v1.5 and all-MiniLM-L6-v2 behavioral identities. Recall may return zero through K items instead of always filling K. Python callers pass `relevance_filter=None`, CLI callers pass `--no-relevance-filter`, and MCP callers pass `relevance_filter="off"` to restore legacy unfiltered behavior.
- Unknown, upgraded, or behaviorally changed embedding identities remain unfiltered until the same paired quality gate certifies them.
- Evaluation reports now include the full behavioral embedding identity and state whether the measured configuration is that identity's product default.
- Ollama generation requests disable thinking where supported and safely ignore the documented bounded `thinking` response field; reasoning traces never enter proposals or reports.
- `review-proposals` now requires an existing compatible store and omits proposal/source content by
  default; sensitive text requires separate explicit reveal flags.

### Compatibility

- Ranking remains 80% semantic / 20% recency, but certified identities apply the default relative-gap filter after ranking. Explicit unfiltered opt-out preserves the previous result set.
- Expiry remains lazily enforced during recall. Physical purge is explicit and never deletes an unexpired descendant; blocked expired sources remain stored until their dependencies are resolved.
- Embedding migration never mutates or overwrites the source. Quality-regression overrides require a written reason and remain visible in the report; MCP migration is not exposed.
- Export format v2 replaces v1 for new files. Import remains backward-compatible with v1, but correctly reports that v1 operation IDs cannot be recovered. Non-self-contained imports reject unless provenance loss is explicitly accepted.
- Extraction remains opt-in and never commits model output directly. MCP extraction/acceptance is not exposed; Python hosts own their consent UI, and CLI acceptance requires the reviewed digest, selected proposal IDs, and `--yes`.

### Packaging

- Python source distributions explicitly exclude generated dashboard dependencies and build outputs; local `node_modules` no longer inflate release archives.
- Selected Apache-2.0 with published contribution, security, support, threat-model, and dependency-license policies.
- Added PEP 639 license metadata and canonical Codeberg project URLs to Python package metadata.
- Reduced the source distribution to the Python package plus README, changelog, license, build metadata, and public policy files.
- Added a reproducible release-gate command and a token-minimizing PyPI publication runbook. Codeberg
  remains canonical; no long-lived PyPI credential is stored in Codeberg CI.
- Updated affected dashboard dependencies and transitive resolutions after npm reported seven
  high-severity advisories; the locked dashboard graph now passes `npm audit`.
