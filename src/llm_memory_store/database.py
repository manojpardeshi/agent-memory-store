"""SQLite connection, schema, transaction, and backup helpers."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

import sqlite_vec

from .embeddings import EmbeddingIdentity

SCHEMA_VERSION = 1


class StoreCompatibilityError(RuntimeError):
    """Raised when a runtime cannot safely use an existing store."""


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds")


def _secure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with suppress(OSError):
        path.parent.chmod(0o700)


def _secure_create(path: Path) -> None:
    """Reserve a new sensitive file with owner-only permissions."""

    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    os.close(descriptor)


def _secure_create_if_missing(path: Path) -> None:
    with suppress(FileExistsError):
        _secure_create(path)
    with suppress(OSError):
        path.chmod(0o600)


def load_vector_extension(connection: sqlite3.Connection) -> None:
    connection.enable_load_extension(True)
    try:
        sqlite_vec.load(connection)
    finally:
        connection.enable_load_extension(False)


def connect_database(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        if not path.is_file():
            raise FileNotFoundError(path)
        connection = sqlite3.connect(
            f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5.0, isolation_level=None
        )
    else:
        _secure_parent(path)
        _secure_create_if_missing(path)
        connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    load_vector_extension(connection)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    if read_only:
        connection.execute("PRAGMA query_only=ON")
    else:
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA journal_mode=WAL")
    return connection


def _manifest_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='store_manifest'"
    ).fetchone()
    return row is not None


def initialize_or_validate(
    connection: sqlite3.Connection,
    identity: EmbeddingIdentity,
    *,
    allow_initialize: bool = True,
) -> sqlite3.Row:
    if not _manifest_exists(connection):
        if not allow_initialize:
            raise StoreCompatibilityError("read-only store manifest is missing")
        _initialize_schema(connection, identity)
    row = connection.execute("SELECT * FROM store_manifest WHERE id=1").fetchone()
    if row is None:
        raise StoreCompatibilityError("store manifest is missing")
    expected = identity.to_dict()
    checks = {
        "embedding_provider": expected["provider"],
        "model_name": expected["model_name"],
        "model_revision": expected["model_revision"],
        "dimension": expected["dimension"],
        "normalized": int(bool(expected["normalized"])),
        "distance_metric": expected["distance_metric"],
        "behavior_fingerprint": expected["behavior_fingerprint"],
    }
    mismatches = {
        field: {"store": row[field], "runtime": value}
        for field, value in checks.items()
        if row[field] != value
    }
    if row["schema_version"] != SCHEMA_VERSION:
        mismatches["schema_version"] = {
            "store": row["schema_version"],
            "runtime": SCHEMA_VERSION,
        }
    if mismatches:
        detail = ", ".join(
            f"{field}=store:{values['store']!r}/runtime:{values['runtime']!r}"
            for field, values in mismatches.items()
        )
        raise StoreCompatibilityError(f"store/runtime compatibility mismatch: {detail}")
    return row


def _initialize_schema(connection: sqlite3.Connection, identity: EmbeddingIdentity) -> None:
    dimension = identity.dimension
    if dimension <= 0:
        raise ValueError("embedding dimension must be positive")
    connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
    connection.executescript(
        """
        BEGIN IMMEDIATE;
        CREATE TABLE store_manifest (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            schema_version INTEGER NOT NULL,
            store_id TEXT NOT NULL UNIQUE,
            embedding_provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_revision TEXT NOT NULL,
            runtime_version TEXT NOT NULL,
            dimension INTEGER NOT NULL CHECK (dimension > 0),
            normalized INTEGER NOT NULL CHECK (normalized IN (0, 1)),
            distance_metric TEXT NOT NULL CHECK (distance_metric = 'cosine'),
            behavior_fingerprint TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE scopes (
            id INTEGER PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('private', 'shared')),
            subject TEXT NOT NULL CHECK (length(subject) BETWEEN 1 AND 256),
            environment TEXT NOT NULL CHECK (length(environment) BETWEEN 1 AND 256),
            owner TEXT NOT NULL CHECK (length(owner) BETWEEN 1 AND 256),
            created_at TEXT NOT NULL,
            UNIQUE(kind, subject, environment, owner)
        );
        CREATE INDEX scopes_subject_environment_idx
            ON scopes(subject, environment, kind);

        CREATE TABLE memories (
            id INTEGER PRIMARY KEY,
            memory_id TEXT NOT NULL UNIQUE,
            lineage_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version >= 1),
            scope_id INTEGER NOT NULL REFERENCES scopes(id) ON DELETE RESTRICT,
            kind TEXT NOT NULL CHECK (
                kind IN ('turn', 'fact', 'preference', 'summary', 'event')
            ),
            role TEXT CHECK (role IS NULL OR role IN ('user', 'assistant', 'system', 'tool')),
            content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 100000),
            content_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('active', 'superseded')),
            generation INTEGER NOT NULL CHECK (generation >= 0),
            embedding_status TEXT NOT NULL CHECK (
                embedding_status IN ('pending', 'ready', 'failed')
            ),
            embedding_error TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
            operation_id TEXT UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            supersedes_id INTEGER REFERENCES memories(id) ON DELETE SET NULL,
            occurred_at TEXT,
            UNIQUE(lineage_id, version),
            CHECK (
                (kind = 'turn' AND role IS NOT NULL)
                OR (kind <> 'turn' AND role IS NULL)
            )
        );
        CREATE UNIQUE INDEX memories_one_active_lineage_idx
            ON memories(lineage_id) WHERE status = 'active';
        CREATE INDEX memories_scope_status_idx
            ON memories(scope_id, status, expires_at);
        CREATE INDEX memories_embedding_status_idx
            ON memories(embedding_status, status);
        CREATE INDEX memories_lineage_idx ON memories(lineage_id, version);

        CREATE TABLE memory_sources (
            child_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            source_id INTEGER NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
            relation TEXT NOT NULL CHECK (
                relation IN ('derived_from', 'summarizes', 'supersedes', 'observed_from')
            ),
            PRIMARY KEY(child_id, source_id, relation),
            CHECK (child_id <> source_id)
        );
        CREATE INDEX memory_sources_source_idx ON memory_sources(source_id, child_id);
        COMMIT;
        """
    )
    connection.execute(
        f"""
        CREATE VIRTUAL TABLE memory_vectors USING vec0(
            embedding float[{dimension}] distance_metric=cosine,
            scope_id integer partition key
        )
        """
    )
    connection.execute(
        """
        INSERT INTO store_manifest(
            id, schema_version, store_id, embedding_provider, model_name,
            model_revision, runtime_version, dimension, normalized,
            distance_metric, behavior_fingerprint, created_at
        ) VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SCHEMA_VERSION,
            str(uuid.uuid4()),
            identity.provider,
            identity.model_name,
            identity.model_revision,
            identity.runtime_version,
            identity.dimension,
            int(identity.normalized),
            identity.distance_metric,
            identity.behavior_fingerprint,
            utc_now(),
        ),
    )


def occurred_at_column_exists(connection: sqlite3.Connection) -> bool:
    return any(
        row["name"] == "occurred_at"
        for row in connection.execute("PRAGMA table_info(memories)").fetchall()
    )


def ensure_occurred_at_column(connection: sqlite3.Connection) -> bool:
    """Add the optional ``occurred_at`` column to a store created before it existed.

    Additive and nullable, so ``SCHEMA_VERSION`` is unchanged and older runtimes, which name
    their insert columns explicitly, keep working and simply leave it empty.
    """

    if occurred_at_column_exists(connection):
        return True
    with immediate_transaction(connection):
        if not occurred_at_column_exists(connection):
            connection.execute("ALTER TABLE memories ADD COLUMN occurred_at TEXT")
    return True


KEYWORD_INDEX_TABLE = "memory_keywords"

# The keyword index is derived data: it holds no text the memories table does not, can be
# rebuilt from it at any time, and is maintained by triggers so every write path, including
# older runtimes writing to an indexed store, keeps it in sync. It is additive and does not
# change SCHEMA_VERSION. FTS5 secure-delete is required so forgetting a memory physically
# removes its terms from the index instead of leaving them behind a delete marker.
_KEYWORD_INDEX_DDL = (
    f"""
    CREATE VIRTUAL TABLE {KEYWORD_INDEX_TABLE} USING fts5(
        content, content='memories', content_rowid='id', tokenize='porter unicode61'
    )
    """,
    f"INSERT INTO {KEYWORD_INDEX_TABLE}({KEYWORD_INDEX_TABLE}, rank) VALUES('secure-delete', 1)",
    f"""
    CREATE TRIGGER {KEYWORD_INDEX_TABLE}_after_insert AFTER INSERT ON memories BEGIN
        INSERT INTO {KEYWORD_INDEX_TABLE}(rowid, content) VALUES (new.id, new.content);
    END
    """,
    f"""
    CREATE TRIGGER {KEYWORD_INDEX_TABLE}_after_delete AFTER DELETE ON memories BEGIN
        INSERT INTO {KEYWORD_INDEX_TABLE}({KEYWORD_INDEX_TABLE}, rowid, content)
        VALUES ('delete', old.id, old.content);
    END
    """,
    f"""
    CREATE TRIGGER {KEYWORD_INDEX_TABLE}_after_update AFTER UPDATE OF content ON memories BEGIN
        INSERT INTO {KEYWORD_INDEX_TABLE}({KEYWORD_INDEX_TABLE}, rowid, content)
        VALUES ('delete', old.id, old.content);
        INSERT INTO {KEYWORD_INDEX_TABLE}(rowid, content) VALUES (new.id, new.content);
    END
    """,
    f"INSERT INTO {KEYWORD_INDEX_TABLE}({KEYWORD_INDEX_TABLE}) VALUES('rebuild')",
)

_keyword_index_supported: bool | None = None


def keyword_index_supported() -> bool:
    """Whether this SQLite build has FTS5 with secure-delete (SQLite 3.44 or newer)."""

    global _keyword_index_supported
    if _keyword_index_supported is None:
        probe = sqlite3.connect(":memory:")
        try:
            probe.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
            probe.execute("INSERT INTO probe(probe, rank) VALUES('secure-delete', 1)")
            _keyword_index_supported = True
        except sqlite3.OperationalError:
            _keyword_index_supported = False
        finally:
            probe.close()
    return _keyword_index_supported


def keyword_index_exists(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (KEYWORD_INDEX_TABLE,)
    ).fetchone()
    return row is not None


def ensure_keyword_index(connection: sqlite3.Connection) -> bool:
    """Create and backfill the keyword index if absent; return whether it is available.

    Leaves the store unchanged and returns False when this SQLite build cannot provide a
    secure-delete FTS5 index, so hybrid recall is simply unavailable there.
    """

    if keyword_index_exists(connection):
        return True
    if not keyword_index_supported():
        return False
    with immediate_transaction(connection):
        # Re-check under the write lock: another process may have just created it.
        if not keyword_index_exists(connection):
            for statement in _KEYWORD_INDEX_DDL:
                connection.execute(statement)
    return True


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    else:
        connection.execute("COMMIT")


def consistent_backup(
    source: sqlite3.Connection, destination: Path, *, overwrite: bool = False
) -> None:
    _secure_parent(destination)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"backup destination already exists: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        target = sqlite3.connect(temporary)
        try:
            source.backup(target)
        finally:
            target.close()
        temporary.chmod(0o600)
        check = sqlite3.connect(temporary)
        try:
            load_vector_extension(check)
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"backup integrity check failed: {result}")
        finally:
            check.close()
        if destination.exists() and not overwrite:
            raise FileExistsError(f"backup destination already exists: {destination}")
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def secure_write_text(destination: Path, content: str, *, overwrite: bool = False) -> None:
    """Atomically write a sensitive text artifact without a permissive creation window."""

    _secure_parent(destination)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"destination already exists: {destination}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"destination already exists: {destination}")
        os.replace(temporary, destination)
        destination.chmod(0o600)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def restore_database(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if source.resolve() == destination.resolve():
        raise ValueError("source and destination must differ")
    _secure_parent(destination)
    if destination.exists():
        raise FileExistsError(
            f"restore destination already exists: {destination}; restore into a new path"
        )
    _secure_create(destination)
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    target_connection = sqlite3.connect(destination)
    try:
        load_vector_extension(source_connection)
        result = source_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"source integrity check failed: {result}")
        source_connection.backup(target_connection)
    except BaseException:
        target_connection.close()
        source_connection.close()
        with suppress(FileNotFoundError):
            destination.unlink()
        raise
    else:
        target_connection.close()
        source_connection.close()
        destination.chmod(0o600)
