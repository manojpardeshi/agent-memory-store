from __future__ import annotations

from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore
from scripts.locomo_heldout import (
    ARMS,
    build,
    evidence_ids,
    scope_for,
    score,
    session_datetime,
    store_path,
    turn_content,
)

# A synthetic two-conversation fixture in LoCoMo's shape; no LoCoMo data is used in tests.
FIXTURE = [
    {
        "sample_id": "conv-a",
        "conversation": {
            "speaker_a": "Ada",
            "speaker_b": "Ben",
            "session_1": [
                {"dia_id": "D1:1", "speaker": "Ada", "text": "I adopted a greyhound named Comet."},
                {"dia_id": "D1:2", "speaker": "Ben", "text": "Congratulations on the new pet!"},
            ],
            "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_2": [
                {
                    "dia_id": "D2:1",
                    "speaker": "Ada",
                    "text": "Comet loved the beach today.",
                    "blip_caption": "a dog running on sand",
                },
            ],
            "session_2_date_time": "10:04 am on 1 June, 2023",
        },
        "qa": [
            {
                "question": "What is the name of Ada's greyhound?",
                "category": 1,
                "evidence": ["D1:1"],
            },
            {"question": "Where did Comet go?", "category": 2, "evidence": ["D2:1; D1:1"]},
            {"question": "Is there a cat?", "category": 5, "evidence": ["D1:2"]},
            {"question": "Unparseable evidence", "category": 4, "evidence": ["see above"]},
        ],
    },
    {
        "sample_id": "conv-b",
        "conversation": {
            "session_1": [
                {"dia_id": "D1:1", "speaker": "Cy", "text": "My bakery opened in Leeds."}
            ],
            "session_1_date_time": "9:00 pm on 3 March, 2022",
        },
        "qa": [{"question": "Where did Cy open a bakery?", "category": 3, "evidence": ["D1:1"]}],
    },
]


def test_session_dates_parse_to_utc() -> None:
    assert session_datetime("1:56 pm on 8 May, 2023") == "2023-05-08T13:56:00+00:00"
    assert session_datetime("12:05 am on 1 January 2024") == "2024-01-01T00:05:00+00:00"
    with pytest.raises(ValueError):
        session_datetime("sometime in May")


def test_evidence_ids_accept_joined_entries_and_drop_unparseable() -> None:
    assert evidence_ids({"evidence": ["D2:1; D1:1"]}) == {"D2:1", "D1:1"}
    assert evidence_ids({"evidence": ["see above"]}) == set()


def test_turn_content_includes_speaker_and_image_caption() -> None:
    turn = FIXTURE[0]["conversation"]["session_2"][0]
    assert (
        turn_content(turn)
        == "Ada: Comet loved the beach today. [shares an image: a dog running on sand]"
    )


def test_build_stores_each_turn_with_its_session_date(tmp_path: Path) -> None:
    embedder = DeterministicEmbedder(64)
    counts = build(FIXTURE, tmp_path, embedder)
    assert counts == {"conversations": 2, "turns": 4}
    with MemoryStore(store_path(tmp_path, "conv-a"), embedder, read_only=True) as store:
        records = store.list_memories(scope_for("conv-a"))
        by_dia = {r.metadata["dia_id"]: r for r in records}
        assert by_dia["D2:1"].occurred_at == "2023-06-01T10:04:00.000000+00:00"
        assert by_dia["D1:1"].expires_at is None
    assert build(FIXTURE, tmp_path, embedder) == counts  # idempotent by operation id
    with MemoryStore(store_path(tmp_path, "conv-a"), embedder, read_only=True) as store:
        assert len(store.list_memories(scope_for("conv-a"))) == 3


def test_score_is_aggregate_only_and_excludes_adversarial_and_unparseable(tmp_path: Path) -> None:
    embedder = DeterministicEmbedder(64)
    build(FIXTURE, tmp_path, embedder)
    report = score(FIXTURE, tmp_path, embedder, {"vector": ARMS["vector"]})
    vector = report["arms"]["vector"]
    assert report["excluded_without_parseable_evidence"] == 1
    assert vector["scored_questions"] == 3  # category 5 and the unparseable item are not scored
    assert vector["complete_evidence"] == 3  # tiny stores: every turn fits in the top ten
    assert set(vector["categories"]) == {"1", "2", "3", "4"}
    serialized = repr(report)
    assert "greyhound" not in serialized and "What is" not in serialized


def _ledger(tmp_path: Path, looks: int) -> Path:
    import json

    path = tmp_path / "ledger.json"
    path.write_text(
        json.dumps(
            {
                "held_out_sets": {
                    "locomo10": {
                        "status": "active",
                        "max_looks": 3,
                        "dataset_sha256": "abc",
                        "looks": [{"candidate": f"c{i}"} for i in range(looks)],
                    }
                }
            }
        )
    )
    return path


@pytest.fixture
def clean_git(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.locomo_heldout as heldout

    monkeypatch.setattr(heldout, "_git", lambda *args: "" if args[0] == "status" else "f00d\n")
    monkeypatch.setattr(heldout.subprocess, "run", lambda *a, **k: None)


def test_look_is_recorded_before_scoring_and_retires_the_set_on_the_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_git: None
) -> None:
    import json

    import scripts.locomo_heldout as heldout

    monkeypatch.setattr(heldout, "LEDGER", _ledger(tmp_path, looks=2))
    look = heldout.record_look("hybrid", "f00d", "abc")
    entry = json.loads(heldout.LEDGER.read_text())["held_out_sets"]["locomo10"]
    assert look["result"] is None and entry["looks"][-1]["candidate"] == "hybrid"
    assert entry["status"].startswith("retired")


@pytest.mark.parametrize(
    ("looks", "digest", "message"), [(3, "abc", "used its"), (0, "zzz", "digest")]
)
def test_look_is_refused_when_budget_is_spent_or_data_differs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clean_git: None,
    looks: int,
    digest: str,
    message: str,
) -> None:
    import scripts.locomo_heldout as heldout

    monkeypatch.setattr(heldout, "LEDGER", _ledger(tmp_path, looks=looks))
    with pytest.raises(SystemExit, match=message):
        heldout.record_look("hybrid", "f00d", digest)


def test_look_is_refused_on_a_dirty_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.locomo_heldout as heldout

    monkeypatch.setattr(heldout, "LEDGER", _ledger(tmp_path, looks=0))
    monkeypatch.setattr(heldout, "_git", lambda *args: " M some_file.py\n")
    with pytest.raises(SystemExit, match="clean worktree"):
        heldout.record_look("hybrid", "f00d", "abc")


def test_look_holds_an_exclusive_lock_on_the_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clean_git: None
) -> None:
    import fcntl

    import scripts.locomo_heldout as heldout

    monkeypatch.setattr(heldout, "LEDGER", _ledger(tmp_path, looks=0))
    calls: list[int] = []
    monkeypatch.setattr(heldout.fcntl, "flock", lambda handle, op: calls.append(op))
    heldout.record_look("hybrid", "f00d", "abc")
    assert calls == [fcntl.LOCK_EX]


def test_rerank_arm_reorders_only_the_vector_pool_with_stable_ties(tmp_path: Path) -> None:
    from scripts.locomo_heldout import DEPTH, RERANK_CHARS, make_rerank_arm

    embedder = DeterministicEmbedder(64)
    build(FIXTURE, tmp_path, embedder)
    seen: list[list[str]] = []

    def fake_scores(query: str, docs: list[str]) -> list[float]:
        seen.append(docs)
        return [1.0 if "beach" in doc else 0.0 for doc in docs]  # ties for all but one

    arm = make_rerank_arm(fake_scores)
    with MemoryStore(store_path(tmp_path, "conv-a"), embedder, read_only=True) as store:
        vector = store.recall("Comet", scope_for("conv-a"), limit=50, relevance_filter=None)
        reranked = arm(store, scope_for("conv-a"), "Comet")
    pool_ids = [r.memory.memory_id for r in vector[:20]]
    out_ids = [r.memory.memory_id for r in reranked]
    assert set(out_ids) <= set(pool_ids) and len(out_ids) == min(DEPTH, len(pool_ids))
    assert "beach" in reranked[0].memory.content
    rest = [i for i in pool_ids if i != reranked[0].memory.memory_id]
    assert out_ids[1:] == rest[: len(out_ids) - 1]  # ties keep vector order
    assert all(len(doc) <= RERANK_CHARS for doc in seen[0])


def _report(base: int, cand: int, cats: dict[str, tuple[int, int, int]], lat: tuple) -> dict:
    return {
        "arms": {
            "vector": {
                "scored_questions": sum(n for n, _, _ in cats.values()),
                "complete_evidence": base,
                "median_latency_ms": lat[0],
                "p95_latency_ms": lat[1],
                "categories": {
                    c: {"n": n, "complete_evidence": b} for c, (n, b, _) in cats.items()
                },
            },
            "cand": {
                "complete_evidence": cand,
                "median_latency_ms": lat[2],
                "p95_latency_ms": lat[3],
                "categories": {c: {"complete_evidence": x} for c, (_, _, x) in cats.items()},
            },
        }
    }


RULE = {
    "min_gain_fraction": 0.02,
    "max_category_loss_fraction": 0.01,
    "max_added_median_ms": 500,
    "max_added_p95_ms": 750,
}


def test_verdict_applies_the_frozen_rule_mechanically() -> None:
    from scripts.locomo_heldout import verdict

    cats = {"1": (200, 100, 110), "2": (300, 150, 150)}  # 500 scored -> need +10
    ok = verdict(_report(250, 260, cats, (10, 20, 300, 600)), RULE, "cand")
    assert ok["passed"] and ok["required_complete_evidence"] == 260
    short = verdict(_report(250, 259, cats, (10, 20, 300, 600)), RULE, "cand")
    assert not short["checks"]["complete_evidence_gain"]
    lossy = {"1": (200, 100, 120), "2": (300, 150, 146)}  # loses 4 > floor(3)
    assert not verdict(_report(250, 266, lossy, (10, 20, 300, 600)), RULE, "cand")["passed"]
    slow = verdict(_report(250, 270, cats, (10, 20, 511, 600)), RULE, "cand")
    assert not slow["checks"]["median_latency"] and slow["checks"]["p95_latency"]


def test_result_is_recorded_on_its_own_look(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    import scripts.locomo_heldout as heldout

    path = _ledger(tmp_path, looks=0)
    data = json.loads(path.read_text())
    data["held_out_sets"]["locomo10"]["looks"] = [
        {"candidate": "a", "started": "t1", "result": None},
        {"candidate": "b", "started": "t2", "result": None},
    ]
    path.write_text(json.dumps(data))
    monkeypatch.setattr(heldout, "LEDGER", path)
    heldout.record_result({"candidate": "b", "started": "t2"}, {"passed": True})
    looks = json.loads(path.read_text())["held_out_sets"]["locomo10"]["looks"]
    assert looks[0]["result"] is None and looks[1]["result"] == {"passed": True}
