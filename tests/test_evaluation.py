from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, RelevanceFilter
from llm_memory_store.evaluation import (
    EvaluationDatasetError,
    load_evaluation_dataset,
    run_retrieval_evaluation,
    score_evaluation_rankings,
    write_evaluation_report,
)


def _scope(kind: str, owner: str) -> dict[str, str]:
    return {
        "kind": kind,
        "subject": "eval-user",
        "environment": "test",
        "owner": owner,
    }


def _dataset_value() -> dict:
    return {
        "schema_version": 1,
        "dataset_id": "test-retrieval-v1",
        "description": "Entirely synthetic evaluation fixture.",
        "distractor_policy": "Choose one accessible and topically unrelated control.",
        "top_k": 1,
        "thresholds": {
            "query_count_min": 2,
            "memory_kind_count_min": 1,
            "recall_at_k_min": 1,
            "mrr_min": 1,
            "distractor_leak_rate_max": 0,
            "scope_violation_count_max": 0,
            "runtime_seconds_max": 60,
        },
        "memories": [
            {
                "fixture_id": "pref",
                "kind": "preference",
                "content": "Synthetic editor preference is cobalt mode.",
                "scope": _scope("private", "app-a"),
            },
            {
                "fixture_id": "fact",
                "kind": "fact",
                "content": "Synthetic archive location is the amber cabinet.",
                "scope": _scope("private", "app-a"),
            },
            {
                "fixture_id": "event",
                "kind": "event",
                "content": "Synthetic inaccessible event occurs on Monday.",
                "scope": _scope("private", "app-b"),
            },
            {
                "fixture_id": "summary",
                "kind": "summary",
                "content": "Synthetic Project Lime architecture uses queues and workers.",
                "scope": _scope("shared", "project-lime"),
            },
            {
                "fixture_id": "turn",
                "kind": "turn",
                "role": "user",
                "content": "The synthetic mascot is a heron.",
                "scope": _scope("shared", "project-lime"),
            },
        ],
        "queries": [
            {
                "query_id": "private-query",
                "query": "Synthetic editor preference is cobalt mode.",
                "private_scope": _scope("private", "app-a"),
                "shared_pools": [],
                "expected_fixture_ids": ["pref"],
                "distractor_fixture_ids": ["fact"],
                "inaccessible_fixture_ids": ["event"],
            },
            {
                "query_id": "shared-query",
                "query": "Synthetic Project Lime architecture uses queues and workers.",
                "private_scope": _scope("private", "consumer"),
                "shared_pools": ["project-lime"],
                "expected_fixture_ids": ["summary"],
                "distractor_fixture_ids": ["turn"],
                "inaccessible_fixture_ids": ["event"],
            },
        ],
    }


def _write_dataset(tmp_path: Path, value: dict | None = None) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(value or _dataset_value()), encoding="utf-8")
    return path


def test_loads_valid_versioned_dataset_and_digest(tmp_path: Path) -> None:
    dataset, digest = load_evaluation_dataset(_write_dataset(tmp_path))

    assert dataset.dataset_id == "test-retrieval-v1"
    assert len(dataset.memories) == 5
    assert len(dataset.queries) == 2
    assert len(digest) == 64


def test_rejects_unknown_schema_version(tmp_path: Path) -> None:
    value = _dataset_value()
    value["schema_version"] = 2

    with pytest.raises(EvaluationDatasetError, match="schema_version"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_duplicate_memory_fixture_ids(tmp_path: Path) -> None:
    value = _dataset_value()
    value["memories"][1]["fixture_id"] = "pref"

    with pytest.raises(EvaluationDatasetError, match="fixture_id"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_turn_without_role(tmp_path: Path) -> None:
    value = _dataset_value()
    del value["memories"][4]["role"]

    with pytest.raises(EvaluationDatasetError, match="turn requires"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_unknown_query_fixture_reference(tmp_path: Path) -> None:
    value = _dataset_value()
    value["queries"][0]["expected_fixture_ids"] = ["missing"]

    with pytest.raises(EvaluationDatasetError, match="unknown fixtures"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_inaccessible_expected_fixture(tmp_path: Path) -> None:
    value = _dataset_value()
    value["queries"][0]["expected_fixture_ids"] = ["event"]

    with pytest.raises(EvaluationDatasetError, match="expected fixture is inaccessible"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_accessible_fixture_marked_inaccessible(tmp_path: Path) -> None:
    value = _dataset_value()
    value["queries"][0]["inaccessible_fixture_ids"] = ["fact"]

    with pytest.raises(EvaluationDatasetError, match="inaccessible fixture is available"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_fractional_integer_threshold(tmp_path: Path) -> None:
    value = _dataset_value()
    value["thresholds"]["scope_violation_count_max"] = 0.5

    with pytest.raises(EvaluationDatasetError, match="must be an integer"):
        load_evaluation_dataset(_write_dataset(tmp_path, value))


def test_scores_perfect_rankings_and_coverage(tmp_path: Path) -> None:
    dataset, _ = load_evaluation_dataset(_write_dataset(tmp_path))
    score = score_evaluation_rankings(
        dataset,
        {"private-query": ["pref"], "shared-query": ["summary"]},
        runtime_seconds=0.1,
    )

    assert score["passed"] is True
    assert score["metrics"]["recall_at_k"] == 1
    assert score["metrics"]["mrr"] == 1
    assert score["metrics"]["distractor_leak_rate"] == 0
    assert score["metrics"]["uniform_random_distractor_leak_rate"] == 0.5
    assert score["metrics"]["distractor_reduction_vs_uniform_random"] == 1
    assert score["diagnostics"]["distractor_by_access_mode"] == {
        "private-exact": {
            "hits": 0,
            "total": 1,
            "uniform_random_expected_hits": 0.5,
            "rate": 0,
            "uniform_random_rate": 0.5,
            "reduction_vs_uniform_random": 1,
        },
        "shared-pool": {
            "hits": 0,
            "total": 1,
            "uniform_random_expected_hits": 0.5,
            "rate": 0,
            "uniform_random_rate": 0.5,
            "reduction_vs_uniform_random": 1,
        },
    }
    assert all(score["checks"].values())


def test_scores_distractor_leaks_and_scope_violations(tmp_path: Path) -> None:
    dataset, _ = load_evaluation_dataset(_write_dataset(tmp_path))
    distractors = score_evaluation_rankings(
        dataset,
        {"private-query": ["fact"], "shared-query": ["turn"]},
        runtime_seconds=0.1,
    )
    inaccessible = score_evaluation_rankings(
        dataset,
        {"private-query": ["event"], "shared-query": ["event"]},
        runtime_seconds=0.1,
    )

    assert distractors["metrics"]["distractor_leak_rate"] == 1
    assert distractors["passed"] is False
    assert inaccessible["metrics"]["scope_violation_count"] == 2
    assert inaccessible["passed"] is False


def test_rejects_duplicate_ids_in_a_ranking(tmp_path: Path) -> None:
    value = _dataset_value()
    value["top_k"] = 2
    dataset, _ = load_evaluation_dataset(_write_dataset(tmp_path, value))

    with pytest.raises(ValueError, match="duplicate IDs"):
        score_evaluation_rankings(
            dataset,
            {"private-query": ["pref", "pref"], "shared-query": ["summary"]},
            runtime_seconds=0.1,
        )


def test_runs_isolated_end_to_end_evaluation(tmp_path: Path) -> None:
    report = run_retrieval_evaluation(
        _write_dataset(tmp_path),
        DeterministicEmbedder(64),
    )

    assert report["passed"] is True
    assert report["dataset"]["synthetic_only"] is True
    assert report["dataset"]["kind_counts"] == {
        "turn": 1,
        "fact": 1,
        "preference": 1,
        "summary": 1,
        "event": 1,
    }
    assert report["metrics"]["scope_violation_count"] == 0
    assert report["query_results"][0]["expected_item_details"][0]["fixture_id"] == "pref"
    assert report["query_results"][0]["expected_item_details"][0]["semantic_score"] == 1
    assert report["query_results"][0]["distractor_item_details"][0]["fixture_id"] == "fact"

    filtered = run_retrieval_evaluation(
        _write_dataset(tmp_path),
        DeterministicEmbedder(64),
        relevance_filter=RelevanceFilter.relative(0),
    )
    assert filtered["retrieval_config"] == {
        "limit": 1,
        "retrieval": "vector",
        "relevance_filter": {
            "strategy": "relative_semantic_gap",
            "maximum_semantic_score_gap": 0.0,
        },
        "product_default_for_identity": False,
    }
    assert all(len(result["retrieved_items"]) == 1 for result in filtered["query_results"])


def test_report_write_is_private_and_refuses_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "reports" / "evaluation.json"
    write_evaluation_report({"passed": True}, destination)

    assert destination.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_evaluation_report({"passed": False}, destination)


def test_versioned_product_fixture_has_required_coverage() -> None:
    fixture = Path(__file__).parents[1] / "evaluation" / "retrieval_v1.json"
    dataset, digest = load_evaluation_dataset(fixture)
    kind_counts = {
        kind: sum(memory.kind == kind for memory in dataset.memories)
        for kind in ("turn", "fact", "preference", "summary", "event")
    }

    assert len(dataset.queries) == 50
    assert kind_counts == {kind: 10 for kind in kind_counts}
    assert all(query.distractor_fixture_ids for query in dataset.queries)
    assert all(query.inaccessible_fixture_ids for query in dataset.queries)
    assert len(digest) == 64


def test_independent_product_fixture_is_frozen_and_balanced() -> None:
    fixture = Path(__file__).parents[1] / "evaluation" / "retrieval_v2.json"
    dataset, digest = load_evaluation_dataset(fixture)
    kind_counts = {
        kind: sum(memory.kind == kind for memory in dataset.memories)
        for kind in ("turn", "fact", "preference", "summary", "event")
    }

    assert digest == "67fd5c4b2779a2dab42dca545cbd8a7a8a0a9a604d83cda0c8b54d60134956bf"
    assert len(dataset.memories) == 60
    assert len(dataset.queries) == 60
    assert kind_counts == {kind: 12 for kind in kind_counts}
    assert all(
        not (set(query.expected_fixture_ids) & set(query.distractor_fixture_ids))
        for query in dataset.queries
    )
    assert all(
        not (set(query.expected_fixture_ids) & set(query.inaccessible_fixture_ids))
        for query in dataset.queries
    )
