"""Invariant tests for the within-session-expansion-v1 selection primitives.

Every test here encodes a contract bound: no new sessions, baseline retained as a prefix,
nearest-neighbour expansion under a cap, header preserved through span reduction, and
budget fitting that reduces before it drops and never drops a baseline item.
"""

from __future__ import annotations

from scripts.within_session_expansion import (
    context_json_bytes,
    expand_within_sessions,
    fit_to_budget,
    reduce_to_span,
    split_header,
)


def _msg(mid: str, session: str, index: int, body: str = "x") -> dict:
    header = f'[longmemeval-source]{{"session_id":"{session}","message_index":{index}}}'
    return {
        "memory_id": mid,
        "content": f"{header}\n{body}",
        "memory": f"{header}\n{body}",
        "metadata": {"session_id": session, "message_index": index},
    }


def test_expansion_picks_nearest_to_anchor_under_cap_and_skips_baseline() -> None:
    baseline = [_msg("b1", "s", 5)]
    session = {"s": [_msg(f"m{i}", "s", i) for i in range(0, 12)]}
    out = expand_within_sessions(baseline, session, cap=4)
    assert [m["metadata"]["message_index"] for m in out] == [4, 6, 3, 7]
    assert all(m["expansion"]["anchor_message_index"] == 5 for m in out)
    assert "b1" not in {m["memory_id"] for m in out}


def test_expansion_never_introduces_a_session_absent_from_baseline() -> None:
    baseline = [_msg("b1", "s", 2)]
    session = {"s": [_msg("m1", "s", 3)], "other": [_msg("o1", "other", 0)]}
    out = expand_within_sessions(baseline, session, cap=4)
    assert {m["metadata"]["session_id"] for m in out} == {"s"}


def test_expansion_anchor_is_highest_ranked_baseline_item_per_session() -> None:
    baseline = [_msg("b1", "s", 9), _msg("b2", "s", 1)]  # rank 1 anchors at index 9
    session = {"s": [_msg(f"m{i}", "s", i) for i in range(0, 12)]}
    out = expand_within_sessions(baseline, session, cap=2)
    assert [m["metadata"]["message_index"] for m in out] == [8, 10]


def test_split_header_round_trips_and_tolerates_missing_header() -> None:
    header, body = split_header('[longmemeval-source]{"a":1}\nhello world')
    assert header == '[longmemeval-source]{"a":1}' and body == "hello world"
    assert split_header("plain text") == ("", "plain text")


def test_reduce_to_span_keeps_header_and_returns_unchanged_when_short() -> None:
    content = '[longmemeval-source]{"a":1}\nShort body.'
    assert reduce_to_span(content, "anything", max_body_chars=100) == content


def test_reduce_to_span_selects_the_query_dense_window() -> None:
    body = (
        "Here is a long recipe for chocolate cake with many steps. "
        "Preheat the oven and grease the pan carefully. "
        "I spent 500 dollars on the designer handbag last week. "
        "Then fold the batter and bake for forty minutes."
    )
    content = f'[longmemeval-source]{{"a":1}}\n{body}'
    out = reduce_to_span(content, "how much did I spend on the handbag", max_body_chars=70)
    header, span = split_header(out)
    assert header == '[longmemeval-source]{"a":1}'
    assert "handbag" in span
    assert "chocolate" not in span
    assert len(span.replace("… ", "").replace(" …", "")) <= 70


def test_fit_to_budget_reduces_expansions_before_baseline_and_never_drops_baseline() -> None:
    big = "word " * 400
    baseline = [_msg("b1", "s", 0, big)]
    expansions = [_msg("e1", "s", 1, big), _msg("e2", "s", 2, big)]
    budget = context_json_bytes(baseline) + 600
    out = fit_to_budget(
        baseline, expansions, "word", budget_bytes=budget,
        floor_body_chars=50, reduce_baseline=False,
    )
    assert out[0]["memory_id"] == "b1"
    assert split_header(out[0]["content"])[1] == big  # baseline untouched
    assert context_json_bytes(out) <= budget
    assert all(m["memory_id"] != "b1" for m in out[1:])


def test_fit_to_budget_can_reduce_baseline_only_when_permitted() -> None:
    big = "word " * 400
    baseline = [_msg("b1", "s", 0, big)]
    tight = context_json_bytes(baseline) // 2
    kept = fit_to_budget(baseline, [], "word", budget_bytes=tight,
                         floor_body_chars=50, reduce_baseline=False)
    assert split_header(kept[0]["content"])[1] == big
    reduced = fit_to_budget(baseline, [], "word", budget_bytes=tight,
                            floor_body_chars=50, reduce_baseline=True)
    assert len(reduced) == 1 and reduced[0]["memory_id"] == "b1"
    assert len(split_header(reduced[0]["content"])[1]) < len(big)


def test_fit_to_budget_drops_expansions_from_tail_as_last_resort() -> None:
    baseline = [_msg("b1", "s", 0, "tiny")]
    expansions = [_msg("e1", "s", 1, "a" * 200), _msg("e2", "s", 2, "b" * 200)]
    budget = context_json_bytes(baseline) + 40
    out = fit_to_budget(baseline, expansions, "q", budget_bytes=budget,
                        floor_body_chars=100, reduce_baseline=False)
    assert out[0]["memory_id"] == "b1"
    assert [m["memory_id"] for m in out[1:]] in ([], ["e1"])


def test_fit_to_budget_is_fast_on_very_large_contexts() -> None:
    """Regression: the halving loop re-encoded the whole context hundreds of times and
    took minutes on real LongMemEval questions. Proportional reduction must be fast."""
    import time

    sentence = "The quick brown fox jumps over the lazy dog near the riverbank today. "
    big = sentence * 450  # ~31 KB per body
    baseline = [_msg(f"b{i}", "s", i, big) for i in range(10)]
    expansions = [_msg(f"e{i}", "s", 10 + i, big) for i in range(15)]
    budget = context_json_bytes(baseline)
    started = time.perf_counter()
    out = fit_to_budget(
        baseline, expansions, "fox riverbank", budget_bytes=budget,
        floor_body_chars=400, reduce_baseline=True,
    )
    elapsed = time.perf_counter() - started
    assert context_json_bytes(out) <= budget
    assert [m["memory_id"] for m in out[:10]] == [f"b{i}" for i in range(10)]
    assert elapsed < 3.0, f"fit_to_budget took {elapsed:.1f}s"


def test_fit_to_budget_terminates_on_tiny_overshoot() -> None:
    """Regression: when the overshoot was only a few bytes, each pass removed fewer bytes
    than the span markers added, the total never fell, and the loop never terminated."""
    import time

    body = "A sentence about the phone battery draining fast. " * 60
    baseline = [_msg("b1", "s", 0, body)]
    expansion = [_msg("e1", "s", 1, body)]
    budget = context_json_bytes(baseline + expansion) - 3  # over by three bytes
    started = time.perf_counter()
    out = fit_to_budget(
        baseline, expansion, "phone battery", budget_bytes=budget,
        floor_body_chars=400, reduce_baseline=True,
    )
    assert time.perf_counter() - started < 2.0
    assert context_json_bytes(out) <= budget
    assert out[0]["memory_id"] == "b1"
