# CLI, MCP, and package audit — November 25, 2026

This audit checks the November improvement branches together. They were merged locally in an
isolated temporary worktree; no merge was pushed to `main` and no paid model was called.

## Lifecycle parity

| Lifecycle operation | CLI | MCP | Result |
| --- | --- | --- | --- |
| Remember turn or typed memory; recall, get, list, correct | Direct commands | Corresponding `memory_*` tools | Same store and record behavior in the installed-wheel smoke flow. |
| Hard deletion | Preview, then `--yes` with digest or `--force-current` | Preview, then `confirm=true` with digest or `force_current=true` | Installed-wheel flow previewed through CLI and deleted through MCP with the same digest. |
| Expiry purge | Preview, then digest-bound confirmation | Same preview and confirmation pattern | Covered by the combined Python and MCP tests. |
| Export and backup | Explicit selection and overwrite controls | Preview, then `confirm=true` | Both use the shared no-clobber publication path. |
| Process pending embeddings and inspect status | Direct commands | Corresponding `memory_*` tools | Both dispatch to the same store methods. |

CLI-only restore, JSON import, embedding migration, and proposal acceptance are deliberate
boundaries documented in `mvp-contract.md`. They involve new database paths, model work, or trusted
human review. MCP list is exact-scope; CLI additionally has an all-scopes operator view.

## Verification

- All seven open improvement branches merged locally. The only merge conflicts were additive
  `CHANGELOG.md` entries; there were no code conflicts. The combined tree passed **373 tests**,
  `uv run ruff check .`, `uv lock --check`, and `uv build`.
- The wheel and source archive each installed with dependencies into a fresh Python 3.14.5 virtual
  environment. Both installed the `llm-memory` and `llm-memory-mcp` entry points. The source
  archive's installed CLI initialized an offline deterministic store with `integrity_check=ok`.
- The wheel smoke flow initialized a store and remembered a turn through the installed CLI, read
  and corrected it through the installed MCP server, inspected the correction through CLI, then
  used a CLI deletion preview digest to delete through MCP. Final status showed zero memories and
  `integrity_check=ok`.
- The real-application starter's deterministic offline demo completed through both direct Python
  and MCP transports. Both reported no stale value after correction and a verified deletion.

The PRs are still independent and open. Each is currently mergeable against `main`, but their
shared changelog location will require resolution as earlier PRs land. The local integration
worktree verified the combined code; GitHub reports no automated checks on these PRs.
