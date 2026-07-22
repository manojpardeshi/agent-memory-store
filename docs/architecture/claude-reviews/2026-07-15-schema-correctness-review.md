# Claude Schema Correctness Review

- Date: 2026-07-15
- Reviewer: Claude Sonnet via the local Claude Code CLI (`claude -p`)
- Round: 2
- Status: Advisory input; see the reconciliation record for adopted changes

## Prompt

> Second architecture round. We modified your earlier proposal as follows: use one normalized memories table for turn/fact/preference/summary/event; integer internal ID plus UUID public ID; a normalized memory_sources(child_id, source_id, relation) table instead of JSON provenance; scopes are exactly private(subject, environment, agent) or shared(subject, environment, pool), with no wildcard/hierarchy; raw memory commits first with embedding_status=pending, then synchronous best-effort embedding advances to ready or failed, and process_pending retries explicitly; correction creates a new active version in the same lineage and supersedes the old; hard delete defaults to deleting the whole corrected lineage plus recursively derived descendants, their vectors, and provenance edges; logical active-database deletion uses secure_delete, post-commit verification, and WAL checkpoint but does not claim forensic erasure from backups/SSD snapshots. sqlite-vec uses scope_id as a partition key and exact KNN is performed per explicitly allowed scope then merged. Typed derived memories may be inserted directly in MVP; automatic LLM extraction is deferred. In under 1200 words, identify correctness bugs or hidden complexity in this revision, recommend precise fixes, and state whether it is a credible solo-developer MVP.

## Response

## Correctness bugs & hidden complexity

**1. Single polymorphic `memories` table underestimates per-type schema needs.**
Turns, facts, preferences, summaries, and events have different required fields (turn: speaker/timestamp; preference: confidence/override scope; event: event_time vs record_time). One table forces either sprawling nullable columns or a type-specific JSON blob — which quietly reintroduces the unstructured-payload problem you just eliminated for provenance. It also blocks type-appropriate indexing (full-text on turns vs. vector search on facts).
*Fix:* keep one core table (internal id, uuid, type, scope_id, lineage_id, created_at, embedding_status, is_active) for identity/versioning, plus thin per-type extension tables joined on internal id. Preserves a single ID space for `memory_sources` while giving each type real constraints.

**2. `memory_sources(child_id, source_id, relation)` has no cycle or depth guarantee.**
Nothing stops a cycle forming across corrections/derivations, which breaks the "recursively delete descendants" cascade — a `WITH RECURSIVE` walk over a cyclic graph either loops or needs ad hoc visited-set logic that isn't mentioned.
*Fix:* enforce a DAG at insert time (source generation must be ≤ child generation) and store an explicit `generation`/`depth` column so cascades terminate deterministically and can be reasoned about without runtime cycle detection.

**3. Correction + derivation interaction is unspecified.**
If fact B is derived from turn A, and A is corrected to A′, does B's source edge migrate to A′, or does B keep pointing at the now-superseded A? The proposal doesn't say, and the two answers have very different correctness implications. If edges don't migrate (the safer default), then "hard delete = delete corrected lineage + all descendants" becomes a wider blast radius than users likely expect: deleting A also deletes every fact ever derived from it, even ones a user may still consider valid.
*Fix:* pick the non-migrating default explicitly, document it as the deletion semantics ("delete this memory and everything causally downstream, permanently"), and require a dry-run/preview step before a hard delete executes, since this is the single most destructive and least reversible operation in the system.

**4. Superseded rows must be excluded from vector search, not just correction bookkeeping.**
When a correction creates a new active version, the old row presumably stays until hard-deleted (per the delete-is-separate-from-correct design). If its embedding and sqlite-vec row remain, KNN search will surface stale, corrected content unless every query filters on `is_active`/lineage-head in addition to `scope_id`.
*Fix:* make `is_active` part of the mandatory query predicate alongside `scope_id`, not an assumed side effect of correction.

**5. "Commit raw, then synchronous best-effort embedding" needs an explicit two-transaction contract.**
If the embedding call (likely a network round-trip) happens inside the same transaction as the raw insert, you're holding SQLite's single writer lock across an external API call — a serialization/latency hazard under any concurrent write load. If it's a second transaction (as "commits first" implies), that needs to be stated plainly: T1 inserts with `status=pending` and commits; T2 later updates `status=ready|failed` in its own short transaction. Also unspecified: what a read sees between T1 and T2. If `pending`/`failed` memories are invisible to vector KNN but visible to lexical/ID lookups, a user's very next query might not find something they just wrote — surprising if not documented as the expected contract.
*Fix:* two explicit transactions, no lock held across the network call; document that pending/failed rows are excluded from vector search but included in direct/lexical access; `process_pending` is a bounded-retry sweep over `status IN (pending, failed)`.

**6. Scope model trades ambiguity for enumeration cost.**
Dropping wildcards/hierarchy is a good simplification for matching correctness (no ambiguous partial matches), but it pushes cost onto query time: "search all my private scopes across every agent" now requires the caller to enumerate concrete scope_ids rather than passing a pattern. If `scope_id` is a derived hash of `(subject, environment, agent)`, enumeration means guessing or full-scanning — there's no described lookup path.
*Fix:* maintain a small `scopes` table (`scope_id, kind, subject, environment, agent_or_pool`) so "all scopes for subject X" is an indexed query, not a hash-space search. This is cheap and removes a real gap.

**7. Per-scope exact KNN + merge has a correctness trap and a scaling ceiling.**
Merging top-K results from N separate per-scope queries requires fetching K from *each* scope before the final sort (fetch N×K, then re-rank), and the re-rank must use a consistent, correctly-signed metric (distance ascending vs. similarity descending — an easy off-by-sign bug). This is fine at small N (a handful of scopes per query) but the fan-out is O(N) queries per search, so it won't scale past dozens of allowed scopes without an ANN index that's scope-aware.
*Fix:* explicitly document this as a small-N design (bounded by expected agent/pool counts for a single subject) and note the merge step must fetch K-per-scope before global top-K, not top-K globally from a naive round-robin.

**8. Hard-delete cascade needs explicit atomicity across three stores.**
Deleting a lineage plus descendants touches the memories rows, the sqlite-vec vectors (a separate virtual table, likely without FK cascade), and `memory_sources` edges. If these aren't deleted in one transaction with a defined order (edges → vectors → rows, or all under deferred FK checks), a crash mid-cascade leaves orphaned vectors or dangling edges.
*Fix:* single transaction covering all three; since sqlite-vec won't cascade via FK, delete its rows explicitly in the same transaction, and add a periodic orphan-vector consistency check as a safety net.

**9. `secure_delete` + WAL checkpoint is good but slightly incomplete as stated.**
`PRAGMA secure_delete` must be set at the connection level *before* the delete, not applied retroactively, and WAL checkpointing removes old frames from the WAL file but doesn't zero freed pages in the main database file — freelist/index pages can still retain recoverable content until a `VACUUM` (or `auto_vacuum=incremental` with periodic incremental vacuum) runs. The proposal is right not to claim forensic erasure, but should also not imply checkpoint alone is sufficient for the *active* database file.
*Fix:* add scheduled `PRAGMA incremental_vacuum` (or set `auto_vacuum=INCREMENTAL` at DB creation) alongside the checkpoint step, keeping the existing honest disclaimer about backups/SSD wear-leveling.

## Verdict

Credible as a solo-developer MVP. The scope simplification, honest deletion semantics, and two-phase embedding are the right instincts for keeping scope buildable by one person. The gaps above are clarifications and small additive schema pieces (a `scopes` lookup table, a `generation` column, an `is_active` query predicate, one explicit transaction boundary) rather than a redesign — none require walking back the core decisions. The one item worth resolving *before* writing code, because it's a policy choice rather than a bug fix, is #3: whether corrections propagate to dependents. That single decision determines how surprising hard-delete's blast radius will be to end users.
