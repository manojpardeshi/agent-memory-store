# Claude MVP Architecture Review

- Date: 2026-07-15
- Reviewer: Claude Sonnet via the local Claude Code CLI (`claude -p`)
- Mode: Independent, no-tools architecture review
- Status: Advisory input; recommendations are not decisions unless accepted in the architecture decision log

## Prompt

> You are an independent principal architect. Review this proposed MVP only from the requirements embedded here; do not use tools. A solo developer is building a Python, personal, local-first, provider-neutral LLM memory store. It must use one embedded portable datastore, local embeddings, MCP over stdio and a thin Python API. It must synchronously and durably commit raw turns; optionally derive typed facts, preferences and summaries without an always-on daemon; recall by semantic similarity plus recency; default to private subject/environment/agent scope with explicit shared pools; correct through versioned supersession; hard-delete row data, vectors and linked versions with verification; export JSON; and perform consistent backup/restore. Scale is 1 user, a handful of agents, under 50K records, p95 recall target 200ms, no network/cloud/auth/UI/document RAG. Current proposals are SQLite plus sqlite-vec exact KNN, one embedding model per store, OS filesystem security, and private development before Codeberg publication. Produce no more than 3000 words with concrete recommendations: minimal vertical slice; schema/invariants; Python and MCP operations; storage choice; local embedding choice and manifest; processing states; exact scope and delete semantics; security risks; tests; package layout; ADRs to accept/reject/experiment; and over-engineering to avoid.

## Response

# Architecture Review: Local-First LLM Memory Store

## Verdict on core proposals

**SQLite + sqlite-vec exact KNN: Accept.** At <50K records with 384–1024 dim vectors, exact brute-force KNN in sqlite-vec is fast enough (single-digit ms) and avoids ANN index tuning, rebuild-on-delete complexity, and recall/precision tradeoffs you don't need at this scale. One file, one transaction log, one backup unit. Correct call.

**One embedding model per store: Accept, with a hard version pin.** Mixing embedding models in one vector space silently corrupts similarity search — cosine distance across two models' spaces is meaningless. Pin the model + revision in a manifest row; refuse to write vectors from a different model without an explicit re-embed migration.

**OS filesystem security: Accept for MVP, document the ceiling.** No auth/network is in scope, so OS file permissions (0600 on the DB file, 0700 on the directory) are the entire security boundary. This is fine *if* stated explicitly as a boundary, not deferred.

**Private dev before Codeberg publication: Accept**, but treat license, `.gitattributes` for the SQLite file (must never be committed), and secrets scanning as day-one hygiene, not launch-day scramble.

---

## Minimal vertical slice

Cut everything except this path, and ship it before touching anything else:

1. `remember_turn(text, role, scope)` → synchronous durable INSERT into `turns` (WAL commit, fsync).
2. `recall(query, scope, k)` → embed query, exact KNN over `vectors` joined to `turns`, blended with recency decay, return ranked results.
3. `forget(id)` → hard delete row + vector + verify absence.
4. MCP stdio server exposing exactly these three tools plus `export`.

No summaries, no fact extraction, no supersession, no shared pools in v0. Those are v1 additions once the spine is proven under real use. This is the single biggest risk to a solo dev's timeline: the "optional" derived-memory features (facts, preferences, summaries) are where scope creep lives, and they're explicitly *optional* in your own requirements — so build the raw-turn spine first, prove p95 recall, then layer derivation as a batch job triggered by CLI/MCP call, never a daemon.

---

## Schema and invariants

```sql
CREATE TABLE store_manifest (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  embedding_model TEXT NOT NULL,
  embedding_dim INTEGER NOT NULL,
  embedding_revision TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE scopes (
  scope_id TEXT PRIMARY KEY,        -- e.g. 'subject:person', 'agent:coder', 'shared:team-x'
  kind TEXT NOT NULL CHECK (kind IN ('subject','environment','agent','shared')),
  is_shared INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope_id TEXT NOT NULL REFERENCES scopes(scope_id),
  role TEXT NOT NULL,               -- user|assistant|system
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,         -- ISO8601, UTC
  deleted_at TEXT                   -- NULL unless hard-deleted (tombstone before purge)
);

CREATE VIRTUAL TABLE vectors USING vec0(
  turn_id INTEGER PRIMARY KEY,
  embedding FLOAT[N]                -- N = manifest.embedding_dim, enforced at write time
);

CREATE TABLE derived_items (            -- facts, preferences, summaries
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL CHECK (kind IN ('fact','preference','summary')),
  scope_id TEXT NOT NULL REFERENCES scopes(scope_id),
  content TEXT NOT NULL,
  source_turn_ids TEXT NOT NULL,     -- JSON array, provenance
  version INTEGER NOT NULL DEFAULT 1,
  supersedes_id INTEGER REFERENCES derived_items(id),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','deleted')),
  created_at TEXT NOT NULL
);

CREATE TABLE derived_vectors USING vec0(
  item_id INTEGER PRIMARY KEY,
  embedding FLOAT[N]
);
```

**Invariants to enforce in application code (not achievable purely in SQLite constraints):**

- Every `turns` row has exactly one `vectors` row before the transaction that inserts it commits — write both in one `BEGIN IMMEDIATE` transaction, or the turn write fails. No orphaned turns without vectors, no orphaned vectors without turns.
- `embedding_dim` in the manifest is immutable after first write; changing embedding models requires a new store or an explicit, logged re-embedding migration that rewrites every vector.
- Supersession is append-only: superseding an item never mutates the old row's `content`, only its `status` and creates a new row pointing back via `supersedes_id`. This gives you a correction audit trail for free.
- `deleted_at` tombstones exist only transiently, inside the delete transaction, to sequence FK cleanup — not as a soft-delete feature. Requirement is hard delete; don't let a tombstone column become a de facto soft-delete leak.

---

## Python API and MCP operations

Thin means the MCP layer is a dispatch shim, not where logic lives. Core logic lives in a plain Python package importable without MCP at all (useful for tests, and for a future non-MCP consumer).

```python
class MemoryStore:
    def remember(self, content: str, role: str, scope: ScopeId) -> TurnId: ...
    def recall(self, query: str, scope: ScopeId, k: int = 10,
               recency_halflife_days: float = 14.0) -> list[RecallResult]: ...
    def derive(self, scope: ScopeId, kind: Literal["fact","preference","summary"]) -> list[DerivedItem]: ...
    def correct(self, item_id: int, new_content: str) -> DerivedItem: ...  # supersede
    def forget(self, target: TurnId | DerivedItemId) -> DeleteReceipt: ...
    def export(self, scope: ScopeId | None = None) -> dict: ...  # JSON
    def backup(self, dest_path: Path) -> None: ...
    def restore(self, src_path: Path) -> None: ...
```

MCP tools map 1:1 onto these — `memory.remember`, `memory.recall`, `memory.derive`, `memory.correct`, `memory.forget`, `memory.export`. Do not add MCP-only conveniences (batch variants, pagination cursors, streaming) until a real client needs them; stdio MCP is inherently single-client, single-request-at-a-time in practice, so keep it boringly synchronous.

**Recall scoring**: compute `score = α * cosine_sim + (1-α) * exp(-age_days / halflife)`, α configurable, default ~0.7. Keep this formula in one function, tested independently of the DB, so you can tune it without touching storage code.

---

## Local embedding choice and manifest

For CPU-only, no-network, <50K records: a compact sentence-transformers model run via `onnxruntime` or `fastembed` (which wraps ONNX models with no torch dependency) is the right tradeoff — avoids pulling in the PyTorch stack for a personal tool. Concretely: **BAAI/bge-small-en-v1.5** (384-dim) or **all-MiniLM-L6-v2** (384-dim) are both well-tested, small (~130MB), and fast enough that embedding is not your bottleneck at this scale — retrieval will dominate p95, and 384-dim exact KNN over 50K rows is trivially under 200ms.

Manifest must record: model name, revision/commit hash of the weights, dim, and a normalization flag (whether vectors are L2-normalized before storage — do this, it makes cosine distance a dot product, which sqlite-vec computes faster). Store this as the single row in `store_manifest` above; check it on every store open and fail loudly if the runtime model doesn't match.

---

## Processing states

Derivation (facts/preferences/summaries) needs an explicit state machine since there's no daemon to retry silently:

```text
pending → processing → done
                     ↘ failed (retryable, logged with error)
```

Model this as a `derivation_jobs` table (`turn_id_range`, `kind`, `state`, `attempts`, `last_error`), driven by an explicit CLI/MCP `derive` call — never a background thread. This matches your no-daemon constraint and makes failures visible and re-runnable instead of silently retried into a corrupted state. Idempotency matters here: re-running `derive` over an already-processed range should be a no-op or produce a new superseding version, never a duplicate.

---

## Scope and delete semantics

**Scope model**: every row belongs to exactly one `scope_id`. Default scope for any write is `subject:<default-subject>` unless caller explicitly names a `shared:*` scope. Recall queries default to the caller's own scope(s) and must explicitly opt into cross-scope/shared search — never implicitly leak private-scope data into a shared-pool query or vice versa. This is a security property, not just a UX default, so enforce it in `MemoryStore.recall` itself (a mandatory scope filter clause), not as an optional parameter with an unsafe default.

**Hard delete with verification** — this is the part worth being pedantic about, since "verified" delete is explicitly required:

```python
def forget(self, target) -> DeleteReceipt:
    with self._db.begin_immediate():
        turn_id = self._resolve(target)
        self._db.execute("DELETE FROM vectors WHERE turn_id = ?", (turn_id,))
        self._db.execute("DELETE FROM turns WHERE id = ?", (turn_id,))
        # cascade: any derived_items whose source_turn_ids include this id
        affected = self._find_derived_referencing(turn_id)
        for item in affected:
            self._db.execute("DELETE FROM derived_vectors WHERE item_id = ?", (item.id,))
            self._db.execute("DELETE FROM derived_items WHERE id = ?", (item.id,))
    # verification, post-commit, separate read transaction
    assert self._db.execute("SELECT 1 FROM turns WHERE id=?", (turn_id,)).fetchone() is None
    assert self._db.execute("SELECT 1 FROM vectors WHERE turn_id=?", (turn_id,)).fetchone() is None
    return DeleteReceipt(turn_id=turn_id, cascaded_items=[i.id for i in affected], verified=True)
```

Two things matter: (1) the cascade must walk `derived_items.source_turn_ids` so a corrected/summarized fact doesn't outlive the raw turn it was derived from — otherwise "hard delete" is a lie; (2) verification is a real post-commit SELECT, not just "no exception was thrown." On WAL mode, also run `PRAGMA wal_checkpoint(TRUNCATE)` after deletes if you need the deleted bytes actually gone from disk (relevant if "verified" is meant to include forensic non-recoverability — clarify this with the user before implementing, since it's a meaningfully bigger job than a logical delete, and see the security risk below).

---

## Security risks

1. **"OS filesystem security" doesn't cover data-at-rest if the disk is unencrypted or backed up unencrypted to a third party (Time Machine to a cloud drive, etc.).** State this ceiling explicitly to the user; it's outside MVP scope but must not be silently assumed away.
2. **Hard delete vs. SQLite's actual on-disk behavior**: `DELETE` does not zero bytes; VACUUM/checkpoint can still leave data in freelist pages or WAL files until overwritten. If "verified delete" needs to mean forensically gone (not just query-invisible), you need `PRAGMA secure_delete=ON` plus periodic `VACUUM`, and even then the WAL and any OS-level backups (Time Machine, cloud sync) may retain copies. Decide and document which guarantee you're actually making.
3. **MCP stdio trust boundary**: whatever process spawns your MCP server inherits full read/write/delete access with no auth. That's appropriate for a personal single-user tool, but if you ever run multiple agents concurrently against the same store, add a file lock (SQLite's own locking suffices) — don't build auth, just don't assume single-writer safety you haven't verified.
4. **Embedding model supply chain**: pulling model weights at first run means a network dependency and a trust decision (weights from HF hub). Pin a specific revision hash in the manifest and verify it, or vendor the model file, so "local-first" isn't silently violated by an unpinned auto-download.
5. **Export command is a full data-exfiltration path by design** — that's the point of `export`, but make sure it never becomes the default output destination for logs/errors (i.e., don't accidentally dump full turn content into stderr/debug logs, since anything in `docs/` or `logs/` in this repo could end up committed).

---

## Tests

- **Durability**: kill the process (SIGKILL) mid-`remember` and assert on restart either the full turn+vector exists or neither does — never a half-write. Requires actually testing WAL commit atomicity, not just unit-testing the Python call.
- **Invariant tests**: no turn without a paired vector; no vector without a paired turn; manifest embedding_dim matches every vector's length.
- **Scope isolation**: recall from scope A never returns rows from scope B, including under shared-pool configuration, with an explicit test for the *default-private* case.
- **Delete verification**: after `forget`, all three assertions (turn gone, vector gone, cascaded derived items gone) plus a directly-run `SELECT COUNT(*)` sanity check, not just relying on the store's own claimed receipt.
- **Recall correctness at scale**: seed ~50K synthetic rows, assert p95 recall latency <200ms on representative hardware — this is a real perf test, not a mock.
- **Backup/restore round-trip**: backup, mutate original, restore, assert restored state matches the backup snapshot exactly (byte-for-byte on the DB file, or row-for-row via export diff).
- **Model mismatch guard**: attempt to open a store with a different embedding model configured than the manifest records; assert a loud failure, not silent corruption.

---

## Package layout

```text
memstore/
  __init__.py
  core/
    store.py          # MemoryStore — all logic, no MCP awareness
    scoring.py         # recall scoring (cosine + recency), pure functions
    schema.sql
    migrations/
  embed/
    manifest.py
    provider.py         # wraps fastembed/onnxruntime, one implementation
  mcp/
    server.py           # stdio server, dispatch only, no logic
  cli.py                # thin wrapper for derive/backup/export, no logic
tests/
  test_durability.py
  test_invariants.py
  test_scope_isolation.py
  test_delete_verification.py
  test_recall_perf.py
  test_backup_restore.py
```

Keep `core/` importable with zero MCP dependency — that's what "thin Python API" should mean structurally, not just descriptively.

---

## ADRs

**Accept**: SQLite + sqlite-vec exact KNN; one embedding model per store with manifest pin; append-only supersession for corrections; explicit-scope-required for any cross-scope/shared recall; no daemon, derivation as explicit batch call; hard delete implemented as cascade-and-verify transaction.

**Reject**: any ANN index (HNSW/IVF) — unneeded complexity and rebuild cost at this scale; soft-delete/tombstone as a permanent feature; multi-model embedding support in a single store; concurrent multi-writer support; any auth/network layer.

**Experiment** (spike before committing): `PRAGMA secure_delete` + VACUUM cadence for genuine forensic delete guarantees, if the user actually needs that stronger claim; whether recency decay should be configurable per-scope or global-only; whether derived-item re-embedding on correction should be synchronous (simpler) or queued (only if correction volume ever becomes non-trivial — unlikely at this scale, so default to synchronous and only revisit if proven slow).

---

## Over-engineering to avoid

Don't build: a plugin architecture for swappable vector backends (you have one datastore, by design); a generic "memory type" system beyond turns/facts/preferences/summaries; async/concurrent access support (single user, single process); a query DSL for recall filters beyond scope+k+recency; migration tooling more elaborate than numbered SQL scripts (schema_version in the manifest is enough); any caching layer (SQLite page cache plus <50K rows needs nothing extra); and — the biggest trap — a full daemon-like background derivation scheduler disguised as a "job queue," when an explicit CLI/MCP-triggered batch call satisfies the requirement completely.
