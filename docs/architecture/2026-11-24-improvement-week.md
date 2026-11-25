# Improvement Week: November 24–30, 2026

Status: in progress. Work is limited to the local, single-user product boundary. Use synthetic
data and free local checks; do not reopen rejected retrieval policies or run paid model benchmarks.

The September `improvement-suggestions.md` predates releases 0.2–0.4. Its completed and rejected
items are historical evidence, not this week's backlog. PR #1 already addresses atomic hard deletion
and preview-bound confirmation; it remains separate from the work below.

| Day | Work | Completion check |
| --- | --- | --- |
| Nov 24 | Fix `find_by_metadata` applying `LIMIT` before expiry filtering. | An expired first match cannot hide a later live match; full Python tests and Ruff pass. |
| Nov 25 | Audit no-overwrite publication for JSON export and SQLite backup under concurrent destination creation. Fix any reproduced race. | A deterministic race test proves existing destinations are preserved, or the audit records why no change is needed. |
| Nov 26 | Add a per-question watchdog to the local Mem0 runner. Audit the paid Kimi runners for timeout and billing-safe resume behavior before changing them. | Offline tests prove the local timeout and alarm cleanup; paid runs never reissue an uncertain in-flight call automatically. |
| Nov 27 | Audit concurrent correction and idempotent write behavior across two SQLite connections. Fix verified invariant failures. | Reproducible interleaving tests cover any fix; no duplicate active lineage or wrong-scope replay is introduced. |
| Nov 28 | Measure `status()` cost and memory use at personal-scale store sizes, then optimize only if the measurements justify it. | Before/after figures and unchanged integrity results are recorded. |
| Nov 29 | Review CLI/MCP lifecycle parity and package installation against the week's changes. | Full tests, Ruff, lock check, and wheel/source build pass; examples still run offline. |
| Nov 30 | Review open PRs, resolve regressions, and publish a short evidence-based weekly report. | Every shipped change has a GitHub PR, test evidence, and a stated remaining limitation. |

Each day should leave the repository clean and use a reviewable `codex/` branch. Changes to public
behavior need documentation and focused regression coverage. Keep the default retrieval policy and
existing benchmark decisions unchanged unless new independent evidence meets their written gates.

## Progress

- **Nov 24 complete:** expiry filtering now happens before the metadata lookup limit. The new
  regression covers expired rows preceding a live match. Full Python suite: 354 passed; Ruff,
  lock check, and package build passed. PR #2.
- **Nov 25 complete early:** export and backup publication now preserves a competing destination.
  Deterministic race tests cover both paths. Full Python suite: 355 passed; Ruff, lock check, and
  package build passed. PR #3.
- **Nov 26 local portion complete early:** the Mem0 local comparator has a configurable question
  deadline, checkpointed timeout, and alarm cleanup. Offline tests prove a deadline is not swallowed
  by its session-error handler. Full Python suite: 356 passed; Ruff, lock check, and package build
  passed. PR #4.
- **Nov 26 complete early:** Kimi calls already have per-call network timeouts. The baseline runner
  now persists an in-flight question marker before paid calls and rejects incomplete legacy reports
  without one. The paired runner rejects uncertain in-flight calls instead of automatically reissuing
  them; its explicit observed no-response HTTP 429 path remains. Both paths now stop for manual
  reconciliation when billing is uncertain. A durable per-call ledger would improve resumability but
  is not needed to prevent automatic duplicate charges. No paid calls were made. Full Python suite:
  356 passed; Ruff, lock check, and package build passed. PR #6.
- **Nov 27 complete early:** operation-ID replay now rejects scope, write-type, role, and provenance
  collisions, including a concurrent insert collision. Correction replay is restricted to the same
  lineage, and active-version reads happen under the SQLite write lock so concurrent corrections
  advance versions serially. Full Python suite: 358 passed; Ruff, lock check, and package build
  passed. PR #5.
- **Nov 28 complete early:** synthetic 1,000/10,000/50,000-memory measurements showed `status()`
  spent Python memory on three full ID sets. At 50,000 memories, SQLite `EXCEPT` counts reduced
  status latency from 0.546–0.575 s to 0.376–0.377 s and traced Python peak allocation from
  8.929–9.020 MiB to 0.002–0.004 MiB. Full status reports and integrity results matched; a
  focused regression also counts a missing and an orphan vector. Full Python suite: 354 passed;
  Ruff, lock check, and package build passed. PR #7.
- **Nov 29 complete early:** all seven code PRs were merged in a temporary local integration
  worktree. Combined verification passed 373 tests, Ruff, lock check, and wheel/source build.
  Fresh virtual environments installed both artifacts. An installed-wheel smoke flow crossed CLI
  and MCP for remember, get, correct, preview-bound deletion, and status; the source archive's CLI
  also initialized a store offline. Both Python and MCP real-application demos passed offline.
  Only additive changelog conflicts arose during local merges; no code conflict. PR #8 records the
  parity and package audit. The open PRs will need changelog reconciliation as they land.
