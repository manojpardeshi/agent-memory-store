#!/usr/bin/env python3
"""Run the frozen paired Kimi answer-quality development comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__:
    from scripts.run_memorybench_claude_pilot import (
        build_answer_prompt,
        build_judge_prompt,
        load_question_dates,
        parse_judge_response,
    )
    from scripts.run_memorybench_kimi_qualification import (
        ANSWER_EFFORT,
        ANSWER_MAX_COMPLETION_TOKENS,
        ANSWER_SYSTEM_PROMPT,
        JUDGE_EFFORT,
        JUDGE_MAX_COMPLETION_TOKENS,
        JUDGE_SYSTEM_PROMPT,
        MODEL,
        build_kimi_request,
        run_kimi_call,
        worst_case_cost_usd,
    )
else:
    from run_memorybench_claude_pilot import (
        build_answer_prompt,
        build_judge_prompt,
        load_question_dates,
        parse_judge_response,
    )
    from run_memorybench_kimi_qualification import (
        ANSWER_EFFORT,
        ANSWER_MAX_COMPLETION_TOKENS,
        ANSWER_SYSTEM_PROMPT,
        JUDGE_EFFORT,
        JUDGE_MAX_COMPLETION_TOKENS,
        JUDGE_SYSTEM_PROMPT,
        MODEL,
        build_kimi_request,
        run_kimi_call,
        worst_case_cost_usd,
    )

EXPERIMENT_ID = "kimi-k3-session-diverse-paired-development60-v1"
QUESTION_COUNT = 60
JUDGE_REPEATS = 3
ARMS = ("baseline", "candidate")
ANSWER_MAX_CALL_USD = 0.25
JUDGE_MAX_CALL_USD = 0.05
MAX_TOTAL_USD = 5.0


class PairedDevelopmentError(RuntimeError):
    """Raised when a paired run violates its frozen inputs or execution contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PairedDevelopmentError(f"expected a JSON object: {path}")
    return value


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_api_key(*, keychain_service: str | None, environment: dict[str, str]) -> str:
    """Load the API key without placing it in arguments, output, or the report."""
    if keychain_service:
        try:
            process = subprocess.run(
                ["security", "find-generic-password", "-s", keychain_service, "-w"],
                capture_output=True,
                check=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise PairedDevelopmentError("could not retrieve the Kimi key from Keychain") from error
        key = process.stdout.strip()
        if not key:
            raise PairedDevelopmentError("Keychain returned an empty Kimi API key")
        return key
    key = environment.get("MOONSHOT_API_KEY", "").strip()
    if not key:
        raise PairedDevelopmentError(
            "MOONSHOT_API_KEY or --keychain-service is required"
        )
    return key


def arm_order_for_question(question_id: str) -> tuple[str, str]:
    """Balance which stateless arm is called first with a reproducible hash rule."""
    order_key = f"{EXPERIMENT_ID}{question_id}"
    if hashlib.sha256(order_key.encode()).digest()[0] % 2 == 0:
        return ARMS
    return tuple(reversed(ARMS))


def _context_json_bytes(results: list[dict[str, Any]]) -> int:
    return len(json.dumps(results, indent=2, ensure_ascii=False).encode())


def _merge_completed_checkpoints(
    checkpoints: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {}
    for checkpoint in checkpoints:
        if checkpoint.get("status") != "completed":
            raise PairedDevelopmentError("every baseline checkpoint must be completed")
        checkpoint_questions = checkpoint.get("questions")
        if not isinstance(checkpoint_questions, dict):
            raise PairedDevelopmentError("baseline checkpoint has no questions object")
        for question_id in checkpoint.get("targetQuestionIds", []):
            if question_id in questions:
                raise PairedDevelopmentError(f"duplicate baseline question {question_id}")
            try:
                questions[question_id] = checkpoint_questions[question_id]
            except KeyError as error:
                raise PairedDevelopmentError(
                    f"baseline checkpoint omits question {question_id}"
                ) from error
    return questions


def _validate_inputs(
    *,
    selection: dict[str, Any],
    selection_sha256: str,
    development: dict[str, Any],
    development_sha256: str,
    baseline_checkpoints: list[dict[str, Any]],
    baseline_sha256: list[str],
    candidate: dict[str, Any],
    candidate_sha256: str,
    contract: dict[str, Any],
    contract_sha256: str,
) -> tuple[tuple[str, ...], dict[str, dict[str, Any]]]:
    if MODEL != "kimi-k3":
        raise PairedDevelopmentError("runner requires exact model kimi-k3")
    if (
        contract.get("status") != "frozen-before-paid-run"
        or contract.get("experiment_id") != EXPERIMENT_ID
    ):
        raise PairedDevelopmentError("expected the frozen paired development contract")
    if (
        development.get("role") != "development"
        or development.get("sealed") is not False
        or development.get("question_count") != 180
    ):
        raise PairedDevelopmentError("expected the unsealed 180-question development manifest")
    if development.get("observed_selection_sha256") != selection_sha256:
        raise PairedDevelopmentError("selection is not the frozen observed development selection")
    contract_selection = contract.get("selection", {})
    if (
        contract_selection.get("sha256") != selection_sha256
        or contract_selection.get("development_manifest_sha256") != development_sha256
        or contract_selection.get("questions") != QUESTION_COUNT
    ):
        raise PairedDevelopmentError("selection or manifest differs from the frozen contract")
    question_ids_value = selection.get("question_ids")
    if not isinstance(question_ids_value, list) or len(question_ids_value) != QUESTION_COUNT:
        raise PairedDevelopmentError("selection must contain exactly 60 questions")
    question_ids = tuple(question_ids_value)
    if len(set(question_ids)) != QUESTION_COUNT:
        raise PairedDevelopmentError("selection contains duplicate question IDs")
    development_ids = development.get("question_ids")
    if not isinstance(development_ids, list) or not set(question_ids).issubset(development_ids):
        raise PairedDevelopmentError("selection reaches outside the unsealed development split")
    if candidate.get("status") != "completed":
        raise PairedDevelopmentError("session-diverse candidate replay must be completed")
    if candidate.get("manifest_sha256") != development_sha256:
        raise PairedDevelopmentError("candidate identifies a different development manifest")
    if candidate.get("question_ids") != development_ids:
        raise PairedDevelopmentError("candidate does not cover the exact development manifest")
    if candidate.get("source_checkpoint_sha256") != sorted(baseline_sha256):
        # The candidate replay covers 180 development questions and may therefore identify
        # additional checkpoints. The paid 60-question run is bound separately below to the
        # exact baseline checkpoint frozen in its contract.
        candidate_source_hashes = candidate.get("source_checkpoint_sha256")
        if not isinstance(candidate_source_hashes, list) or not set(baseline_sha256).issubset(
            candidate_source_hashes
        ):
            raise PairedDevelopmentError("candidate identifies different baseline checkpoints")
    contract_sources = contract.get("sources", {})
    if baseline_sha256 != [contract_sources.get("baseline_checkpoint_sha256")]:
        raise PairedDevelopmentError("baseline checkpoint differs from the frozen contract")
    if candidate.get("gate_sha256") != contract_sources.get(
        "session_diverse_retrieval_gates_sha256"
    ):
        raise PairedDevelopmentError("candidate retrieval gate differs from the frozen contract")
    if contract_sources.get("session_diverse_raw_sha256") != candidate_sha256:
        raise PairedDevelopmentError("candidate replay differs from the frozen contract")
    if contract.get("arms") != {
        "baseline": "released-ranked-top-10",
        "candidate": "session-diverse-v1",
    }:
        raise PairedDevelopmentError("frozen contract arms are unsupported")
    if candidate.get("context_policy") != contract.get("candidate_policy"):
        raise PairedDevelopmentError("candidate policy differs from the frozen contract")
    expected_protocol = contract.get("model_protocol", {})
    source_dir = Path(__file__).resolve().parent
    if (
        expected_protocol.get("exact_model") != MODEL
        or expected_protocol.get("answer_repeats") != 1
        or expected_protocol.get("judge_repeats") != JUDGE_REPEATS
        or expected_protocol.get("answer_reasoning_effort") != ANSWER_EFFORT
        or expected_protocol.get("answer_max_completion_tokens")
        != ANSWER_MAX_COMPLETION_TOKENS
        or expected_protocol.get("answer_system_prompt_sha256")
        != _sha256_text(ANSWER_SYSTEM_PROMPT)
        or expected_protocol.get("judge_reasoning_effort") != JUDGE_EFFORT
        or expected_protocol.get("judge_max_completion_tokens")
        != JUDGE_MAX_COMPLETION_TOKENS
        or expected_protocol.get("judge_system_prompt_sha256")
        != _sha256_text(JUDGE_SYSTEM_PROMPT)
        or expected_protocol.get("prompt_builder_source_sha256")
        != _sha256(source_dir / "run_memorybench_claude_pilot.py")
        or expected_protocol.get("request_builder_source_sha256")
        != _sha256(source_dir / "run_memorybench_kimi_qualification.py")
    ):
        raise PairedDevelopmentError("model protocol differs from runner constants")
    expected_budget = contract.get("budget", {})
    if expected_budget != {
        "maximum_total_cost_usd": MAX_TOTAL_USD,
        "maximum_answer_call_cost_usd": ANSWER_MAX_CALL_USD,
        "maximum_judge_call_cost_usd": JUDGE_MAX_CALL_USD,
        "single_shared_ledger": True,
        "pre_call_worst_case_reservation_required": True,
    }:
        raise PairedDevelopmentError("budget protocol differs from runner constants")
    if not isinstance(contract_sha256, str) or len(contract_sha256) != 64:
        raise PairedDevelopmentError("frozen contract hash is invalid")
    candidate_questions = candidate.get("questions")
    if not isinstance(candidate_questions, dict) or set(candidate_questions) != set(
        development_ids
    ):
        raise PairedDevelopmentError("candidate development results are incomplete")

    baseline_questions = _merge_completed_checkpoints(baseline_checkpoints)
    if any(question_id not in baseline_questions for question_id in question_ids):
        raise PairedDevelopmentError("a selected question is absent from baseline checkpoints")
    expected_counts = selection.get("question_type_counts")
    actual_counts: dict[str, int] = {}
    for question_id in question_ids:
        question = baseline_questions[question_id]
        question_type = question.get("questionType")
        actual_counts[question_type] = actual_counts.get(question_type, 0) + 1
        candidate_question = candidate_questions[question_id]
        if candidate_question.get("question_type") != question_type:
            raise PairedDevelopmentError(f"question type differs for {question_id}")
        baseline_results = question.get("phases", {}).get("search", {}).get("results")
        candidate_results = candidate_question.get("results")
        if not isinstance(baseline_results, list) or not isinstance(candidate_results, list):
            raise PairedDevelopmentError(f"missing paired context for {question_id}")
        if len(candidate_results) != len(baseline_results):
            raise PairedDevelopmentError(f"paired result count differs for {question_id}")
        baseline_ids = [item.get("memory_id") for item in baseline_results]
        ranked_ids = candidate_question.get("diagnostics", {}).get(
            "ranked_pool_top_10_memory_ids"
        )
        if not isinstance(ranked_ids, list) or ranked_ids[: len(baseline_ids)] != baseline_ids:
            raise PairedDevelopmentError(f"base ranking differs for {question_id}")
        if candidate_question.get("context_json_bytes") != _context_json_bytes(
            candidate_results
        ):
            raise PairedDevelopmentError(f"candidate context byte count differs for {question_id}")
    if actual_counts != expected_counts:
        raise PairedDevelopmentError("selection question-type counts differ from baseline")
    return question_ids, baseline_questions


def _input_identity(
    *,
    selection_sha256: str,
    development_sha256: str,
    candidate_sha256: str,
    baseline_sha256: list[str],
    contract_sha256: str,
) -> dict[str, Any]:
    files = {
        "contract_sha256": contract_sha256,
        "selection_sha256": selection_sha256,
        "development_manifest_sha256": development_sha256,
        "candidate_replay_sha256": candidate_sha256,
        "baseline_checkpoint_sha256": sorted(baseline_sha256),
    }
    return {**files, "combined_sha256": _canonical_sha256(files)}


def _protocols(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_protocol": contract["model_protocol"],
        "budget": contract["budget"],
        "execution": {
            "fresh_answers": True,
            "answer_calls": QUESTION_COUNT * len(ARMS),
            "judge_calls": QUESTION_COUNT * len(ARMS) * JUDGE_REPEATS,
            "question_paired_and_arm_interleaved": True,
        },
    }


def _new_report(
    *,
    question_ids: tuple[str, ...],
    identity: dict[str, Any],
    contract: dict[str, Any],
    question_dates_supplied: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "running",
        "question_dates_supplied": question_dates_supplied,
        "experiment_id": EXPERIMENT_ID,
        "model": MODEL,
        "question_ids": list(question_ids),
        "arm_order": list(ARMS),
        "arm_order_by_question": {
            question_id: list(arm_order_for_question(question_id))
            for question_id in question_ids
        },
        "arms": contract["arms"],
        "context_metrics": contract["preflight_context_json_bytes"],
        "input_identity": identity,
        "split_guard": {
            "role": "development",
            "sealed": False,
            "sealed_validation_opened": False,
            "sealed_competitor_reserve_opened": False,
        },
        "protocols": _protocols(contract),
        "budget": {
            "max_total_usd": MAX_TOTAL_USD,
            "spent_usd": 0.0,
            "unreconciled_reservations_usd": 0.0,
        },
        "in_flight": None,
        "retry_events": [],
        "unreconciled_calls": [],
        "answers": {},
        "judgments": {},
        "started_at": datetime.now(UTC).isoformat(),
    }


def _contexts(
    question_id: str,
    baseline_questions: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "baseline": baseline_questions[question_id]["phases"]["search"]["results"],
        "candidate": candidate["questions"][question_id]["results"],
    }


def _usage_cost(record: dict[str, Any]) -> float:
    try:
        return float(record["usage"]["calculated_cost_usd"])
    except (KeyError, TypeError, ValueError) as error:
        raise PairedDevelopmentError("saved call has invalid usage cost") from error


def _validate_saved_call(
    record: dict[str, Any],
    *,
    prompt: str,
    judge: bool,
) -> None:
    if record.get("prompt_sha256") != _sha256_text(prompt):
        raise PairedDevelopmentError("saved prompt hash differs on resume")
    body = build_kimi_request(
        prompt,
        system_prompt=JUDGE_SYSTEM_PROMPT if judge else ANSWER_SYSTEM_PROMPT,
        reasoning_effort=JUDGE_EFFORT if judge else ANSWER_EFFORT,
        max_completion_tokens=(
            JUDGE_MAX_COMPLETION_TOKENS if judge else ANSWER_MAX_COMPLETION_TOKENS
        ),
        judge=judge,
    )
    if record.get("request_sha256") != hashlib.sha256(body).hexdigest():
        raise PairedDevelopmentError("saved request hash differs on resume")
    cost = _usage_cost(record)
    ceiling = JUDGE_MAX_CALL_USD if judge else ANSWER_MAX_CALL_USD
    if cost < 0 or cost > ceiling + 1e-9:
        raise PairedDevelopmentError("saved call cost violates its per-call ceiling")


def _answer_date(
    question_id: str,
    question: dict[str, Any],
    question_dates: dict[str, str] | None,
) -> str | None:
    """Resolve the prompt's question date identically for fresh calls and resume checks.

    Without a dataset this returns the checkpoint value, which the retrieval-only phase list
    never populates, so prompts render "Not specified" exactly as every recorded paired run
    did. That keeps recorded evidence reproducible. With a dataset the date is supplied.
    """
    return (question_dates or {}).get(question_id) or question.get("questionDate")


def _validate_resume(
    report: dict[str, Any],
    *,
    question_ids: tuple[str, ...],
    identity: dict[str, Any],
    contract: dict[str, Any],
    baseline_questions: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
    question_dates: dict[str, str] | None = None,
) -> None:
    if bool(report.get("question_dates_supplied", False)) != bool(question_dates):
        raise PairedDevelopmentError(
            "resume would mix prompts with and without question dates; "
            "rerun with the same --dataset setting as the original report"
        )
    expected = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "model": MODEL,
        "question_ids": list(question_ids),
        "arm_order": list(ARMS),
        "arm_order_by_question": {
            question_id: list(arm_order_for_question(question_id))
            for question_id in question_ids
        },
        "arms": contract["arms"],
        "context_metrics": contract["preflight_context_json_bytes"],
        "input_identity": identity,
        "protocols": _protocols(contract),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise PairedDevelopmentError(f"resume identity mismatch: {key}")
    budget = report.get("budget", {})
    if budget.get("max_total_usd") != MAX_TOTAL_USD:
        raise PairedDevelopmentError("resume identity mismatch: budget")
    answers = report.get("answers")
    judgments = report.get("judgments")
    if not isinstance(answers, dict) or not isinstance(judgments, dict):
        raise PairedDevelopmentError("saved answers or judgments are invalid")
    if not set(answers).issubset(question_ids) or not set(judgments).issubset(question_ids):
        raise PairedDevelopmentError("saved output contains an out-of-split question")

    saved_cost = 0.0
    for question_id, answer_arms in answers.items():
        if not isinstance(answer_arms, dict) or not set(answer_arms).issubset(ARMS):
            raise PairedDevelopmentError("saved answer contains an invalid arm")
        question = baseline_questions[question_id]
        contexts = _contexts(question_id, baseline_questions, candidate)
        for arm, record in answer_arms.items():
            if record.get("question_type") != question["questionType"]:
                raise PairedDevelopmentError("saved answer question type differs")
            if record.get("context_json_bytes") != _context_json_bytes(contexts[arm]):
                raise PairedDevelopmentError("saved answer context bytes differ")
            prompt = build_answer_prompt(
                question["question"],
                contexts[arm],
                _answer_date(question_id, question, question_dates),
            )
            _validate_saved_call(record, prompt=prompt, judge=False)
            if not isinstance(record.get("answer"), str) or not record["answer"].strip():
                raise PairedDevelopmentError("saved answer is empty")
            saved_cost += _usage_cost(record)
    for question_id, judgment_arms in judgments.items():
        if not isinstance(judgment_arms, dict) or not set(judgment_arms).issubset(ARMS):
            raise PairedDevelopmentError("saved judgment contains an invalid arm")
        question = baseline_questions[question_id]
        for arm, votes in judgment_arms.items():
            try:
                answer = answers[question_id][arm]["answer"]
            except (KeyError, TypeError) as error:
                raise PairedDevelopmentError("saved judgment has no paired answer") from error
            if not isinstance(votes, dict) or not set(votes).issubset(
                {str(index) for index in range(JUDGE_REPEATS)}
            ):
                raise PairedDevelopmentError("saved judgment has an invalid repeat")
            prompt = build_judge_prompt(
                question["question"],
                question["groundTruth"],
                answer,
                question["questionType"],
            )
            for record in votes.values():
                _validate_saved_call(record, prompt=prompt, judge=True)
                parsed = parse_judge_response(record.get("raw_response", ""))
                if any(record.get(key) != parsed[key] for key in parsed):
                    raise PairedDevelopmentError("saved judgment differs from raw response")
                saved_cost += _usage_cost(record)
    unreconciled = float(budget.get("unreconciled_reservations_usd", 0.0))
    spent = float(budget.get("spent_usd", -1.0))
    if not math.isclose(spent, saved_cost + unreconciled, abs_tol=1e-8):
        raise PairedDevelopmentError("saved shared budget ledger does not reconcile")
    if spent > MAX_TOTAL_USD + 1e-9:
        raise PairedDevelopmentError("saved run exceeded the shared budget")


def _recover_in_flight(report: dict[str, Any], output: Path) -> None:
    pending = report.get("in_flight")
    if pending is None:
        return
    if not isinstance(pending, dict) or pending.get("reserved_usd") not in (
        ANSWER_MAX_CALL_USD,
        JUDGE_MAX_CALL_USD,
    ):
        raise PairedDevelopmentError("saved in-flight reservation is invalid")
    reserved = float(pending["reserved_usd"])
    report["budget"]["spent_usd"] = round(
        float(report["budget"]["spent_usd"]) + reserved, 9
    )
    report["budget"]["unreconciled_reservations_usd"] = round(
        float(report["budget"]["unreconciled_reservations_usd"]) + reserved, 9
    )
    report["unreconciled_calls"].append(pending)
    report["in_flight"] = None
    _atomic_write_json(output, report)


def _recover_known_http_429(report: dict[str, Any], output: Path) -> None:
    """Record one observed no-response HTTP 429 and reissue its exact request slot."""

    pending = report.get("in_flight")
    if not isinstance(pending, dict):
        raise PairedDevelopmentError("HTTP 429 recovery requires one saved in-flight call")
    retry_events = report.setdefault("retry_events", [])
    if not isinstance(retry_events, list) or retry_events:
        raise PairedDevelopmentError("only one HTTP 429 recovery is allowed")
    retry_events.append(
        {
            "slot": pending.get("slot"),
            "request_sha256": pending.get("request_sha256"),
            "reason": "HTTP 429 before a response or usage record",
            "charged_usd": 0.0,
            "identical_request_reissue": True,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
    )
    report["in_flight"] = None
    _atomic_write_json(output, report)


def _remaining_budget(report: dict[str, Any]) -> float:
    return MAX_TOTAL_USD - float(report["budget"]["spent_usd"])


def _begin_call(
    report: dict[str, Any],
    output: Path,
    *,
    slot: str,
    body: bytes,
    max_completion_tokens: int,
    max_call_usd: float,
) -> None:
    worst = worst_case_cost_usd(body, max_completion_tokens)
    if worst > max_call_usd + 1e-9:
        raise PairedDevelopmentError(
            f"request worst-case cost ${worst:.6f} exceeds ${max_call_usd:.6f} for {slot}"
        )
    if _remaining_budget(report) + 1e-9 < max_call_usd:
        raise PairedDevelopmentError(
            f"remaining shared budget cannot reserve ${max_call_usd:.2f} for {slot}"
        )
    report["in_flight"] = {
        "slot": slot,
        "request_sha256": hashlib.sha256(body).hexdigest(),
        "reserved_usd": max_call_usd,
        "reserved_at": datetime.now(UTC).isoformat(),
    }
    _atomic_write_json(output, report)


def _finish_call(
    report: dict[str, Any],
    output: Path,
    call: dict[str, Any],
    destination: dict[str, Any],
    record: dict[str, Any],
) -> None:
    cost = float(call["usage"]["calculated_cost_usd"])
    report["budget"]["spent_usd"] = round(
        float(report["budget"]["spent_usd"]) + cost, 9
    )
    if report["budget"]["spent_usd"] > MAX_TOTAL_USD + 1e-9:
        raise PairedDevelopmentError("paired run exceeded the shared budget")
    destination.update(record)
    report["in_flight"] = None
    _atomic_write_json(output, report)


def _call_record(call: dict[str, Any], *, prompt: str) -> dict[str, Any]:
    return {
        "prompt_sha256": _sha256_text(prompt),
        "duration_ms": call["duration_ms"],
        "request_sha256": call["request_sha256"],
        "usage": call["usage"],
    }


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    arm_summary: dict[str, dict[str, Any]] = {}
    majority: dict[str, dict[str, int]] = {}
    for question_id in report["question_ids"]:
        majority[question_id] = {}
        for arm in ARMS:
            score = int(
                sum(
                    int(report["judgments"][question_id][arm][str(repeat)]["score"])
                    for repeat in range(JUDGE_REPEATS)
                )
                >= 2
            )
            majority[question_id][arm] = score
    for arm in ARMS:
        correct = sum(scores[arm] for scores in majority.values())
        arm_summary[arm] = {
            "majority_correct": correct,
            "majority_accuracy": correct / QUESTION_COUNT,
        }
    return {
        "questions": QUESTION_COUNT,
        "answers_completed": QUESTION_COUNT * len(ARMS),
        "judge_calls_completed": QUESTION_COUNT * len(ARMS) * JUDGE_REPEATS,
        "arms": arm_summary,
        "paired": {
            "both_correct": sum(
                scores["baseline"] == scores["candidate"] == 1
                for scores in majority.values()
            ),
            "both_incorrect": sum(
                scores["baseline"] == scores["candidate"] == 0
                for scores in majority.values()
            ),
            "baseline_only_correct": sum(
                scores["baseline"] == 1 and scores["candidate"] == 0
                for scores in majority.values()
            ),
            "candidate_only_correct": sum(
                scores["baseline"] == 0 and scores["candidate"] == 1
                for scores in majority.values()
            ),
        },
        "human_audit_complete": False,
    }


def run_paired_development(
    *,
    selection_path: Path,
    development_manifest_path: Path,
    contract_path: Path,
    baseline_checkpoint_paths: list[Path],
    candidate_path: Path,
    output: Path,
    api_key: str,
    timeout_seconds: int,
    recover_known_http_429: bool = False,
    question_dates: dict[str, str] | None = None,
) -> dict[str, Any]:
    selection = _load(selection_path)
    development = _load(development_manifest_path)
    candidate = _load(candidate_path)
    contract = _load(contract_path)
    baseline_checkpoints = [_load(path) for path in baseline_checkpoint_paths]
    selection_sha256 = _sha256(selection_path)
    development_sha256 = _sha256(development_manifest_path)
    candidate_sha256 = _sha256(candidate_path)
    baseline_sha256 = [_sha256(path) for path in baseline_checkpoint_paths]
    contract_sha256 = _sha256(contract_path)
    question_ids, baseline_questions = _validate_inputs(
        selection=selection,
        selection_sha256=selection_sha256,
        development=development,
        development_sha256=development_sha256,
        baseline_checkpoints=baseline_checkpoints,
        baseline_sha256=baseline_sha256,
        candidate=candidate,
        candidate_sha256=candidate_sha256,
        contract=contract,
        contract_sha256=contract_sha256,
    )
    identity = _input_identity(
        selection_sha256=selection_sha256,
        development_sha256=development_sha256,
        candidate_sha256=candidate_sha256,
        baseline_sha256=baseline_sha256,
        contract_sha256=contract_sha256,
    )
    if output.exists():
        report = _load(output)
        _validate_resume(
            report,
            question_ids=question_ids,
            identity=identity,
            contract=contract,
            baseline_questions=baseline_questions,
            candidate=candidate,
            question_dates=question_dates,
        )
        if recover_known_http_429:
            _recover_known_http_429(report, output)
        else:
            _recover_in_flight(report, output)
        report["status"] = "running"
        _atomic_write_json(output, report)
    else:
        report = _new_report(
            question_ids=question_ids,
            identity=identity,
            contract=contract,
            question_dates_supplied=bool(question_dates),
        )
        _atomic_write_json(output, report)

    for question_id in question_ids:
        question = baseline_questions[question_id]
        contexts = _contexts(question_id, baseline_questions, candidate)
        answers = report["answers"].setdefault(question_id, {})
        judgments = report["judgments"].setdefault(question_id, {})
        ordered_arms = arm_order_for_question(question_id)
        for arm in ordered_arms:
            if arm in answers:
                continue
            prompt = build_answer_prompt(
                question["question"],
                contexts[arm],
                _answer_date(question_id, question, question_dates),
            )
            body = build_kimi_request(
                prompt,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                reasoning_effort=ANSWER_EFFORT,
                max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
                judge=False,
            )
            slot = f"answer:{question_id}:{arm}"
            _begin_call(
                report,
                output,
                slot=slot,
                body=body,
                max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
                max_call_usd=ANSWER_MAX_CALL_USD,
            )
            call = run_kimi_call(
                api_key,
                body,
                max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
                max_call_usd=ANSWER_MAX_CALL_USD,
                timeout_seconds=timeout_seconds,
            )
            record = {
                "question_type": question["questionType"],
                "context_json_bytes": _context_json_bytes(contexts[arm]),
                "answer": call["result"],
                **_call_record(call, prompt=prompt),
            }
            answers[arm] = {}
            _finish_call(report, output, call, answers[arm], record)
            print(
                f"answered paired question {question_id}; total "
                f"${report['budget']['spent_usd']:.6f}",
                flush=True,
            )

        for repeat in range(JUDGE_REPEATS):
            judge_arm_order = ordered_arms if repeat % 2 == 0 else tuple(reversed(ordered_arms))
            for arm in judge_arm_order:
                arm_judgments = judgments.setdefault(arm, {})
                repeat_key = str(repeat)
                if repeat_key in arm_judgments:
                    continue
                answer = answers[arm]["answer"]
                prompt = build_judge_prompt(
                    question["question"],
                    question["groundTruth"],
                    answer,
                    question["questionType"],
                )
                body = build_kimi_request(
                    prompt,
                    system_prompt=JUDGE_SYSTEM_PROMPT,
                    reasoning_effort=JUDGE_EFFORT,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    judge=True,
                )
                slot = f"judge:{question_id}:{arm}:{repeat}"
                _begin_call(
                    report,
                    output,
                    slot=slot,
                    body=body,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    max_call_usd=JUDGE_MAX_CALL_USD,
                )
                call = run_kimi_call(
                    api_key,
                    body,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    max_call_usd=JUDGE_MAX_CALL_USD,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    parsed = parse_judge_response(str(call["result"]))
                except RuntimeError as error:
                    raise PairedDevelopmentError("Kimi judge returned invalid JSON") from error
                record = {
                    **parsed,
                    "raw_response": call["result"],
                    **_call_record(call, prompt=prompt),
                }
                arm_judgments[repeat_key] = {}
                _finish_call(
                    report,
                    output,
                    call,
                    arm_judgments[repeat_key],
                    record,
                )

    report["summary"] = _summary(report)
    report["status"] = "completed"
    report["completed_at"] = datetime.now(UTC).isoformat()
    _atomic_write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--development-manifest", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--baseline-checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keychain-service")
    parser.add_argument(
        "--recover-known-http-429",
        action="store_true",
        help="record and identically reissue one observed no-response HTTP 429 slot",
    )
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "pinned LongMemEval dataset; supplies question_date to answer prompts. Omit only "
            "to reproduce a recorded report made without dates"
        ),
    )
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")
    try:
        api_key = load_api_key(
            keychain_service=args.keychain_service,
            environment=dict(os.environ),
        )
        report = run_paired_development(
            selection_path=args.selection.resolve(),
            development_manifest_path=args.development_manifest.resolve(),
            contract_path=args.contract.resolve(),
            baseline_checkpoint_paths=[path.resolve() for path in args.baseline_checkpoint],
            candidate_path=args.candidate.resolve(),
            output=args.output.resolve(),
            api_key=api_key,
            timeout_seconds=args.timeout_seconds,
            recover_known_http_429=args.recover_known_http_429,
            question_dates=load_question_dates(args.dataset) if args.dataset else None,
        )
    except PairedDevelopmentError as error:
        parser.error(str(error))
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"total cost: ${report['budget']['spent_usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
