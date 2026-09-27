"""The batched record fetch must be indistinguishable from per-record fetches.

`list_memories` and export previously issued two queries per record. These tests pin
both the output (field for field, in order, including superseded rows, provenance
sources, and metadata) and the cost (query count independent of record count).
"""

from __future__ import annotations

from llm_memory_store import Scope


def _scope() -> Scope:
    return Scope.private("tester", "test", "agent")


def _populate(store, count: int) -> None:
    scope = _scope()
    records = [
        store.remember("fact", f"synthetic fact number {index}", scope, metadata={"index": index})
        for index in range(count)
    ]
    # Derive from an active fact first, then supersede a different one, so the set holds
    # a provenance edge and a superseded row at the same time.
    store.remember(
        "summary",
        "summary derived from the second fact",
        scope,
        source_memory_ids=[records[1].memory_id],
    )
    store.correct(records[0].memory_id, "synthetic fact number 0, corrected")


def test_batched_list_matches_per_record_fetch_exactly(store) -> None:
    _populate(store, 12)
    listed = store.list_memories(_scope(), include_superseded=True)
    ids = [
        int(row["id"])
        for row in store.connection.execute(
            "SELECT id FROM memories ORDER BY id DESC LIMIT 100"
        ).fetchall()
    ]
    one_by_one = [store._records_by_internal_ids([i])[0] for i in ids]
    assert listed == one_by_one
    assert any(r.status == "superseded" for r in listed)
    assert any(r.source_memory_ids for r in listed)


def test_missing_internal_id_still_raises_key_error(store) -> None:
    import pytest

    with pytest.raises(KeyError):
        store._record_by_internal_id(987654)


def test_list_memories_query_count_does_not_grow_with_records(store) -> None:
    _populate(store, 60)
    statements: list[str] = []
    store.connection.set_trace_callback(statements.append)
    try:
        store.list_memories(_scope(), include_superseded=True, limit=5)
        small = len(statements)
        statements.clear()
        store.list_memories(_scope(), include_superseded=True, limit=60)
        large = len(statements)
    finally:
        store.connection.set_trace_callback(None)
    assert large == small, (small, large)
