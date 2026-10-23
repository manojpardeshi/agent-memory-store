"""Property-based tests (Hypothesis) of the real implementation.

These check the safety properties that are proved on a model in Rocq, against the actual Python:
keyword-query sanitisation, hybrid-recall scope isolation and fusion order, the held-out ledger
budget, and ``occurred_at`` validation. They use only synthetic data; no LoCoMo data and not the
real ledger is read.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import scripts.locomo_heldout as heldout
from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.store import (
    KEYWORD_STOPWORDS,
    MAX_KEYWORD_QUERY_TERMS,
    OCCURRED_AT_CLOCK_SKEW,
    keyword_query,
)

# ---------------------------------------------------------------------------------------------
# 1. keyword_query
# ---------------------------------------------------------------------------------------------

QUERY_SHAPE = re.compile(r'"[^\W_]+"( OR "[^\W_]+")*')
WORD = re.compile(r"[^\W_]+")

_SYNTAX_FRAGMENTS = [
    '"',
    "'",
    "_",
    "NEAR",
    "NEAR/3",
    "AND",
    "OR",
    "NOT",
    "*",
    "^",
    "(",
    ")",
    ":",
    "-",
    "+",
    "{",
    "}",
    "col:",
    "\U0001f600",
    "é",
    "ı",
    "İ",
    "ß",
    "\n",
    "\t",
]
_short_words = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=4)
# Mixes arbitrary unicode with FTS5 syntax and many distinct words (to exceed the term cap).
keyword_text = st.one_of(
    st.text(max_size=120),
    st.lists(st.one_of(st.sampled_from(_SYNTAX_FRAGMENTS), st.text(max_size=6)), max_size=30).map(
        " ".join
    ),
    st.lists(st.one_of(_short_words, st.sampled_from(_SYNTAX_FRAGMENTS)), max_size=200).map(
        " ".join
    ),
)


def _eligible_tokens(text: str) -> list[str]:
    return [t for t in WORD.findall(text.lower()) if t not in KEYWORD_STOPWORDS and len(t) > 1]


@settings(derandomize=True, max_examples=400, deadline=None)
@given(keyword_text)
def test_keyword_query_is_always_a_safe_quoted_or_query(text: str) -> None:
    query = keyword_query(text)
    eligible = _eligible_tokens(text)
    if not eligible:
        assert query is None  # None iff there is no eligible token
        return
    assert query is not None
    assert QUERY_SHAPE.fullmatch(query)
    terms = [part[1:-1] for part in query.split(" OR ")]
    assert 1 <= len(terms) <= MAX_KEYWORD_QUERY_TERMS
    assert len(set(terms)) == len(terms)
    for term in terms:
        assert '"' not in term and not any(ch.isspace() for ch in term)
        assert term not in KEYWORD_STOPWORDS and len(term) > 1
    # Terms are the first distinct eligible tokens, in order.
    assert terms == list(dict.fromkeys(eligible))[:MAX_KEYWORD_QUERY_TERMS]


@settings(derandomize=True, max_examples=50, deadline=None)
@given(st.lists(_short_words, min_size=70, max_size=150, unique=True))
def test_keyword_query_caps_the_number_of_terms(words: list[str]) -> None:
    eligible = _eligible_tokens(" ".join(words))
    assume(len(set(eligible)) > MAX_KEYWORD_QUERY_TERMS)
    query = keyword_query(" ".join(words))
    assert query is not None
    assert len(query.split(" OR ")) == MAX_KEYWORD_QUERY_TERMS


@pytest.fixture(scope="module")
def fts_store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[MemoryStore]:
    path = tmp_path_factory.mktemp("fts") / "memory.sqlite3"
    instance = MemoryStore(path, DeterministicEmbedder(64))
    scope = Scope.private("subject", "test", "agent")
    for text in (
        "near and or not operators in a sentence",
        "the quick brown fox jumps over the lazy dog",
        "col:value ^start prefix* (grouped) terms",
        "emoji \U0001f600 and é combining marks",
    ):
        instance.remember("fact", text, scope)
    try:
        yield instance
    finally:
        instance.close()


@settings(
    derandomize=True,
    max_examples=300,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(keyword_text)
def test_keyword_query_never_raises_in_fts5_match(fts_store: MemoryStore, text: str) -> None:
    assume(re.search(r"\w", text) is not None and text.strip())
    scope = Scope.private("subject", "test", "agent")
    results = fts_store.recall(text, scope, limit=10, retrieval="hybrid", relevance_filter=None)
    assert len({r.memory.memory_id for r in results}) == len(results)


# ---------------------------------------------------------------------------------------------
# 2. Hybrid recall fusion
# ---------------------------------------------------------------------------------------------

VOCABULARY = [
    "alpha",
    "beta",
    "gamma",
    "delta",
    "coffee",
    "garden",
    "river",
    "stone",
    "the",
    "what",
    "is",
    "it",
    "and",
    "of",
]
STOPWORD_ONLY = ["what", "is", "it", "the", "and", "of", "tell", "me", "about", "you"]

texts = st.lists(st.sampled_from(VOCABULARY), min_size=1, max_size=6).map(" ".join)
queries = st.lists(st.sampled_from(VOCABULARY), min_size=1, max_size=4).map(" ".join)
stopword_queries = st.lists(st.sampled_from(STOPWORD_ONLY), min_size=1, max_size=4).map(" ".join)
POOLS = ["pool-a", "pool-b"]
AGENTS = ["agent-0", "agent-1", "agent-2"]


@st.composite
def store_layouts(draw: st.DrawFn) -> list[tuple[str, str, str]]:
    """Memories as (scope kind, owner, text): 2-15 across 2-3 private scopes and optional pools."""

    agents = AGENTS[: draw(st.integers(2, 3))]
    owners = [("private", a) for a in agents]
    if draw(st.booleans()):
        owners += [("shared", p) for p in POOLS[: draw(st.integers(1, 2))]]
    size = draw(st.integers(2, 15))
    return [(*draw(st.sampled_from(owners)), draw(texts)) for _ in range(size)]


def _scope(kind: str, owner: str) -> Scope:
    if kind == "private":
        return Scope.private("subject", "test", owner)
    return Scope.shared("subject", "test", owner)


@contextmanager
def _populated_store(layout: list[tuple[str, str, str]]) -> Iterator[MemoryStore]:
    with tempfile.TemporaryDirectory() as directory:
        store = MemoryStore(Path(directory) / "memory.sqlite3", DeterministicEmbedder(64))
        try:
            for kind, owner, text in layout:
                store.remember("fact", text, _scope(kind, owner))
            yield store
        finally:
            store.close()


@settings(derandomize=True, max_examples=60, deadline=None)
@given(store_layouts(), queries, st.sets(st.sampled_from(POOLS)), st.integers(1, 20))
def test_hybrid_recall_isolates_scopes_and_orders_by_fusion_score(
    layout: list[tuple[str, str, str]], query: str, pools: set[str], limit: int
) -> None:
    named_pools = sorted(pools)
    with _populated_store(layout) as store:
        results = store.recall(
            query,
            _scope("private", "agent-0"),
            shared_pools=named_pools,
            limit=limit,
            retrieval="hybrid",
            relevance_filter=None,
        )
    allowed = {_scope("private", "agent-0")} | {_scope("shared", p) for p in named_pools}
    assert len(results) <= limit
    assert all(result.memory.scope in allowed for result in results)
    ids = [result.memory.memory_id for result in results]
    assert len(set(ids)) == len(ids)
    fusion = [result.fusion_score for result in results]
    assert all(score is not None and score > 0 for score in fusion)
    assert all(a >= b for a, b in zip(fusion, fusion[1:], strict=False))


@settings(derandomize=True, max_examples=40, deadline=None)
@given(store_layouts(), stopword_queries, st.sets(st.sampled_from(POOLS)))
def test_hybrid_equals_vector_order_when_the_query_has_no_keyword(
    layout: list[tuple[str, str, str]], query: str, pools: set[str]
) -> None:
    assert keyword_query(query) is None
    private = _scope("private", "agent-0")
    with _populated_store(layout) as store:
        common = {"shared_pools": sorted(pools), "limit": 100, "relevance_filter": None}
        vector = store.recall(query, private, retrieval="vector", **common)
        hybrid = store.recall(query, private, retrieval="hybrid", **common)
    assert [r.memory.memory_id for r in hybrid] == [r.memory.memory_id for r in vector]


# ---------------------------------------------------------------------------------------------
# 3. Held-out ledger record_look
# ---------------------------------------------------------------------------------------------


@contextmanager
def _isolated_ledger(max_looks: int, prefilled: int) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "ledger.json"
        entry = {
            "status": "active",
            "max_looks": max_looks,
            "dataset_sha256": "good",
            "looks": [{"candidate": f"c{i}"} for i in range(prefilled)],
        }
        path.write_text(json.dumps({"held_out_sets": {heldout.SET_NAME: entry}}))
        git = lambda *args: "" if args[0] == "status" else "f00d\n"  # noqa: E731
        with (
            mock.patch.object(heldout, "LEDGER", path),
            mock.patch.object(heldout, "_git", git),
            mock.patch.object(heldout.subprocess, "run", lambda *a, **k: None),
        ):
            yield path


def _entry(path: Path) -> dict:
    return json.loads(path.read_text())["held_out_sets"][heldout.SET_NAME]


@st.composite
def ledger_runs(draw: st.DrawFn) -> tuple[int, int, list[bool]]:
    max_looks = draw(st.integers(1, 5))
    prefilled = draw(st.integers(0, max_looks))
    return max_looks, prefilled, draw(st.lists(st.booleans(), min_size=1, max_size=15))


@settings(derandomize=True, max_examples=150, deadline=None)
@given(ledger_runs())
def test_held_out_ledger_never_exceeds_its_budget_and_refusals_change_nothing(
    run: tuple[int, int, list[bool]],
) -> None:
    max_looks, prefilled, matches = run
    with _isolated_ledger(max_looks, prefilled) as path:
        looks, active = prefilled, True
        for index, digest_matches in enumerate(matches):
            before = path.read_bytes()
            expect_accept = active and digest_matches and looks < max_looks
            try:
                heldout.record_look(f"cand{index}", "f00d", "good" if digest_matches else "bad")
            except SystemExit:
                assert not expect_accept
                assert path.read_bytes() == before  # a refused attempt never touches the ledger
            else:
                assert expect_accept
                looks += 1
                if looks >= max_looks:
                    active = False  # retired on the last look
            entry = _entry(path)
            assert len(entry["looks"]) == looks <= max_looks
            assert (entry["status"] == "active") == active
        if not active:
            retired = path.read_bytes()
            for digest in ("good", "bad"):
                with pytest.raises(SystemExit):
                    heldout.record_look("late", "f00d", digest)
            assert path.read_bytes() == retired


# ---------------------------------------------------------------------------------------------
# 4. occurred_at validation
# ---------------------------------------------------------------------------------------------

offsets = st.integers(-23 * 60 - 59, 23 * 60 + 59).map(lambda m: timezone(timedelta(minutes=m)))
past_instants = st.datetimes(min_value=datetime(1971, 1, 2), max_value=datetime(2026, 1, 1)).map(
    lambda d: d.replace(tzinfo=UTC)
)


@pytest.fixture(scope="module")
def occurred_store(tmp_path_factory: pytest.TempPathFactory) -> Iterator[MemoryStore]:
    path = tmp_path_factory.mktemp("occurred") / "memory.sqlite3"
    instance = MemoryStore(path, DeterministicEmbedder(64))
    try:
        yield instance
    finally:
        instance.close()


SCOPE = Scope.private("subject", "test", "agent")
store_settings = settings(
    derandomize=True,
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@store_settings
@given(past_instants, offsets)
def test_occurred_at_is_normalised_to_utc_and_keeps_the_instant(
    occurred_store: MemoryStore, instant: datetime, zone: timezone
) -> None:
    local = instant.astimezone(zone)
    assert local.utcoffset() == zone.utcoffset(None)
    record = occurred_store.remember(
        "fact", "occurred", SCOPE, occurred_at=local.isoformat(), embed=False
    )
    assert record.occurred_at is not None
    stored = datetime.fromisoformat(record.occurred_at)
    assert stored.utcoffset() == timedelta(0)
    assert stored == instant == local
    assert record.occurred_at == instant.isoformat(timespec="microseconds")


@store_settings
@given(st.datetimes(min_value=datetime(1971, 1, 2), max_value=datetime(2200, 1, 1)))
def test_naive_occurred_at_is_rejected(occurred_store: MemoryStore, naive: datetime) -> None:
    with pytest.raises(ValueError):
        occurred_store.remember("fact", "naive", SCOPE, occurred_at=naive.isoformat(), embed=False)


@store_settings
@given(st.integers(min_value=-(10**9), max_value=10**9), offsets)
def test_occurred_at_future_boundary_is_the_clock_skew(
    occurred_store: MemoryStore, delta_seconds: int, zone: timezone
) -> None:
    skew = int(OCCURRED_AT_CLOCK_SKEW.total_seconds())
    margin = 30  # seconds of real time that may elapse between building and validating
    instant = (datetime.now(UTC) + timedelta(seconds=delta_seconds)).astimezone(zone)
    if delta_seconds <= skew - margin:
        record = occurred_store.remember(
            "fact", "in range", SCOPE, occurred_at=instant.isoformat(), embed=False
        )
        assert datetime.fromisoformat(record.occurred_at or "") == instant
    elif delta_seconds >= skew + margin:
        with pytest.raises(ValueError):
            occurred_store.remember(
                "fact", "too far", SCOPE, occurred_at=instant.isoformat(), embed=False
            )


@pytest.mark.parametrize(
    ("delta_seconds", "accepted"),
    [(-1, True), (0, True), (290, True), (310, False), (86_400, False)],
)
def test_occurred_at_skew_edges_are_exact_enough(
    occurred_store: MemoryStore, delta_seconds: int, accepted: bool
) -> None:
    instant = datetime.now(UTC) + timedelta(seconds=delta_seconds)
    if accepted:
        occurred_store.remember("fact", "edge", SCOPE, occurred_at=instant.isoformat(), embed=False)
    else:
        with pytest.raises(ValueError):
            occurred_store.remember(
                "fact", "edge", SCOPE, occurred_at=instant.isoformat(), embed=False
            )
