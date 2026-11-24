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
| Nov 26 | Add bounded per-question watchdogs to the remaining long-running benchmark runners. | Timeout and cleanup paths have offline tests; a stalled question cannot silently hang a run. |
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
  lock check, and package build passed.
