#!/usr/bin/env python3
"""Validate and deterministically assemble the independent session-density corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

CATEGORIES = (
    "single-session-preference",
    "single-session-user",
    "multi-session",
    "temporal-reasoning",
    "knowledge-update",
    "single-session-assistant",
)
STRATA = ("dense-evidence", "diversity-required")
SINGLE_SESSION_CATEGORIES = {
    "single-session-preference",
    "single-session-user",
    "single-session-assistant",
}
MULTI_SESSION_CATEGORIES = {
    "multi-session",
    "temporal-reasoning",
    "knowledge-update",
}
ORDER_SEED = "session-density-development60-v1"
TOKEN_RE = re.compile(r"[a-z0-9]+")


class SessionDensityCorpusError(RuntimeError):
    """Raised when an author file violates the fresh-corpus contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(TOKEN_RE.findall(text.casefold()))


def _shingles(text: str, width: int = 12) -> set[tuple[str, ...]]:
    tokens = _tokens(text)
    return {tokens[index : index + width] for index in range(len(tokens) - width + 1)}


def _require_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SessionDensityCorpusError(f"{location} must be non-empty text")
    return value


def _validate_case(case: dict[str, Any], author: str) -> None:
    case_id = _require_text(case.get("id"), "case id")
    if case.get("author") != author:
        raise SessionDensityCorpusError(f"{case_id} has the wrong author")
    category = case.get("category")
    stratum = case.get("stratum")
    if category not in CATEGORIES or stratum not in STRATA:
        raise SessionDensityCorpusError(f"{case_id} has an invalid category or stratum")
    _require_text(case.get("question"), f"{case_id} question")
    _require_text(case.get("ground_truth"), f"{case_id} ground truth")
    try:
        question_date = datetime.fromisoformat(
            _require_text(case.get("question_date"), f"{case_id} date")
        )
    except ValueError as exc:
        raise SessionDensityCorpusError(f"{case_id} has an invalid ISO date") from exc

    sessions = case.get("sessions")
    if not isinstance(sessions, list) or not 8 <= len(sessions) <= 10:
        raise SessionDensityCorpusError(f"{case_id} must contain 8 to 10 sessions")
    session_ids: list[str] = []
    message_to_session: dict[str, str] = {}
    messages_per_session: list[int] = []
    for session in sessions:
        session_id = _require_text(session.get("session_id"), f"{case_id} session id")
        if session_id in session_ids:
            raise SessionDensityCorpusError(f"{case_id} repeats session id {session_id}")
        session_ids.append(session_id)
        try:
            session_date = datetime.fromisoformat(
                _require_text(session.get("date"), f"{case_id}/{session_id} date")
            )
        except ValueError as exc:
            raise SessionDensityCorpusError(
                f"{case_id}/{session_id} has an invalid ISO date"
            ) from exc
        if session_date > question_date:
            raise SessionDensityCorpusError(f"{case_id}/{session_id} is after the question date")
        messages = session.get("messages")
        if not isinstance(messages, list) or not messages:
            raise SessionDensityCorpusError(f"{case_id}/{session_id} lacks messages")
        messages_per_session.append(len(messages))
        for message in messages:
            message_id = _require_text(
                message.get("message_id"), f"{case_id}/{session_id} message id"
            )
            if message_id in message_to_session:
                raise SessionDensityCorpusError(f"{case_id} repeats message id {message_id}")
            if message.get("role") not in {"user", "assistant"}:
                raise SessionDensityCorpusError(f"{case_id}/{message_id} has an invalid role")
            _require_text(message.get("content"), f"{case_id}/{message_id} content")
            message_to_session[message_id] = session_id

    if not 20 <= len(message_to_session) <= 28:
        raise SessionDensityCorpusError(f"{case_id} must contain 20 to 28 messages")
    if max(messages_per_session) < 3:
        raise SessionDensityCorpusError(f"{case_id} needs a session with at least 3 messages")

    required_messages = case.get("required_message_ids")
    required_sessions = case.get("required_session_ids")
    if not isinstance(required_messages, list) or not isinstance(required_sessions, list):
        raise SessionDensityCorpusError(f"{case_id} lacks required evidence labels")
    if len(set(required_messages)) != len(required_messages) or len(set(required_sessions)) != len(
        required_sessions
    ):
        raise SessionDensityCorpusError(f"{case_id} repeats required evidence labels")
    if not set(required_messages).issubset(message_to_session):
        raise SessionDensityCorpusError(f"{case_id} references an unknown required message")
    if not set(required_sessions).issubset(session_ids):
        raise SessionDensityCorpusError(f"{case_id} references an unknown required session")
    sessions_from_messages = {message_to_session[message_id] for message_id in required_messages}
    if sessions_from_messages != set(required_sessions):
        raise SessionDensityCorpusError(
            f"{case_id} required message and session labels do not agree"
        )
    if len(message_to_session) - len(required_messages) < 12:
        raise SessionDensityCorpusError(f"{case_id} needs at least 12 distractor messages")
    fact_units = case.get("required_fact_units")
    if not isinstance(fact_units, list) or not fact_units:
        raise SessionDensityCorpusError(f"{case_id} lacks required fact units")
    fact_ids: set[str] = set()
    fact_support: set[str] = set()
    for unit in fact_units:
        if not isinstance(unit, dict):
            raise SessionDensityCorpusError(f"{case_id} has an invalid fact unit")
        fact_id = _require_text(unit.get("fact_id"), f"{case_id} fact id")
        if fact_id in fact_ids:
            raise SessionDensityCorpusError(f"{case_id} repeats fact id {fact_id}")
        fact_ids.add(fact_id)
        _require_text(unit.get("text"), f"{case_id}/{fact_id} fact text")
        support = unit.get("supporting_message_ids")
        if not isinstance(support, list) or not support or not set(support).issubset(
            required_messages
        ):
            raise SessionDensityCorpusError(f"{case_id}/{fact_id} has invalid support")
        fact_support.update(support)
    if fact_support != set(required_messages):
        raise SessionDensityCorpusError(f"{case_id} fact units do not cover required messages")
    if stratum == "dense-evidence":
        maximum_sessions = 1 if category in SINGLE_SESSION_CATEGORIES else 2
        if not 3 <= len(required_messages) <= 6 or not 1 <= len(
            required_sessions
        ) <= maximum_sessions:
            raise SessionDensityCorpusError(f"{case_id} violates dense-evidence bounds")
    elif category not in MULTI_SESSION_CATEGORIES or not 2 <= len(required_sessions) <= 4:
        raise SessionDensityCorpusError(
            f"{case_id} violates diversity-required category or session bounds"
        )


def _expected_stratum_counts(author: str, category: str) -> dict[str, int]:
    if category in SINGLE_SESSION_CATEGORIES:
        return {"dense-evidence": 5, "diversity-required": 0}
    if category == "multi-session":
        return {"dense-evidence": 0, "diversity-required": 5}
    if category == "temporal-reasoning":
        dense = 3 if author == "A" else 2
    else:
        dense = 2 if author == "A" else 3
    return {"dense-evidence": dense, "diversity-required": 5 - dense}


def validate_author_document(document: dict[str, Any], author: str) -> list[dict[str, Any]]:
    if document.get("schema_version") != 1 or document.get("status") != "independent-author-draft":
        raise SessionDensityCorpusError(f"author {author} document header is invalid")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) != 30:
        raise SessionDensityCorpusError(f"author {author} must provide exactly 30 cases")
    for case in cases:
        if not isinstance(case, dict):
            raise SessionDensityCorpusError(f"author {author} contains a non-object case")
        _validate_case(case, author)
    ids = [case["id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise SessionDensityCorpusError(f"author {author} repeats case ids")
    counts = Counter((case["category"], case["stratum"]) for case in cases)
    expected = {
        (category, stratum): _expected_stratum_counts(author, category)[stratum]
        for category in CATEGORIES
        for stratum in STRATA
        if _expected_stratum_counts(author, category)[stratum]
    }
    if counts != expected:
        raise SessionDensityCorpusError(f"author {author} category/stratum balance is invalid")
    return cases


def validate_cross_review(
    review: dict[str, Any], *, reviewer: str, expected_source_sha256: str
) -> None:
    if review.get("schema_version") != 1 or review.get("reviewer") != reviewer:
        raise SessionDensityCorpusError(f"reviewer {reviewer} review header is invalid")
    if review.get("status") != "pass":
        raise SessionDensityCorpusError(f"reviewer {reviewer} did not pass the source")
    if review.get("source_sha256") != expected_source_sha256:
        raise SessionDensityCorpusError(f"reviewer {reviewer} reviewed a different source")
    per_case = review.get("per_case_findings")
    if not isinstance(per_case, list) or len(per_case) != 30:
        raise SessionDensityCorpusError(f"reviewer {reviewer} lacks 30 case reviews")
    if review.get("corpus_findings"):
        raise SessionDensityCorpusError(f"reviewer {reviewer} reports corpus findings")


def _longmemeval_texts(dataset: Any) -> list[str]:
    records = (
        dataset
        if isinstance(dataset, list)
        else dataset.get("data", dataset.get("questions"))
    )
    if not isinstance(records, list):
        raise SessionDensityCorpusError("LongMemEval dataset has an unsupported shape")
    texts: list[str] = []
    for record in records:
        for key in ("question", "answer"):
            if isinstance(record.get(key), str):
                texts.append(record[key])
        sessions = record.get("haystack_sessions", [])
        for session in sessions:
            messages = session if isinstance(session, list) else session.get("messages", [])
            for message in messages:
                if isinstance(message.get("content"), str):
                    texts.append(message["content"])
    return texts


def assert_no_longmemeval_overlap(cases: list[dict[str, Any]], dataset: Any) -> None:
    corpus_texts: list[str] = []
    for case in cases:
        corpus_texts.extend((case["question"], case["ground_truth"]))
        corpus_texts.extend(
            message["content"]
            for session in case["sessions"]
            for message in session["messages"]
        )
    corpus_hashes = {
        hashlib.sha256(" ".join(_tokens(text)).encode()).hexdigest()
        for text in corpus_texts
    }
    corpus_shingles: set[tuple[str, ...]] = set()
    for text in corpus_texts:
        corpus_shingles.update(_shingles(text))
    for text in _longmemeval_texts(dataset):
        normalized_hash = hashlib.sha256(" ".join(_tokens(text)).encode()).hexdigest()
        if normalized_hash in corpus_hashes:
            raise SessionDensityCorpusError("fresh corpus has an exact normalized text overlap")
        if _shingles(text) & corpus_shingles:
            raise SessionDensityCorpusError("fresh corpus has a normalized 12-token overlap")


def build_corpus(
    author_a: dict[str, Any],
    author_b: dict[str, Any],
    *,
    longmemeval_dataset: Any | None = None,
) -> dict[str, Any]:
    cases = validate_author_document(author_a, "A") + validate_author_document(author_b, "B")
    all_case_ids = [case["id"] for case in cases]
    if len(set(all_case_ids)) != 60:
        raise SessionDensityCorpusError("case ids must be unique across authors")
    all_message_ids = [
        message["message_id"]
        for case in cases
        for session in case["sessions"]
        for message in session["messages"]
    ]
    if len(set(all_message_ids)) != len(all_message_ids):
        raise SessionDensityCorpusError("message ids must be unique across the corpus")
    if longmemeval_dataset is not None:
        assert_no_longmemeval_overlap(cases, longmemeval_dataset)
    ordered = sorted(
        cases,
        key=lambda case: hashlib.sha256(f"{ORDER_SEED}:{case['id']}".encode()).hexdigest(),
    )
    return {
        "schema_version": 1,
        "status": "assembled-awaiting-independent-review",
        "corpus_id": ORDER_SEED,
        "owner_data": False,
        "private_conversation_data": False,
        "longmemeval_overlap_check_completed": longmemeval_dataset is not None,
        "question_count": len(ordered),
        "category_counts": dict(sorted(Counter(case["category"] for case in ordered).items())),
        "stratum_counts": dict(sorted(Counter(case["stratum"] for case in ordered).items())),
        "cases": ordered,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--author-a", type=Path, required=True)
    parser.add_argument("--author-b", type=Path, required=True)
    parser.add_argument("--review-a-of-b", type=Path)
    parser.add_argument("--review-b-of-a", type=Path)
    parser.add_argument("--longmemeval-dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    author_a = json.loads(args.author_a.read_text(encoding="utf-8"))
    author_b = json.loads(args.author_b.read_text(encoding="utf-8"))
    dataset = (
        json.loads(args.longmemeval_dataset.read_text(encoding="utf-8"))
        if args.longmemeval_dataset
        else None
    )
    if bool(args.review_a_of_b) != bool(args.review_b_of_a):
        raise SessionDensityCorpusError("both cross-review files must be supplied together")
    reviews: dict[str, Any] = {}
    if args.review_a_of_b and args.review_b_of_a:
        reviews = {
            "review_a_of_b": json.loads(args.review_a_of_b.read_text(encoding="utf-8")),
            "review_b_of_a": json.loads(args.review_b_of_a.read_text(encoding="utf-8")),
        }
        validate_cross_review(
            reviews["review_a_of_b"],
            reviewer="A",
            expected_source_sha256=_sha256(args.author_b),
        )
        validate_cross_review(
            reviews["review_b_of_a"],
            reviewer="B",
            expected_source_sha256=_sha256(args.author_a),
        )
    corpus = build_corpus(author_a, author_b, longmemeval_dataset=dataset)
    if reviews:
        corpus["status"] = "independently-reviewed"
    corpus["source_sha256"] = {
        "author_a": _sha256(args.author_a),
        "author_b": _sha256(args.author_b),
        "build_script": _sha256(Path(__file__)),
        "longmemeval_dataset": (
            _sha256(args.longmemeval_dataset) if args.longmemeval_dataset else None
        ),
        "review_a_of_b": _sha256(args.review_a_of_b) if args.review_a_of_b else None,
        "review_b_of_a": _sha256(args.review_b_of_a) if args.review_b_of_a else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(corpus, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"assembled {corpus['question_count']} fresh cases; status={corpus['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
