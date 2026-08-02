#!/usr/bin/env python3
"""Run a resumable, budget-bounded Kimi K3 evaluator qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

if __package__:
    from scripts.probe_kimi_api import API_URL, MODEL, ProbeError, calculate_cost_usd
    from scripts.run_memorybench_claude_pilot import (
        SYSTEM_PROMPT,
        build_answer_prompt,
        build_judge_prompt,
        load_selection,
        parse_judge_response,
    )
else:
    from probe_kimi_api import API_URL, MODEL, ProbeError, calculate_cost_usd
    from run_memorybench_claude_pilot import (
        SYSTEM_PROMPT,
        build_answer_prompt,
        build_judge_prompt,
        load_selection,
        parse_judge_response,
    )

ANSWER_EFFORT = "high"
JUDGE_EFFORT = "low"
ANSWER_MAX_COMPLETION_TOKENS = 4096
JUDGE_MAX_COMPLETION_TOKENS = 1024
ANSWER_SYSTEM_PROMPT = SYSTEM_PROMPT
JUDGE_SYSTEM_PROMPT = (
    "You are a strict benchmark judge. Follow the rubric exactly and return only the "
    "required JSON object."
)
CONTEXT_MODES = ("retrieved", "empty")


class QualificationError(RuntimeError):
    """Raised when the Kimi qualification violates its frozen contract."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _response_format_for_judge() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "longmemeval_judgment",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "score": {"type": "integer", "enum": [0, 1]},
                    "label": {"type": "string", "enum": ["correct", "incorrect"]},
                    "explanation": {"type": "string"},
                },
                "required": ["score", "label", "explanation"],
                "additionalProperties": False,
            },
        },
    }


def build_kimi_request(
    prompt: str,
    *,
    system_prompt: str,
    reasoning_effort: str,
    max_completion_tokens: int,
    judge: bool,
) -> bytes:
    payload: dict[str, Any] = {
        "model": MODEL,
        "reasoning_effort": reasoning_effort,
        "max_completion_tokens": max_completion_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
    }
    if judge:
        payload["response_format"] = _response_format_for_judge()
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def worst_case_cost_usd(body: bytes, max_completion_tokens: int) -> float:
    # A tokenizer cannot emit more ordinary text tokens than UTF-8 bytes. The additional
    # 1,024-token allowance covers protocol framing and special tokens not represented in body.
    input_token_bound = len(body) + 1024
    return (input_token_bound * 3.00 + max_completion_tokens * 15.00) / 1_000_000


def run_kimi_call(
    api_key: str,
    body: bytes,
    *,
    max_completion_tokens: int,
    max_call_usd: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    worst_cost = worst_case_cost_usd(body, max_completion_tokens)
    if worst_cost > max_call_usd:
        raise QualificationError(
            f"request worst-case cost ${worst_cost:.6f} exceeds per-call ceiling "
            f"${max_call_usd:.6f}"
        )
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        raise QualificationError(f"Kimi API returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise QualificationError("Kimi API connection failed") from error
    duration_ms = round((time.monotonic() - started) * 1000)

    if payload.get("model") != MODEL:
        raise QualificationError(
            f"expected response model {MODEL!r}, got {payload.get('model')!r}"
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise QualificationError("Kimi response must contain exactly one choice")
    choice = choices[0]
    if choice.get("finish_reason") != "stop":
        raise QualificationError(
            f"Kimi response did not finish normally: {choice.get('finish_reason')!r}"
        )
    content = choice.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise QualificationError("Kimi response content was empty")
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        raise QualificationError("Kimi response did not include token usage")
    cost = calculate_cost_usd(usage)
    actual_cost = float(cost["calculated_cost_usd"])
    if actual_cost > max_call_usd + 1e-9:
        raise QualificationError(
            f"Kimi call cost ${actual_cost:.6f} exceeded ${max_call_usd:.6f}"
        )
    details = usage.get("completion_tokens_details") or {}
    return {
        "result": content.strip(),
        "duration_ms": duration_ms,
        "request_sha256": hashlib.sha256(body).hexdigest(),
        "usage": {
            **cost,
            "reasoning_tokens": int(details.get("reasoning_tokens", 0)),
        },
    }


def _load_source(
    root: Path,
    run_id: str,
    question_ids: tuple[str, ...],
) -> tuple[Path, dict[str, Any]]:
    checkpoint_path = root / "data" / "runs" / run_id / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    target_ids = checkpoint.get("targetQuestionIds")
    if not isinstance(target_ids, list) or not set(question_ids).issubset(target_ids):
        raise QualificationError("qualification selection is not a subset of the source run")
    if checkpoint.get("status") != "completed":
        raise QualificationError("source MemoryBench run is not complete")
    return checkpoint_path, checkpoint


def _new_report(
    *,
    root: Path,
    run_id: str,
    checkpoint_path: Path,
    checkpoint: dict[str, Any],
    question_ids: tuple[str, ...],
    selection_sha256: str | None,
    max_call_usd: float,
    max_total_usd: float,
    context_mode: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "running",
        "model": MODEL,
        "source_run_id": run_id,
        "source_checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        "memorybench_root": str(root),
        "question_ids": list(question_ids),
        "selection_sha256": selection_sha256,
        "source_provider": checkpoint.get("provider"),
        "source_benchmark": checkpoint.get("benchmark"),
        "context_protocol": {
            "mode": context_mode,
            "expected_empty_context_behavior": (
                "I don't know" if context_mode == "empty" else None
            ),
        },
        "answer_protocol": {
            "reasoning_effort": ANSWER_EFFORT,
            "max_completion_tokens": ANSWER_MAX_COMPLETION_TOKENS,
            "system_prompt_sha256": _sha256_text(ANSWER_SYSTEM_PROMPT),
        },
        "judge_protocol": {
            "reasoning_effort": JUDGE_EFFORT,
            "max_completion_tokens": JUDGE_MAX_COMPLETION_TOKENS,
            "system_prompt_sha256": _sha256_text(JUDGE_SYSTEM_PROMPT),
            "same_base_model_as_answerer": True,
        },
        "budget": {
            "max_call_usd": max_call_usd,
            "max_total_usd": max_total_usd,
            "spent_usd": 0.0,
        },
        "answers": {},
        "judgments": {},
    }


def _remaining_budget(report: dict[str, Any]) -> float:
    return float(report["budget"]["max_total_usd"]) - float(report["budget"]["spent_usd"])


def _record_cost(report: dict[str, Any], call: dict[str, Any]) -> None:
    cost = float(call["usage"]["calculated_cost_usd"])
    report["budget"]["spent_usd"] = round(float(report["budget"]["spent_usd"]) + cost, 9)
    if report["budget"]["spent_usd"] > report["budget"]["max_total_usd"] + 1e-9:
        raise QualificationError("qualification exceeded its total budget")


def _ensure_budget(report: dict[str, Any], body: bytes, max_completion_tokens: int) -> None:
    required = worst_case_cost_usd(body, max_completion_tokens)
    if _remaining_budget(report) + 1e-9 < required:
        raise QualificationError(
            f"remaining budget cannot cover worst-case next call: ${required:.6f}"
        )


def run_qualification(
    *,
    root: Path,
    run_id: str,
    output: Path,
    api_key: str,
    question_ids: tuple[str, ...],
    selection_sha256: str | None,
    answer_repeats: int,
    judge_repeats: int,
    max_call_usd: float,
    max_total_usd: float,
    timeout_seconds: int,
    context_mode: str = "retrieved",
) -> dict[str, Any]:
    if context_mode not in CONTEXT_MODES:
        raise QualificationError(f"unsupported context mode: {context_mode!r}")
    checkpoint_path, checkpoint = _load_source(root, run_id, question_ids)
    checkpoint_sha256 = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        if report.get("model") != MODEL:
            raise QualificationError("existing report uses a different model")
        if report.get("source_checkpoint_sha256") != checkpoint_sha256:
            raise QualificationError("existing report uses a different source checkpoint")
        if report.get("question_ids") != list(question_ids):
            raise QualificationError("existing report uses a different selection")
        existing_context_mode = report.get("context_protocol", {}).get(
            "mode", "retrieved"
        )
        if existing_context_mode != context_mode:
            raise QualificationError("existing report uses a different context mode")
        if report.get("budget", {}).get("max_call_usd") != max_call_usd:
            raise QualificationError("existing report uses a different per-call budget")
        if report.get("budget", {}).get("max_total_usd") != max_total_usd:
            raise QualificationError("existing report uses a different total budget")
        report["status"] = "running"
    else:
        report = _new_report(
            root=root,
            run_id=run_id,
            checkpoint_path=checkpoint_path,
            checkpoint=checkpoint,
            question_ids=question_ids,
            selection_sha256=selection_sha256,
            max_call_usd=max_call_usd,
            max_total_usd=max_total_usd,
            context_mode=context_mode,
        )
        _atomic_write_json(output, report)

    questions = checkpoint["questions"]
    for question_id in question_ids:
        answer_records = report["answers"].setdefault(question_id, {})
        question = questions[question_id]
        context: list[object]
        if context_mode == "empty":
            context = []
        else:
            result_path = Path(question["phases"]["search"]["resultFile"])
            if not result_path.is_absolute():
                result_path = root / result_path
            search_data = json.loads(result_path.read_text(encoding="utf-8"))
            context = search_data.get("results", [])
        prompt = build_answer_prompt(
            question["question"],
            context,
            question.get("questionDate"),
        )
        for answer_repeat in range(answer_repeats):
            repeat_key = str(answer_repeat)
            if repeat_key in answer_records:
                continue
            body = build_kimi_request(
                prompt,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                reasoning_effort=ANSWER_EFFORT,
                max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
                judge=False,
            )
            _ensure_budget(report, body, ANSWER_MAX_COMPLETION_TOKENS)
            call = run_kimi_call(
                api_key,
                body,
                max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
                max_call_usd=max_call_usd,
                timeout_seconds=timeout_seconds,
            )
            _record_cost(report, call)
            answer_records[repeat_key] = {
                "question_type": question["questionType"],
                "prompt_sha256": _sha256_text(prompt),
                "answer": call["result"],
                "duration_ms": call["duration_ms"],
                "request_sha256": call["request_sha256"],
                "usage": call["usage"],
            }
            _atomic_write_json(output, report)
            print(
                f"answered {question_id} repeat {answer_repeat}: "
                f"${call['usage']['calculated_cost_usd']:.6f}, "
                f"total ${report['budget']['spent_usd']:.6f}",
                flush=True,
            )

    for question_id in question_ids:
        question = questions[question_id]
        question_judgments = report["judgments"].setdefault(question_id, {})
        for answer_repeat in range(answer_repeats):
            answer_key = str(answer_repeat)
            answer_judgments = question_judgments.setdefault(answer_key, {})
            answer = report["answers"][question_id][answer_key]["answer"]
            prompt = build_judge_prompt(
                question["question"],
                question["groundTruth"],
                answer,
                question["questionType"],
            )
            for judge_repeat in range(judge_repeats):
                judge_key = str(judge_repeat)
                if judge_key in answer_judgments:
                    continue
                body = build_kimi_request(
                    prompt,
                    system_prompt=JUDGE_SYSTEM_PROMPT,
                    reasoning_effort=JUDGE_EFFORT,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    judge=True,
                )
                _ensure_budget(report, body, JUDGE_MAX_COMPLETION_TOKENS)
                call = run_kimi_call(
                    api_key,
                    body,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    max_call_usd=max_call_usd,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    judgment = parse_judge_response(str(call["result"]))
                except (ProbeError, RuntimeError) as error:
                    raise QualificationError("Kimi judge returned an invalid judgment") from error
                _record_cost(report, call)
                answer_judgments[judge_key] = {
                    **judgment,
                    "prompt_sha256": _sha256_text(prompt),
                    "raw_response": call["result"],
                    "duration_ms": call["duration_ms"],
                    "request_sha256": call["request_sha256"],
                    "usage": call["usage"],
                }
                _atomic_write_json(output, report)
                print(
                    f"judged {question_id} answer {answer_repeat} repeat {judge_repeat}: "
                    f"{judgment['label']}, ${call['usage']['calculated_cost_usd']:.6f}, "
                    f"total ${report['budget']['spent_usd']:.6f}",
                    flush=True,
                )

    first_scores = [
        int(report["judgments"][question_id]["0"]["0"]["score"])
        for question_id in question_ids
    ]
    report["summary"] = {
        "question_count": len(question_ids),
        "answer_repeats_completed": answer_repeats,
        "judge_repeats_completed": judge_repeats,
        "first_pass_correct": sum(first_scores),
        "first_pass_accuracy": sum(first_scores) / len(first_scores),
        "same_base_model_answerer_and_judge": True,
        "human_audit_complete": False,
    }
    report["status"] = "completed"
    _atomic_write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memorybench-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--selection-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--answer-repeats", type=int, default=1)
    parser.add_argument("--judge-repeats", type=int, default=1)
    parser.add_argument("--max-call-usd", type=float, default=0.50)
    parser.add_argument("--max-total-usd", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--context-mode", choices=CONTEXT_MODES, default="retrieved")
    args = parser.parse_args()
    if not os.environ.get("MOONSHOT_API_KEY", "").strip():
        parser.error("MOONSHOT_API_KEY is required")
    if args.answer_repeats < 1 or args.judge_repeats < 1:
        parser.error("repeat counts must be positive")
    if args.max_call_usd <= 0 or args.max_total_usd <= 0:
        parser.error("budgets must be positive")
    if args.max_call_usd > args.max_total_usd:
        parser.error("per-call budget cannot exceed total budget")
    question_ids, selection_sha256 = load_selection(args.selection_file)
    report = run_qualification(
        root=args.memorybench_root.resolve(),
        run_id=args.run_id,
        output=args.output.resolve(),
        api_key=os.environ["MOONSHOT_API_KEY"],
        question_ids=question_ids,
        selection_sha256=selection_sha256,
        answer_repeats=args.answer_repeats,
        judge_repeats=args.judge_repeats,
        max_call_usd=args.max_call_usd,
        max_total_usd=args.max_total_usd,
        timeout_seconds=args.timeout_seconds,
        context_mode=args.context_mode,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"total cost: ${report['budget']['spent_usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
