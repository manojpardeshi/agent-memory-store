# Claude Final Ship Assessment

> Verbatim Claude Sonnet response captured on 2026-07-15 after the implementation-review findings were reconciled. The two suggested test gaps were subsequently added; the suite now has 22 passing tests.

## Assessment

**Prior blockers 1–6: resolved.** Each has a concrete, verifiable mechanism rather than a policy promise:

- Whole-store export → now requires an explicit exact-scope/subject/all-scopes selector (no implicit default).
- Restore → `--yes` required, always refuses existing destinations, sidecars untouched.
- Permissive file-creation window → DB files precreated 0600; backup/export use mkstemp(0600)+atomic replace, closing the window where a file briefly exists world/group-readable.
- Backup/export clobbering → both refuse existing paths unless overwrite is explicit; CLI broad exports gated by `--yes`, MCP export/backup preview gated by `confirm=true`.
- Operation-id race → duplicate insert now resolves to the already-committed record instead of erroring or double-writing.
- Deriving from superseded sources → enforced at two points (source must be active; re-checked again inside the embedding transaction before vector insertion), which correctly closes the TOCTOU gap between selection and write.

This is a good pattern: the confirm/--yes additions fix *consent*, the mkstemp/precreate/atomic-replace changes fix *exposure*, and the active-status recheck fixes a *logic* race — three different bug classes, three different mechanisms, not a single blanket "add a flag" fix.

**Preview/delete drift: not fixed, but reasonably scoped.** Recomputing descendants at execution time (rather than trusting the preview snapshot) is arguably the *safer* choice for privacy-complete deletion — it guarantees nothing that started referencing the target after preview survives the delete. The drift this creates (execution may cascade wider than what was previewed) is only a real hazard under concurrent mutation between preview and confirm, which a single-writer personal MVP doesn't have. Deferring revision-bound confirmation until multi-process use is the right sequencing — building it now would be speculative for a workload that doesn't exist yet.

**Residual gaps, based only on what's stated:**

- The write-up says the *consent gates* (`--yes`, `confirm=true`) and the *operation-id race resolution* were "implemented," but the specific tests called out are for path-overwrite/no-clobber and artifact modes. There's no explicit confirmation that a test asserts "missing `--yes`/`confirm` actually aborts" or "concurrent duplicate operation-id resolves to one row, not an unhandled exception." Given single-writer usage this is low risk to *this* release, but it's the natural next thing to pin down before trusting the gates long-term.
- Deferred items (auto-extraction, TTL purge, JSON import, model migration, numeric retrieval-quality threshold) are correctly out of scope for an MVP and not blockers.

**Ship/no-ship: Ship**, for private, single-user, single-writer working use. All six data-loss/exposure/corruption blockers from the prior review have real fixes with matching tests (ResourceWarning-as-error is a good sign the file/connection handling was actually exercised, not just unit-tested in isolation). The one open item (preview/delete drift) is a consciously accepted, well-justified trade-off for this deployment shape, not an oversight.

**Before widening scope** (multi-writer, public, or anyone else's data): add explicit tests for the confirm/`--yes` abort paths and the operation-id race, and revisit preview/delete drift with revision-bound confirmation.
