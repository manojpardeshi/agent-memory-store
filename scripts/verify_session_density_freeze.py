#!/usr/bin/env python3
"""Verify session-density v2 inputs without freezing or authorizing execution."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

MINIMUM_MESSAGES_PER_CASE = 20
MINIMUM_SESSIONS_PER_CASE = 8
MINIMUM_DISTRACTOR_MESSAGES_PER_CASE = 12
MINIMUM_DISTRACTOR_SESSIONS_PER_CASE = 4

# Both statuses deny execution. The experiment was closed without ever being frozen or run
# (AD-053), so a closed draft must keep satisfying the no-authorization check rather than
# reporting a failure that could be misread as the block having been lifted.
NON_AUTHORIZING_DRAFT_STATUSES = frozenset(
    {"draft-blocked-not-frozen", "closed-without-execution"}
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _check(
    checks: list[dict[str, Any]], name: str, passed: bool, detail: str
) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def _case_messages(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        message
        for session in case.get("sessions", [])
        for message in session.get("messages", [])
        if isinstance(message, dict)
    ]


def corpus_fitness(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Return machine checks for whether a corpus can exercise a top-10 swap policy."""

    checks: list[dict[str, Any]] = []
    cases = corpus.get("cases")
    _check(
        checks,
        "corpus_header",
        corpus.get("schema_version") == 1
        and corpus.get("status") == "independently-reviewed"
        and isinstance(cases, list)
        and len(cases) == 60
        and corpus.get("question_count") == 60,
        "requires an independently reviewed 60-case schema-v1 corpus",
    )
    if not isinstance(cases, list):
        return checks

    category_counts = Counter(case.get("category") for case in cases)
    stratum_counts = Counter(case.get("stratum") for case in cases)
    _check(
        checks,
        "corpus_balance",
        len(category_counts) == 6
        and set(category_counts.values()) == {10}
        and stratum_counts == {"dense-evidence": 40, "diversity-required": 20},
        f"category_counts={dict(category_counts)}, stratum_counts={dict(stratum_counts)}",
    )

    sparse_cases: list[str] = []
    insufficient_distractors: list[str] = []
    single_session_conflicts: list[str] = []
    missing_fact_units: list[str] = []
    invalid_fact_units: list[str] = []
    for case in cases:
        case_id = str(case.get("id", "<missing>"))
        sessions = case.get("sessions")
        if not isinstance(sessions, list):
            sparse_cases.append(case_id)
            continue
        messages = _case_messages(case)
        if (
            len(messages) < MINIMUM_MESSAGES_PER_CASE
            or len(sessions) < MINIMUM_SESSIONS_PER_CASE
        ):
            sparse_cases.append(case_id)

        required_messages = set(case.get("required_message_ids", []))
        required_sessions = set(case.get("required_session_ids", []))
        distractor_messages = [
            message
            for message in messages
            if message.get("message_id") not in required_messages
        ]
        distractor_sessions = [
            session
            for session in sessions
            if session.get("session_id") not in required_sessions
        ]
        if (
            len(distractor_messages) < MINIMUM_DISTRACTOR_MESSAGES_PER_CASE
            or len(distractor_sessions) < MINIMUM_DISTRACTOR_SESSIONS_PER_CASE
        ):
            insufficient_distractors.append(case_id)

        category = case.get("category")
        if (
            isinstance(category, str)
            and category.startswith("single-session-")
            and len(required_sessions) != 1
        ):
            single_session_conflicts.append(case_id)

        fact_units = case.get("required_fact_units")
        if not isinstance(fact_units, list) or not fact_units:
            missing_fact_units.append(case_id)
            continue
        seen_fact_ids: set[str] = set()
        cited_messages: set[str] = set()
        valid = True
        for fact in fact_units:
            if not isinstance(fact, dict):
                valid = False
                continue
            fact_id = fact.get("fact_id")
            fact_text = fact.get("text")
            source_ids = fact.get("supporting_message_ids")
            if (
                not isinstance(fact_id, str)
                or not fact_id
                or fact_id in seen_fact_ids
                or not isinstance(fact_text, str)
                or not fact_text.strip()
                or not isinstance(source_ids, list)
                or not source_ids
                or not set(source_ids).issubset(required_messages)
            ):
                valid = False
            else:
                seen_fact_ids.add(fact_id)
                cited_messages.update(source_ids)
        if cited_messages != required_messages:
            valid = False
        if not valid:
            invalid_fact_units.append(case_id)

    _check(
        checks,
        "minimum_retrieval_topology",
        not sparse_cases,
        (
            f"every case needs >= {MINIMUM_MESSAGES_PER_CASE} messages and >= "
            f"{MINIMUM_SESSIONS_PER_CASE} sessions; failing={sparse_cases}"
        ),
    )
    _check(
        checks,
        "minimum_distractor_topology",
        not insufficient_distractors,
        (
            f"every case needs >= {MINIMUM_DISTRACTOR_MESSAGES_PER_CASE} non-required "
            f"messages and >= {MINIMUM_DISTRACTOR_SESSIONS_PER_CASE} non-required "
            f"sessions; failing={insufficient_distractors}"
        ),
    )
    _check(
        checks,
        "single_session_category_semantics",
        not single_session_conflicts,
        (
            "single-session categories must label exactly one required session; "
            f"failing={single_session_conflicts}"
        ),
    )
    _check(
        checks,
        "atomic_required_fact_units",
        not missing_fact_units and not invalid_fact_units,
        (
            "fact units must be non-empty, atomic, and cite exactly the required messages; "
            f"missing={missing_fact_units}, invalid={invalid_fact_units}"
        ),
    )
    return checks


def review_fitness(
    review: dict[str, Any],
    *,
    reviewer: str,
    expected_case_ids: set[str],
    reviewed_source_sha256: str,
) -> list[dict[str, Any]]:
    """Require a passing, exact, finding-free review of the exact reviewed source revision."""

    checks: list[dict[str, Any]] = []
    _check(
        checks,
        f"review_{reviewer}_source_identity",
        review.get("source_sha256") == reviewed_source_sha256,
        (
            "review must cite the exact reviewed author-half digest; "
            f"review={review.get('source_sha256')}, actual={reviewed_source_sha256}"
        ),
    )
    findings = review.get("per_case_findings")
    reviewed_ids = (
        [item.get("case_id") for item in findings if isinstance(item, dict)]
        if isinstance(findings, list)
        else []
    )
    invalid_items = (
        [
            item.get("case_id")
            for item in findings
            if not isinstance(item, dict)
            or item.get("status") != "pass"
            or item.get("findings") != []
        ]
        if isinstance(findings, list)
        else ["<missing>"]
    )
    _check(
        checks,
        f"review_{reviewer}_coverage",
        review.get("schema_version") == 1
        and review.get("reviewer") == reviewer
        and review.get("status") == "pass"
        and len(reviewed_ids) == len(expected_case_ids)
        and len(set(reviewed_ids)) == len(reviewed_ids)
        and set(reviewed_ids) == expected_case_ids,
        f"reviewed={len(reviewed_ids)}, expected={len(expected_case_ids)}",
    )
    _check(
        checks,
        f"review_{reviewer}_findings",
        not invalid_items and review.get("corpus_findings") == [],
        f"nonpassing_or_nonempty_case_findings={invalid_items}",
    )
    return checks


def baseline_fitness(
    baseline: dict[str, Any],
    analysis: dict[str, Any],
    *,
    corpus_sha256: str,
    ordered_case_ids: list[str],
    baseline_sha256: str,
) -> list[dict[str, Any]]:
    """Verify a baseline-only artifact and analysis without evaluating a candidate."""

    checks: list[dict[str, Any]] = []
    questions = baseline.get("questions")
    _check(
        checks,
        "baseline_header",
        baseline.get("schema_version") == 1
        and baseline.get("artifact_type") == "session-density-baseline-input"
        and baseline.get("status") == "completed-baseline-only"
        and baseline.get("corpus_sha256") == corpus_sha256,
        "requires a completed baseline-only artifact tied to the exact corpus",
    )
    _check(
        checks,
        "baseline_non_authorization",
        baseline.get("candidate_executed") is False
        and baseline.get("candidate_results_present") is False
        and baseline.get("hosted_api_calls") == 0
        and baseline.get("sealed_validation_question_records") == 0
        and baseline.get("reserve_question_records") == 0,
        "candidate, hosted API, sealed validation, and reserve use must all be zero",
    )
    question_ids = baseline.get("question_ids")
    _check(
        checks,
        "baseline_question_identity",
        question_ids == ordered_case_ids
        and isinstance(questions, dict)
        and set(questions) == set(ordered_case_ids),
        "baseline question order and records must exactly match the corpus",
    )
    short_pools: list[str] = []
    malformed_pools: list[str] = []
    if isinstance(questions, dict):
        for case_id in ordered_case_ids:
            question = questions.get(case_id, {})
            pool = question.get("ranked_pool") if isinstance(question, dict) else None
            if not isinstance(pool, list):
                malformed_pools.append(case_id)
                continue
            if len(pool) < 12:
                short_pools.append(case_id)
            for result in pool:
                if (
                    not isinstance(result, dict)
                    or not isinstance(result.get("memory_id"), str)
                    or not isinstance(result.get("score"), (int, float))
                    or not isinstance(result.get("metadata", {}).get("session_id"), str)
                ):
                    malformed_pools.append(case_id)
                    break
    _check(
        checks,
        "baseline_ranked_pool_schema",
        not malformed_pools,
        (
            "every ranked result needs memory_id, numeric score, and session_id; "
            f"failing={sorted(set(malformed_pools))}"
        ),
    )
    _check(
        checks,
        "baseline_ranked_pool_depth",
        not short_pools,
        (
            "every case needs at least 12 ranked candidates to test top-10 swaps; "
            f"failing={short_pools}"
        ),
    )
    _check(
        checks,
        "baseline_analysis_header",
        analysis.get("schema_version") == 1
        and analysis.get("artifact_type") == "session-density-baseline-analysis"
        and analysis.get("status") == "completed-baseline-only"
        and analysis.get("baseline_input_sha256") == baseline_sha256
        and analysis.get("candidate_metrics_present") is False,
        "analysis must identify only the exact baseline input and contain no candidate metrics",
    )
    _check(
        checks,
        "baseline_analysis_non_authorization",
        analysis.get("hosted_api_calls") == 0
        and analysis.get("sealed_validation_question_records") == 0
        and analysis.get("reserve_question_records") == 0,
        "baseline analysis must remain API-free and split-isolated",
    )
    return checks


def verify_freeze_readiness(
    *,
    draft_path: Path,
    corpus_path: Path,
    author_a_path: Path,
    author_b_path: Path,
    review_a_of_b_path: Path,
    review_b_of_a_path: Path,
    baseline_input_path: Path | None = None,
    baseline_analysis_path: Path | None = None,
) -> dict[str, Any]:
    """Build a non-mutating readiness report. This function never freezes a contract."""

    draft = _load(draft_path)
    corpus = _load(corpus_path)
    author_a = _load(author_a_path)
    author_b = _load(author_b_path)
    review_a = _load(review_a_of_b_path)
    review_b = _load(review_b_of_a_path)
    checks: list[dict[str, Any]] = []
    _check(
        checks,
        "draft_remains_blocked",
        draft.get("status") in NON_AUTHORIZING_DRAFT_STATUSES
        and draft.get("execution_authorized") is False
        and draft.get("stage_2_paid_paired_answer", {}).get("authorized") is False,
        "readiness verification must not authorize candidate or paid execution",
    )
    fresh = draft.get("required_before_freeze", {}).get("fresh_corpus", {})
    path_hashes = {
        "author_a_sha256": _sha256(author_a_path),
        "author_b_sha256": _sha256(author_b_path),
        "build_script_sha256": _sha256(Path(__file__).with_name("build_session_density_corpus.py")),
        "corpus_sha256": _sha256(corpus_path),
        "review_a_of_b_sha256": _sha256(review_a_of_b_path),
        "review_b_of_a_sha256": _sha256(review_b_of_a_path),
    }
    mismatches = {
        key: {"contract": fresh.get(key), "actual": value}
        for key, value in path_hashes.items()
        if fresh.get(key) != value
    }
    _check(
        checks,
        "recorded_source_hashes",
        not mismatches,
        f"mismatches={mismatches}",
    )
    checks.extend(corpus_fitness(corpus))
    author_a_ids = {
        case.get("id") for case in author_a.get("cases", []) if isinstance(case, dict)
    }
    author_b_ids = {
        case.get("id") for case in author_b.get("cases", []) if isinstance(case, dict)
    }
    checks.extend(
        review_fitness(
            review_a,
            reviewer="A",
            expected_case_ids=author_b_ids,
            reviewed_source_sha256=path_hashes["author_b_sha256"],
        )
    )
    checks.extend(
        review_fitness(
            review_b,
            reviewer="B",
            expected_case_ids=author_a_ids,
            reviewed_source_sha256=path_hashes["author_a_sha256"],
        )
    )

    baseline_present = baseline_input_path is not None and baseline_analysis_path is not None
    _check(
        checks,
        "baseline_input_and_analysis_present",
        baseline_present,
        "both raw baseline input and baseline-only analysis are required before freeze",
    )
    if baseline_present:
        assert baseline_input_path is not None
        assert baseline_analysis_path is not None
        baseline = _load(baseline_input_path)
        analysis = _load(baseline_analysis_path)
        baseline_sha256 = _sha256(baseline_input_path)
        checks.extend(
            baseline_fitness(
                baseline,
                analysis,
                corpus_sha256=_sha256(corpus_path),
                ordered_case_ids=[str(case.get("id")) for case in corpus.get("cases", [])],
                baseline_sha256=baseline_sha256,
            )
        )
        _check(
            checks,
            "draft_baseline_input_hash",
            fresh.get("baseline_input_sha256") == baseline_sha256,
            (
                f"contract={fresh.get('baseline_input_sha256')}, "
                f"actual={baseline_sha256}"
            ),
        )
        _check(
            checks,
            "draft_baseline_analysis_hash",
            fresh.get("baseline_analysis_sha256") == _sha256(baseline_analysis_path),
            (
                f"contract={fresh.get('baseline_analysis_sha256')}, "
                f"actual={_sha256(baseline_analysis_path)}"
            ),
        )

    failed = [check["name"] for check in checks if not check["passed"]]
    return {
        "schema_version": 1,
        "status": "ready-for-explicit-freeze-review" if not failed else "blocked",
        "contract_frozen": False,
        "candidate_execution_authorized": False,
        "paid_execution_authorized": False,
        "sealed_validation_used": False,
        "reserve_used": False,
        "checks": checks,
        "failed_checks": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--author-a", type=Path, required=True)
    parser.add_argument("--author-b", type=Path, required=True)
    parser.add_argument("--review-a-of-b", type=Path, required=True)
    parser.add_argument("--review-b-of-a", type=Path, required=True)
    parser.add_argument("--baseline-input", type=Path)
    parser.add_argument("--baseline-analysis", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.baseline_input) != bool(args.baseline_analysis):
        parser.error("baseline input and analysis must be supplied together")
    report = verify_freeze_readiness(
        draft_path=args.draft,
        corpus_path=args.corpus,
        author_a_path=args.author_a,
        author_b_path=args.author_b,
        review_a_of_b_path=args.review_a_of_b,
        review_b_of_a_path=args.review_b_of_a,
        baseline_input_path=args.baseline_input,
        baseline_analysis_path=args.baseline_analysis,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "ready-for-explicit-freeze-review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
