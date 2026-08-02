from __future__ import annotations

from scripts.verify_session_density_freeze import (
    baseline_fitness,
    corpus_fitness,
    review_fitness,
)


def _case(case_id: str, *, category: str = "single-session-user") -> dict:
    sessions = []
    for session_index in range(8):
        messages = []
        for message_index in range(3 if session_index < 4 else 2):
            messages.append(
                {
                    "message_id": f"{case_id}-M{session_index}-{message_index}",
                    "role": "user",
                    "content": f"Fictional content {session_index} {message_index}",
                }
            )
        sessions.append(
            {
                "session_id": f"{case_id}-S{session_index}",
                "date": "2026-01-01T00:00:00Z",
                "messages": messages,
            }
        )
    required = [f"{case_id}-M0-{index}" for index in range(3)]
    return {
        "id": case_id,
        "category": category,
        "stratum": "dense-evidence",
        "sessions": sessions,
        "required_message_ids": required,
        "required_session_ids": [f"{case_id}-S0"],
        "required_fact_units": [
            {
                "fact_id": f"{case_id}-F1",
                "text": "A fictional atomic fact.",
                "supporting_message_ids": required,
            }
        ],
    }


def test_corpus_fitness_rejects_too_few_messages_for_top10_swap() -> None:
    cases = []
    categories = [
        "single-session-preference",
        "single-session-user",
        "multi-session",
        "temporal-reasoning",
        "knowledge-update",
        "single-session-assistant",
    ]
    for category in categories:
        for index in range(10):
            case = _case(f"{category}-{index}", category=category)
            if category.startswith("single-session-"):
                case["stratum"] = "dense-evidence"
            elif category == "multi-session":
                case["stratum"] = "diversity-required"
            else:
                case["stratum"] = (
                    "dense-evidence" if index < 5 else "diversity-required"
                )
            if case["stratum"] == "diversity-required":
                case["required_session_ids"] = [
                    f"{case['id']}-S0",
                    f"{case['id']}-S1",
                ]
                second = f"{case['id']}-M1-0"
                case["required_message_ids"].append(second)
                case["required_fact_units"][0]["supporting_message_ids"].append(second)
            cases.append(case)
    corpus = {
        "schema_version": 1,
        "status": "independently-reviewed",
        "question_count": 60,
        "cases": cases,
    }
    passing = corpus_fitness(corpus)
    assert all(check["passed"] for check in passing)

    corpus["cases"][0]["sessions"] = corpus["cases"][0]["sessions"][:2]
    failing = {check["name"]: check["passed"] for check in corpus_fitness(corpus)}
    assert failing["minimum_retrieval_topology"] is False
    assert failing["minimum_distractor_topology"] is False


def test_corpus_fitness_rejects_single_session_label_conflict_and_missing_facts() -> None:
    case = _case("case-1")
    case["required_session_ids"] = ["case-1-S0", "case-1-S1"]
    case.pop("required_fact_units")
    corpus = {
        "schema_version": 1,
        "status": "independently-reviewed",
        "question_count": 60,
        "cases": [case] * 60,
    }
    checks = {check["name"]: check["passed"] for check in corpus_fitness(corpus)}
    assert checks["single_session_category_semantics"] is False
    assert checks["atomic_required_fact_units"] is False


def _passing_review(source_sha256: str = "a" * 64) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reviewer": "A",
        "status": "pass",
        "source_sha256": source_sha256,
        "per_case_findings": [
            {"case_id": "B001", "status": "pass", "findings": []},
            {"case_id": "B002", "status": "pass", "findings": []},
        ],
        "corpus_findings": [],
    }


def _named(checks: list[dict[str, object]], suffix: str) -> dict[str, object]:
    return next(check for check in checks if str(check["name"]).endswith(suffix))


def test_review_fitness_requires_each_case_once_and_no_findings() -> None:
    review = _passing_review()
    assert all(
        check["passed"]
        for check in review_fitness(
            review,
            reviewer="A",
            expected_case_ids={"B001", "B002"},
            reviewed_source_sha256="a" * 64,
        )
    )
    review["per_case_findings"][1]["case_id"] = "B001"  # type: ignore[index]
    checks = review_fitness(
        review,
        reviewer="A",
        expected_case_ids={"B001", "B002"},
        reviewed_source_sha256="a" * 64,
    )
    assert not _named(checks, "_coverage")["passed"]


def test_review_fitness_rejects_review_of_a_superseded_source_revision() -> None:
    """A review authored against an earlier author half must not satisfy the freeze gate.

    Case IDs survive a corpus repair unchanged, so coverage and findings alone cannot
    distinguish a current review from one written against an invalidated revision.
    """

    review = _passing_review(source_sha256="b" * 64)
    checks = review_fitness(
        review,
        reviewer="A",
        expected_case_ids={"B001", "B002"},
        reviewed_source_sha256="c" * 64,
    )
    assert not _named(checks, "_source_identity")["passed"]
    assert _named(checks, "_coverage")["passed"]
    assert _named(checks, "_findings")["passed"]


def test_review_fitness_rejects_missing_source_hash() -> None:
    review = _passing_review()
    del review["source_sha256"]
    checks = review_fitness(
        review,
        reviewer="A",
        expected_case_ids={"B001", "B002"},
        reviewed_source_sha256="a" * 64,
    )
    assert not _named(checks, "_source_identity")["passed"]


def test_baseline_fitness_requires_baseline_only_deep_ranked_pools() -> None:
    ordered = ["case-1"]
    ranked_pool = [
        {
            "memory_id": f"memory-{index}",
            "score": 1.0 - index / 100,
            "metadata": {"session_id": f"session-{index}"},
        }
        for index in range(12)
    ]
    baseline = {
        "schema_version": 1,
        "artifact_type": "session-density-baseline-input",
        "status": "completed-baseline-only",
        "corpus_sha256": "corpus",
        "candidate_executed": False,
        "candidate_results_present": False,
        "hosted_api_calls": 0,
        "sealed_validation_question_records": 0,
        "reserve_question_records": 0,
        "question_ids": ordered,
        "questions": {"case-1": {"ranked_pool": ranked_pool}},
    }
    analysis = {
        "schema_version": 1,
        "artifact_type": "session-density-baseline-analysis",
        "status": "completed-baseline-only",
        "baseline_input_sha256": "baseline",
        "candidate_metrics_present": False,
        "hosted_api_calls": 0,
        "sealed_validation_question_records": 0,
        "reserve_question_records": 0,
    }
    checks = baseline_fitness(
        baseline,
        analysis,
        corpus_sha256="corpus",
        ordered_case_ids=ordered,
        baseline_sha256="baseline",
    )
    assert all(check["passed"] for check in checks)

    baseline["candidate_executed"] = True
    baseline["questions"]["case-1"]["ranked_pool"] = ranked_pool[:10]
    checks = {
        check["name"]: check["passed"]
        for check in baseline_fitness(
            baseline,
            analysis,
            corpus_sha256="corpus",
            ordered_case_ids=ordered,
            baseline_sha256="baseline",
        )
    }
    assert checks["baseline_non_authorization"] is False
    assert checks["baseline_ranked_pool_depth"] is False
