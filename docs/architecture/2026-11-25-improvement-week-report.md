# Improvement week closeout — November 25, 2026

The November 24–30 plan was completed early in the local, single-user product boundary. Eight
focused pull requests remain open as review units. This report accompanies a combined integration
branch that resolves their additive changelog conflicts and gives reviewers one merge path. No
change has been merged to `main` as of this report.

| PR | Delivered change | Verification and scope |
| --- | --- | --- |
| [#1](https://github.com/manojpardeshi/agent-memory-store/pull/1) | Atomic hard deletion and preview-bound CLI/MCP confirmation | Concurrent deletion and stale-preview regressions; local SQLite only. |
| [#2](https://github.com/manojpardeshi/agent-memory-store/pull/2) | Expiry filtering before metadata lookup `LIMIT`, plus the week plan | Expired-first regression; 354 tests on its branch. |
| [#3](https://github.com/manojpardeshi/agent-memory-store/pull/3) | No-clobber JSON export and SQLite backup publication | Deterministic competing-destination tests; 355 tests on its branch. |
| [#4](https://github.com/manojpardeshi/agent-memory-store/pull/4) | Local Mem0 per-question watchdog | Offline timeout and alarm-cleanup tests; requires `SIGALRM`. |
| [#5](https://github.com/manojpardeshi/agent-memory-store/pull/5) | Scoped operation-ID replay and serial correction versions | Replay and two-connection correction tests; 358 tests on its branch. |
| [#6](https://github.com/manojpardeshi/agent-memory-store/pull/6) | Paid Kimi resume fails closed on uncertain calls | Offline simulated interruptions; 356 tests on its branch; no paid calls. |
| [#7](https://github.com/manojpardeshi/agent-memory-store/pull/7) | SQLite status counts replacing Python ID sets | Synthetic 50,000-memory audit and missing/orphan regression; 354 tests on its branch. |
| [#8](https://github.com/manojpardeshi/agent-memory-store/pull/8) | CLI/MCP and package integration audit | Wheel and source installs in clean environments, cross-surface lifecycle smoke, offline demos. |

## Combined verification

All eight branches were merged in an isolated temporary worktree. The combined tree passed **373
Python tests**, `uv run ruff check .`, `uv lock --check`, `uv build`, and `git diff --check`.
Fresh Python 3.14.5 environments installed the wheel and source archive with dependencies. The
installed wheel completed CLI remember → MCP get/correct → CLI inspect/preview → MCP digest-bound
delete → CLI integrity status. Direct Python and MCP real-application demos both completed offline.
No paid benchmark was run.

At 50,000 synthetic memories, `status()` took 0.546–0.575 seconds before and 0.376–0.377 seconds
after the SQL change. Peak traced Python allocation fell from 8.929–9.020 MiB to 0.002–0.004 MiB.
The full status reports matched; this is a personal-scale result, not a claim about SQLite's own
memory use or multi-user workloads.

## Review and remaining limits

- The combined code had no merge conflicts. Independent PRs add changelog entries at the same
  location, so sequentially merging those branches would require resolving that file. The
  integration branch contains the resolved changelog and is the simpler single merge path after
  reviewing the focused PRs.
- GitHub reports no automated checks or reviews on these PRs. Local tests and package smoke provide
  the evidence above; a repository CI gate remains future work.
- An uncertain paid Kimi call stops automatic resume. Manual billing reconciliation or a durable
  per-call ledger is still needed to continue that particular report safely.
- The Mem0 watchdog uses `SIGALRM` and therefore runs only where that signal is available.
- Backup and export no-clobber publication relies on same-directory hard links. The temporary file
  is created in the destination directory; overwrite still requires an explicit request.

The week plan's code and audit goals are complete. Merging the reviewed integration pull request
and closing superseded focused PRs are repository-maintainer decisions after review.
