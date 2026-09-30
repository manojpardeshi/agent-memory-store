"""find_by_metadata: exact-scope metadata lookup that never widens access.

Pins isolation (other scopes invisible), expiry and supersession semantics matching
recall, input validation that keeps the JSON path parameter-bound, and that only
matching rows are fetched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from llm_memory_store import Scope


def _scope(owner: str = "agent") -> Scope:
    return Scope.private("tester", "test", owner)


def _turns(store, scope, session: str, count: int, **extra):
    return [
        store.remember_turn(
            f"{session} message {i}", "user", scope,
            metadata={"session_id": session, "message_index": i, **extra},
        )
        for i in range(count)
    ]


def test_returns_only_matching_session_in_insertion_order(store) -> None:
    scope = _scope()
    wanted = _turns(store, scope, "s1", 4)
    _turns(store, scope, "s2", 3)
    found = store.find_by_metadata(scope, {"session_id": "s1"})
    assert [r.memory_id for r in found] == [r.memory_id for r in wanted]


def test_multiple_filters_combine_with_and(store) -> None:
    scope = _scope()
    _turns(store, scope, "s1", 4)
    found = store.find_by_metadata(scope, {"session_id": "s1", "message_index": 2})
    assert [r.metadata["message_index"] for r in found] == [2]


def test_other_scopes_are_never_visible(store) -> None:
    _turns(store, _scope("a"), "shared-id", 2)
    _turns(store, _scope("b"), "shared-id", 5)
    assert len(store.find_by_metadata(_scope("a"), {"session_id": "shared-id"})) == 2
    assert store.find_by_metadata(_scope("never-created"), {"session_id": "shared-id"}) == []


def test_expired_memories_are_excluded_by_default(store) -> None:
    scope = _scope()
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    store.remember("fact", "expired fact", scope, metadata={"tag": "t"}, expires_at=past)
    store.remember("fact", "live fact", scope, metadata={"tag": "t"}, expires_at=future)
    assert [r.content for r in store.find_by_metadata(scope, {"tag": "t"})] == ["live fact"]
    assert len(store.find_by_metadata(scope, {"tag": "t"}, include_expired=True)) == 2


def test_superseded_memories_follow_the_flag(store) -> None:
    scope = _scope()
    original = store.remember("fact", "old value", scope, metadata={"tag": "t"})
    store.correct(original.memory_id, "new value")
    active = store.find_by_metadata(scope, {"tag": "t"})
    assert [r.content for r in active] == ["new value"]
    assert len(store.find_by_metadata(scope, {"tag": "t"}, include_superseded=True)) == 2


def test_boolean_values_match_json_booleans(store) -> None:
    scope = _scope()
    store.remember("fact", "flagged", scope, metadata={"flag": True})
    store.remember("fact", "unflagged", scope, metadata={"flag": False})
    assert [r.content for r in store.find_by_metadata(scope, {"flag": True})] == ["flagged"]


@pytest.mark.parametrize("bad_key", ["", "a.b", "$.x", "x') OR 1=1 --", "1abc", "a" * 65])
def test_rejects_keys_that_are_not_plain_identifiers(store, bad_key) -> None:
    with pytest.raises(ValueError):
        store.find_by_metadata(_scope(), {bad_key: "x"})


def test_rejects_empty_filters_and_non_scalar_values(store) -> None:
    with pytest.raises(ValueError):
        store.find_by_metadata(_scope(), {})
    with pytest.raises(TypeError):
        store.find_by_metadata(_scope(), {"session_id": ["a"]})
