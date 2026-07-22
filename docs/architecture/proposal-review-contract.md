# Deterministic Proposal Review Contract

Last updated: 2026-07-20
Status: accepted for implementation

## Objective and users

Make review-first extraction safe and usable even though every measured local extractor remains
below the automation gates. The primary user is the single local owner deciding which proposals may
become durable memories. The secondary user is an application developer integrating the same
review report through Python or the CLI.

This slice adds evidence for a human decision. It does not add model authority, automatic
acceptance, a managed queue, MCP mutation, an HTTP listener, or semantic conflict judgment.

## Requirements and scale

- Load and revalidate the existing content-addressed proposal bundle before inspecting the store.
- Review is read-only. It must not create, update, embed, correct, expire, or delete a memory.
- Revalidate every source snapshot and distinguish missing, superseded, expired, shape-changed,
  content-changed, and current sources.
- Detect a previously accepted proposal from its exact `extract:<proposal_id>` operation identity.
  Distinguish a valid active replay, a replay whose result is now superseded or expired, and an
  operation-ID collision whose stored record does not match the proposal contract.
- Within the exact target scope, report active, unexpired memories with the same normalized content
  and kind as exact duplicates. Report the same normalized content under another kind as an exact
  kind collision. Also cross-index proposals in the same bundle so two equivalent proposals with
  different provenance cannot hide from the review. These are review indicators, not semantic
  conclusions.
- Preserve all evidence as independent axes and also provide one stable primary status. A lower
  priority indicator must not hide a stale source or operation collision.
- Keep acceptance separate and explicit. Selected acceptance remains bound to the exact bundle
  digest and reuses the review safety checks before the first write.
- Default CLI and report output omits proposal and source content. Explicit, separate flags may
  include proposal content or source content for a local interactive review.
- The static dashboard may visualize an exported review report in the browser, but it receives no
  database handle and cannot accept memories.

The expected personal scale is at most 100,000 active memories, 20 sources per bundle, and 50
proposals per bundle. Review may scan the exact target scope once and index normalized content in
memory. It must not perform one full-scope scan per proposal.

## Deterministic semantics

Source issue precedence is: `missing`, `superseded`, `expired`, `shape_changed`,
`content_changed`, then `current`. The report retains every applicable issue even though the first
one supplies the source's primary status. A superseded source may identify its active replacement,
but the implementation never re-anchors automatically.

Proposal primary status precedence is:

1. `blocked_source` when any cited source is not current;
2. `operation_collision` when the deterministic operation ID belongs to a structurally different
   record;
3. `replayed_superseded` or `replayed_expired` when a valid earlier acceptance is no longer active;
4. `accepted_replay` when the exact accepted result is active and unexpired;
5. `exact_duplicate` when an independently created active memory has the same normalized content,
   kind, and exact scope;
6. `kind_collision` when active memory has the same normalized content and exact scope but another
   kind;
7. `new` otherwise.

Normalization is NFC Unicode plus collapsed whitespace, matching proposal normalization. Exact
duplicate and kind-collision indicators exclude superseded and expired memories. They do not compare
embeddings, infer keys, merge scopes, or claim that different text is contradictory.

`blocked_source`, `operation_collision`, `replayed_superseded`, and `replayed_expired` are not
acceptance-ready. `accepted_replay` is eligible only for an idempotent replay. Exact duplicates and
kind collisions remain selectable because the human retains authority; the report recommends skip
or additional review rather than silently rejecting them.

## Security and privacy

- Bundle parsing, canonical identity, byte bounds, and digest verification remain the first trust
  boundary.
- Store queries use exact scope and operation identifiers. There is no fuzzy lookup or model call.
- Default output contains identifiers, kinds, statuses, counts, and hashes but no memory text or
  filesystem/database path. Content inclusion requires an explicit CLI flag.
- Source and proposal content remain untrusted data even when explicitly displayed.
- Review reports are sensitive local artifacts. The CLI writes them owner-only with no overwrite by
  default when an output path is requested.
- CLI review opens the existing compatible database in SQLite read-only and `query_only` mode. A
  programming error that attempts a write therefore fails at the database boundary.
- Acceptance still requires `--yes`, the exact expected bundle digest, and explicit proposal IDs.
  A review report is evidence, not a consent token.

## Success criteria

- Deterministic fixtures detect every store or same-bundle exact duplicate, exact kind collision, valid replay,
  superseded/expired replay, and planted operation collision.
- Missing, superseded, expired, content-changed, and shape-changed sources are reported and block
  only their dependent proposals during acceptance.
- Review leaves SQLite `total_changes`, logical memory rows, embeddings, and provenance unchanged.
- Default JSON contains no proposal or source content; each opt-in reveals only its named content
  class.
- Tampered bundles fail before store analysis. Selected acceptance of any non-ready proposal fails
  before the first write.
- A 100,000-row exact-scope synthetic review completes within two seconds on the reference machine;
  this is a local engineering ceiling, not a distributed-service SLO.
- Python, CLI, dashboard rendering, privacy, lifecycle, and adversarial tests pass together with the
  existing offline verification gate.

## Assumptions and trade-offs

- The OS account and filesystem remain the security boundary. A shared OS account would require a
  different privacy design.
- The product has one writer during explicit acceptance. Review cannot eliminate arbitrary external
  SQLite writers between review and acceptance, so acceptance always recomputes safety checks.
- Hiding content by default protects shell history, logs, and screenshots but requires an explicit
  flag for substantive human judgment.
- Exact normalization intentionally misses paraphrases and real semantic contradictions. Adding an
  embedding or model judge would weaken repeatability and is deferred until separately measured.
- Allowing a human to accept an exact duplicate preserves authority but does not guarantee a
  duplicate-free store. The report makes the cost visible and measurable.
- No rejected-decision ledger exists, so replay means a prior durable acceptance, not a previously
  viewed or rejected proposal.

## Considered options

| Option | Benefit | Cost/risk | Decision |
| --- | --- | --- | --- |
| Multi-axis deterministic review | Preserves all safety evidence and is reproducible offline | Cannot find paraphrases or semantic contradictions | Selected |
| Single first-match classification only | Small output | Hides useful duplicate/collision evidence behind stale-source state | Rejected |
| Embedding or LLM conflict judge | Broader semantic recall | Uncertified false positives, model authority, latency, privacy surface | Deferred |
| Persistent review queue | Tracks rejected decisions and collaboration | Schema, lifecycle, retention, and UI complexity outside personal MVP | Deferred |
| Hierarchical scope-overlap collision | Could support future policy scopes | Conflicts with accepted exact non-hierarchical scope semantics | Rejected |
