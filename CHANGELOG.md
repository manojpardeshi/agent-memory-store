# Changelog

All notable changes to this project are documented here.

## Unreleased

### Changed

- `recall` scores candidates from one batched query and loads only the records it returns: about
  6 SQL statements per call instead of about 123 at limit 10 and 603 at limit 50, with median
  latency roughly halved at limit 10 and cut by about 65% at limit 50 on a 3,000-memory store.
  Results are identical, verified against the previous algorithm.
- `list_memories` and JSON export fetch records two queries per batch of up to 500 instead of two
  per record. Output is unchanged, record for record, and the query count no longer grows with the
  number of records.

- Reframed the post-0.1 roadmap around matched standard-benchmark evidence and measurable local
  retrieval quality before new product tuning.
- Paused retention-tombstone work until benchmark-driven quality releases or concrete user
  retention evidence justify the schema and interchange cost.

### Added

- Opt-in hybrid recall: `recall(..., retrieval="hybrid")`, `llm-memory recall --retrieval hybrid`,
  and the MCP `retrieval` argument fuse vector ranking with an FTS5 BM25 keyword ranking by
  reciprocal rank fusion (k = 60). On held-out LongMemEval-S questions it raised the number with
  complete evidence in the top ten from 80 to 91 of 117. It lowers MRR on the paraphrase-heavy
  synthetic retrieval_v2 suite below its gate, so vector stays the default. Results gain a
  `fusion_score` in hybrid mode only; vector output is unchanged.
- A trigger-maintained FTS5 keyword index (`memory_keywords`) is created for new stores and built
  for existing stores the first time they are opened writable. It is additive, so
  `SCHEMA_VERSION` is unchanged. FTS5 secure-delete makes forgetting physically remove a memory's
  terms. The index needs SQLite 3.44 or newer; on older SQLite it is skipped and hybrid recall is
  unavailable. A runtime on older SQLite cannot write to a store already carrying the index.
  `status()` reports `keyword_index` as `ok`, `corrupt`, `absent`, or `unverified` (read-only).
- `evaluate-retrieval --retrieval {vector,hybrid}` runs the synthetic gates in either mode.

- Experimental `llm_memory_store.temporal.resolve_event_dates(text, reference)` resolves relative
  English date expressions ("last Tuesday", "3 weeks ago", "on March 4th", "last month") to
  calendar dates or ranges deterministically, with fixed documented rules for ambiguous cases and
  no model. Not yet used by recall.

- `MemoryStore.find_by_metadata(scope, filters)` returns memories in one exact scope whose top-level
  metadata matches every filter, matched inside SQLite so only matching rows are loaded. Superseded
  and expired memories are excluded by default using the same expiry rule as `recall`. Keys must be
  plain identifiers; the JSON path is always a bound parameter.

- Added a pinned MemoryBench provider/stdio bridge, LongMemEval-S dataset verifier, lifecycle and
  loopback-evaluator patches, and deterministic adapter tests.
- Recorded a six-category LongMemEval-S diagnostic smoke: all labeled support sets were retrieved
  in the top 10, while the local 8B evaluator failed all six answers, gating the full baseline until
  a trustworthy frozen evaluator pilot passes.
- Added a resumable, budget-bounded Claude CLI pilot runner and recorded exact `claude-opus-5`
  passing the six-category evaluator gate at 5/6 for $1.024665; the full 500-question run remains
  gated on a separate budget decision.
- Added a frozen 60-question LongMemEval-S manifest, sample-aware MemoryBench search orchestration,
  explicit FastEmbed cache handling, and deterministic answer-session retrieval analysis.
- Recorded the Opus 5 stratified diagnostic at 47/60 answers (78.3%) for $9.108015. Multi-session
  (3/10) and temporal (5/10) questions dominate the misses despite 95% labeled-session hit@10;
  the planned paid Opus complementary expansion was later superseded by the Kimi worker protocol.
- Added deterministic LongMemEval development, sealed-validation, reserve, qualification, and
  complementary manifests; started the API-free 440-question retrieval pass.
- Added secret-safe direct Kimi K3 probe and resumable evaluator runners with exact-model checks,
  strict structured judging, cost ceilings, repeated answers/votes, and empty-context controls.
- Recorded Kimi K3 automated qualification at 15/20 retrieved versus 1/20 empty-context, 96.7%
  judge unanimity and answer-repeat agreement, for $1.459725.
- Completed the pre-registered blind 30-item judge-concordance audit on Opus-generated answers:
  Kimi passed all five gates at 28/30 overall human agreement, 16/17 human-positive, 12/13
  human-negative, zero positive-count drift, and 28/30 unanimous, for $0.245987 additional spend.
  This qualifies Kimi judging only.
- Completed the separate human audit of 20 actual first-pass Kimi answers at 17/20 (85%), passing
  the frozen 14/20 answerer gate. Provenance validation matched every candidate exactly to raw
  `kimi-k3` output; this reused existing answers and added no API cost.
- Completed the local 500-question LongMemEval-S retrieval-only baseline at 97.0% Hit@10, 92.1%
  answer-session recall@10, and 0.910 MRR@10; multi-session and temporal coverage remain the
  dominant retrieval gaps.
- Isolated benchmark JSON-lines output from third-party stdout and ASCII-escaped protocol strings
  after a U+2028 source character exposed Node readline record splitting; added regression coverage
  and resumed the intact checkpoint without changing retrieval behavior.
- Added a default-off, provenance-based session-diverse context policy and resumable development
  replay. On the frozen 180-question development split it passed all pre-registered retrieval and
  operational gates: answer-session recall@10 improved from 92.80% to 95.74%, temporal recall from
  83.48% to 90.72%, and mean formatted context bytes fell 13.2%.
- Recorded the candidate's frozen matched 60-question exact-`kimi-k3` answer-quality failure:
  released baseline 45/60 versus session-diverse 40/60 for $4.147215. Added resumable paired-run,
  analysis, and blinded audit tooling. The completed 13-question audit plus 3 reliability
  duplicates passed human reliability gates and authoritatively rescored baseline 47/60 versus
  candidate 41/60. The candidate is rejected; sealed validation and reserve remain unopened.
- Added a reproducible discordance analyzer showing the hard session cap increased distinct sessions
  30→69 but reduced labeled answer-session messages 90→37 across the 11 disputed questions; seven
  of eight candidate losses pruned the direct answer-bearing message.
- Added a deterministic, fictional 60-case session-density corpus assembled from two isolated author
  halves, cross-reviewed after one label correction, balanced across six categories and two evidence
  strata, and verified to have zero normalized 12-token overlap with LongMemEval. The proposed
  score-gated two-swap contract remains draft/blocked pending v1 human adjudication and freeze review.

## 0.1.0 - 2026-07-23

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
