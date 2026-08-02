from __future__ import annotations

import copy

import pytest

from scripts.build_session_density_corpus import (
    CATEGORIES,
    SessionDensityCorpusError,
    build_corpus,
    validate_cross_review,
)


def _author(author: str) -> dict:
    cases = []
    index = 0
    for category in CATEGORIES:
        if category.startswith("single-session-"):
            dense_count = 5
        elif category == "multi-session":
            dense_count = 0
        elif category == "temporal-reasoning":
            dense_count = 3 if author == "A" else 2
        else:
            dense_count = 2 if author == "A" else 3
        for stratum, count in (
            ("dense-evidence", dense_count),
            ("diversity-required", 5 - dense_count),
        ):
            for _ in range(count):
                index += 1
                prefix = f"{author}{index:03d}"
                session_count = 1 if stratum == "dense-evidence" else 2
                sessions = []
                required_messages = []
                required_sessions = []
                for session_index in range(session_count):
                    session_id = f"{prefix}-S{session_index}"
                    required_sessions.append(session_id)
                    messages = []
                    message_count = 3 if stratum == "dense-evidence" else 1
                    for message_index in range(message_count):
                        message_id = f"{prefix}-M{session_index}-{message_index}"
                        required_messages.append(message_id)
                        messages.append(
                            {
                                "message_id": message_id,
                                "role": "user" if message_index % 2 == 0 else "assistant",
                                "content": (
                                    f"Fictional evidence {prefix} "
                                    f"{session_index} {message_index}"
                                ),
                            }
                        )
                    sessions.append(
                        {
                            "session_id": session_id,
                            "date": "2026-01-01T10:00:00+00:00",
                            "messages": messages,
                        }
                    )
                for session_index in range(session_count, 8):
                    session_id = f"{prefix}-S{session_index}"
                    message_id = f"{prefix}-D{session_index}-0"
                    sessions.append(
                        {
                            "session_id": session_id,
                            "date": "2026-01-01T10:00:00+00:00",
                            "messages": [
                                {
                                    "message_id": message_id,
                                    "role": "user",
                                    "content": f"Fictional distractor {prefix} {session_index}",
                                }
                            ],
                        }
                    )
                distractor_index = 1
                while sum(len(session["messages"]) for session in sessions) < 20:
                    message_id = f"{prefix}-DX-{distractor_index}"
                    sessions[-1]["messages"].append(
                        {
                            "message_id": message_id,
                            "role": "assistant" if distractor_index % 2 else "user",
                            "content": (
                                f"Additional fictional distractor "
                                f"{prefix} {distractor_index}"
                            ),
                        }
                    )
                    distractor_index += 1
                cases.append(
                    {
                        "id": prefix,
                        "author": author,
                        "category": category,
                        "stratum": stratum,
                        "question_date": "2026-02-01T10:00:00+00:00",
                        "question": f"What is the fictional answer for {prefix}?",
                        "ground_truth": f"Answer {prefix}",
                        "sessions": sessions,
                        "required_message_ids": required_messages,
                        "required_session_ids": required_sessions,
                        "required_fact_units": [
                            {
                                "fact_id": f"{prefix}-F1",
                                "text": f"Required facts for {prefix}",
                                "supporting_message_ids": required_messages,
                            }
                        ],
                    }
                )
    return {
        "schema_version": 1,
        "status": "independent-author-draft",
        "cases": cases,
    }


def test_build_corpus_validates_balance_and_orders_sixty_cases() -> None:
    corpus = build_corpus(_author("A"), _author("B"))

    assert corpus["status"] == "assembled-awaiting-independent-review"
    assert corpus["question_count"] == 60
    assert set(corpus["category_counts"].values()) == {10}
    assert corpus["stratum_counts"] == {
        "dense-evidence": 40,
        "diversity-required": 20,
    }
    assert corpus["longmemeval_overlap_check_completed"] is False


def test_build_corpus_rejects_inconsistent_required_session_labels() -> None:
    author_a = _author("A")
    author_a["cases"][0]["required_session_ids"] = ["unknown"]

    with pytest.raises(SessionDensityCorpusError, match="unknown required session"):
        build_corpus(author_a, _author("B"))


def test_build_corpus_rejects_longmemeval_shingle_overlap() -> None:
    author_a = _author("A")
    changed = copy.deepcopy(author_a)
    overlap = "one two three four five six seven eight nine ten eleven twelve"
    changed["cases"][0]["question"] = overlap
    dataset = [{"question": overlap, "answer": "unrelated", "haystack_sessions": []}]

    with pytest.raises(SessionDensityCorpusError, match="overlap"):
        build_corpus(changed, _author("B"), longmemeval_dataset=dataset)


def test_cross_review_must_pass_the_exact_source() -> None:
    review = {
        "schema_version": 1,
        "reviewer": "A",
        "status": "pass",
        "source_sha256": "source-b",
        "per_case_findings": [{} for _ in range(30)],
        "corpus_findings": [],
    }

    validate_cross_review(review, reviewer="A", expected_source_sha256="source-b")
    with pytest.raises(SessionDensityCorpusError, match="different source"):
        validate_cross_review(review, reviewer="A", expected_source_sha256="changed")
