# Review: LLM Memory Store MVP

> Verbatim Claude Sonnet review captured on 2026-07-15. Claude was given the complete MVP source, tests, README, and architecture contract in a read-only prompt. File line numbers reflect the pre-fix revision.

## Critical / High Findings

**1. `export_data`/`export_json` default to dumping the entire store across all subjects and scopes — no confirmation gate**
`src/llm_memory_store/store.py: MemoryStore.export_data`

```python
if scope is not None: ...
elif subject is not None: ...
else:
    memory_rows = self.connection.execute("SELECT id FROM memories ORDER BY id").fetchall()
```

`memory_export` in `mcp_server.py` and the `export` CLI subcommand both default `scope_kind=None`, `subject_only=False`. If an MCP tool call (or a script) omits `scope_kind`, the tool silently exports **every subject, every private agent scope, and every shared pool** to an arbitrary caller-chosen path, in plaintext, with zero confirmation. Contrast this with `memory_forget`/`memory_forget_scope`, which correctly gate on `confirm=True` plus a preview. Export is at least as consequential as deletion (it's the primary exfiltration primitive) but has no equivalent safety rail. Since recalled memory content is explicitly documented as "untrusted" and could contain injected instructions aimed at an agent, an agent tricked into calling `memory_export(destination=...)` with no other arguments will leak the whole store. This needs a required, explicit scope (no all-scope default) or a `confirm` parameter mirroring the deletion tools.

**2. `restore_database` silently clobbers an existing destination and deletes its WAL/SHM sidecars**
`src/llm_memory_store/database.py: restore_database`

```python
target_connection = sqlite3.connect(destination)
...
source_connection.backup(target_connection)
...
for suffix in ("-wal", "-shm"):
    sidecar = Path(f"{destination}{suffix}")
    if sidecar.exists():
        os.remove(sidecar)
```

There is no check that `destination` is absent or empty before backing up over it, and no `--yes`/confirmation flag on the CLI `restore` command (unlike `forget`/`forget-scope`). `llm-memory restore --source backup.sqlite3 --db ~/.llm-memory/memory.sqlite3` will overwrite the live production database in place with zero warning. Worse, it unconditionally deletes any `-wal`/`-shm` sidecars belonging to the destination path — if another process (e.g. a running MCP server) currently has that same database open in WAL mode, this can corrupt its in-flight state or lose recently-committed data that hadn't been checkpointed. This is the single most dangerous operation in the tool and has the weakest guard rails.

**3. Sensitive files pass through a window of default (umask) permissions before being chmod'd to 0600**
`src/llm_memory_store/database.py: connect_database`, `consistent_backup`, `restore_database`; `src/llm_memory_store/store.py: MemoryStore.export_json`

```python
connection = sqlite3.connect(path, ...)   # file created here, default mode
...
if path.exists():
    with suppress(OSError):
        path.chmod(0o600)                 # applied after the fact
```

```python
target = sqlite3.connect(destination)     # backup file created here
try: source.backup(target)
finally: target.close()
destination.chmod(0o600)                  # applied after backup completes
```

```python
destination.write_text(json.dumps(data, ...) + "\n")   # export written here
destination.chmod(0o600)                                # applied after write
```

The README/architecture contract explicitly promises database, backup, and export files are mode `0600`. In each case above, sqlite (or `write_text`) creates the file with the process umask (commonly `022` → world-readable `644`) *before* the code narrows permissions. On a genuinely multi-user machine — the exact threat this MVP claims to defend against ("local OS account" boundary) — another local user can read full plaintext personal memory content during that window, and for `export_json` the file may contain the complete database contents. Fix by setting a restrictive umask or pre-creating the file with `os.open(path, os.O_CREAT | os.O_EXCL, 0o600)` before any writer touches it.

## Medium Findings

**4. `MemoryStore.backup` deletes/overwrites an arbitrary caller-chosen path**
`src/llm_memory_store/database.py: consistent_backup` — `if destination.exists(): destination.unlink()`. The only guard is `destination != self.path` in `store.backup()`. An MCP `memory_backup(destination=...)` call (again reachable via an agent acting on injected recalled text) will silently delete and replace any file the caller names, as long as it isn't the live DB path itself. This is an arbitrary-file-clobber primitive with no confirmation.

**5. `operation_id` idempotency check races with the UNIQUE constraint under concurrent calls**
`src/llm_memory_store/store.py: MemoryStore.remember` pre-checks `SELECT id FROM memories WHERE operation_id=?` *outside* the write transaction, then inserts. Two near-simultaneous calls with the same `operation_id` (e.g. an MCP client retry) will both pass the pre-check and the second `INSERT` will raise `sqlite3.IntegrityError` (operation_id is UNIQUE) instead of gracefully returning the already-committed record, defeating the purpose of the idempotency key exactly in the retry scenario it exists for.

**6. Preview shown to the user can understate what a later `--yes`/`confirm=true` call actually deletes**
`store.py: forget`/`forget_scope` recompute `preview_forget(...)` fresh immediately before deleting, rather than reusing a snapshot. Between a `preview-forget` CLI/MCP call and the follow-up confirmed call, new memories deriving from the same lineage can be added (by a concurrently running agent) and will be swept into the deletion the user never actually saw or approved. The recompute-on-execute pattern is good for correctness of the delete itself, but it breaks the "confirm what you saw" guarantee the two-step UX implies.

**7. `_resolve_sources` does not require sources to be `active`**
`store.py: MemoryStore._resolve_sources` looks up any `memory_id` regardless of `status`, so a `fact`/`summary` can be silently derived from an already-superseded (corrected) version, embedding stale/incorrect provenance without any signal to the caller.

## Strengths

- **Embedding compatibility guard is solid**: `embedding_identity`'s sentinel-vector behavior fingerprint plus the full mismatch report in `initialize_or_validate` (`database.py`) correctly refuses to silently mix vector spaces — verified by `test_manifest_rejects_different_embedding_space`.
- **Two-phase commit-then-embed** (`remember`/`correct` commit `pending` in one `IMMEDIATE` transaction, embed in a second) correctly preserves raw content even when the embedder throws, per `test_raw_commit_survives_embedding_failure_and_retries`.
- **Correction/provenance model is well-built**: single-active-version-per-lineage enforced by a partial unique index (`memories_one_active_lineage_idx`), and generation-based cycle prevention in the provenance DAG is simple and correct.
- **Deletion cascade + verification** (`_build_delete_preview`, `_delete_preview`) correctly walks lineage → derived descendants transitively and cross-scope, then verifies post-commit absence — genuinely privacy-respecting design, well covered by tests.
- **Scope isolation for recall** is enforced at the type level (`recall` requires the primary scope to be `private`; shared pools are always pinned to the same subject/environment, never free-floating) and untrusted-content labelling (`context_bundle`, `trust_label`) is a good prompt-injection mitigation for recalled data.
- **Backup uses SQLite's online backup API correctly** under WAL with a post-copy `PRAGMA integrity_check`.

## Ship / No-Ship

**No-ship as-is for the export/backup/restore surface; ship the remember/recall/correct/forget core.** Findings 1–3 are concrete data-loss and privacy-leak defects, not theoretical: a default-argument MCP export call leaks everything, `restore` has no destructive-action guard at all (the one place in this codebase that most needs one, given `forget` already sets the right precedent with `--yes`/`confirm`), and file permissions have a real disclosure window contradicting the stated security contract. These are small, mechanical fixes (require explicit scope for export, add `--yes`/confirm + destination-must-not-exist check to restore, pre-create files at `0600`) and should block a private release until patched. The core memory lifecycle (remember/recall/correct/forget) is well-designed and well-tested and does not need to wait on this.
