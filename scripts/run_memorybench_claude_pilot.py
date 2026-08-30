#!/usr/bin/env python3
# ruff: noqa: E501
"""Run a budget-bounded Claude CLI evaluator pilot over frozen MemoryBench search results."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

MODEL = "claude-opus-5"
DEFAULT_QUESTION_IDS = (
    "d24813b1",
    "15745da0",
    "gpt4_2f8be40d",
    "gpt4_483dd43c",
    "c7dc5443",
    "89527b6b",
)
SYSTEM_PROMPT = (
    "You are running a frozen memory benchmark. Follow the supplied instructions exactly, "
    "use only the supplied context, do not use tools, and keep answers concise."
)

DEFAULT_JUDGE_PROMPT = """I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no.

Respond with ONLY a JSON object:
{"score": 1, "label": "correct", "explanation": "..."} if the response contains the correct answer
{"score": 0, "label": "incorrect", "explanation": "..."} if the response does not contain the correct answer"""

TEMPORAL_JUDGE_PROMPT = """I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct.

Respond with ONLY a JSON object:
{"score": 1, "label": "correct", "explanation": "..."} if the response contains the correct answer
{"score": 0, "label": "incorrect", "explanation": "..."} if the response does not contain the correct answer"""

KNOWLEDGE_UPDATE_JUDGE_PROMPT = """I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.

Respond with ONLY a JSON object:
{"score": 1, "label": "correct", "explanation": "..."} if the response contains the correct answer
{"score": 0, "label": "incorrect", "explanation": "..."} if the response does not contain the correct answer"""

PREFERENCE_JUDGE_PROMPT = """I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.

Respond with ONLY a JSON object:
{"score": 1, "label": "correct", "explanation": "..."} if the response satisfies the rubric
{"score": 0, "label": "incorrect", "explanation": "..."} if the response does not satisfy the rubric"""


class PilotError(RuntimeError):
    """Raised when the evaluator pilot violates its frozen contract."""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_answer_prompt(
    question: str,
    context: list[object],
    question_date: str | None = None,
) -> str:
    context_string = json.dumps(context, indent=2, ensure_ascii=False)
    return f"""You are a question-answering system. Based on the retrieved context below, answer the question.

Question: {question}
Question Date: {question_date or "Not specified"}

Retrieved Context (raw JSON from memory provider):
{context_string}

Instructions:
- The context above is the raw JSON response from a memory search API
- Extract relevant information from the JSON to answer the question
- Consider any temporal/date information present in the data
- If the context contains enough information, provide a clear, concise answer
- If the context does not contain enough information, respond with "I don't know"
- Base your answer ONLY on the provided context

Answer:"""


def _judge_system_prompt(question_type: str) -> str:
    normalized = question_type.lower()
    if "temporal" in normalized:
        return TEMPORAL_JUDGE_PROMPT
    if "update" in normalized or "changing" in normalized:
        return KNOWLEDGE_UPDATE_JUDGE_PROMPT
    if "preference" in normalized:
        return PREFERENCE_JUDGE_PROMPT
    return DEFAULT_JUDGE_PROMPT


def build_judge_prompt(
    question: str,
    ground_truth: str,
    hypothesis: str,
    question_type: str,
) -> str:
    ground_truth_label = (
        "Rubric" if "preference" in question_type.lower() else "Ground Truth Answer"
    )
    return f"""{_judge_system_prompt(question_type)}

Question: {question}
{ground_truth_label}: {ground_truth}
System's Hypothesis: {hypothesis}"""


def parse_judge_response(response: str) -> dict[str, object]:
    match = re.search(r"\{[\s\S]*\}", response)
    if match is None:
        raise PilotError("judge response did not contain a JSON object")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise PilotError("judge response contained invalid JSON") from exc
    if not isinstance(value, dict):
        raise PilotError("judge response must be an object")
    score = value.get("score")
    label = value.get("label")
    explanation = value.get("explanation")
    if score not in (0, 1):
        raise PilotError("judge score must be zero or one")
    if label not in ("correct", "incorrect"):
        raise PilotError("judge label must be correct or incorrect")
    if (score == 1) != (label == "correct"):
        raise PilotError("judge score and label disagree")
    if not isinstance(explanation, str) or not explanation.strip():
        raise PilotError("judge explanation must be a non-empty string")
    return {"score": score, "label": label, "explanation": explanation.strip()}


def _atomic_write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _claude_version() -> str:
    process = subprocess.run(
        ["claude", "--version"],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return process.stdout.strip()


def run_claude(
    prompt: str,
    *,
    max_call_usd: float,
    timeout_seconds: int,
) -> dict[str, object]:
    command = [
        "claude",
        "--safe-mode",
        "--no-chrome",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--prompt-suggestions",
        "false",
        "--tools",
        "",
        "--system-prompt",
        SYSTEM_PROMPT,
        "--model",
        MODEL,
        "--effort",
        "low",
        "--output-format",
        "json",
        "--max-budget-usd",
        f"{max_call_usd:.6f}",
        "--print",
    ]
    started = time.monotonic()
    process = subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    duration_ms = round((time.monotonic() - started) * 1000)
    if process.returncode != 0:
        raise PilotError(
            f"Claude CLI exited with {process.returncode}: {process.stderr.strip()[:500]}"
        )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise PilotError("Claude CLI returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("is_error") is not False:
        raise PilotError("Claude CLI reported an evaluator error")
    result = payload.get("result")
    cost = payload.get("total_cost_usd")
    model_usage = payload.get("modelUsage")
    if not isinstance(result, str) or not result.strip():
        raise PilotError("Claude CLI returned an empty result")
    if not isinstance(cost, (int, float)) or cost < 0:
        raise PilotError("Claude CLI returned an invalid cost")
    if not isinstance(model_usage, dict) or MODEL not in model_usage:
        raise PilotError(f"Claude CLI did not report exact model {MODEL}")
    if cost > max_call_usd + 1e-9:
        raise PilotError(f"Claude CLI exceeded the per-call budget: ${cost:.6f}")
    return {
        "result": result.strip(),
        "cost_usd": cost,
        "duration_ms": duration_ms,
        "model_usage": model_usage,
    }


def load_selection(path: Path | None) -> tuple[tuple[str, ...], str | None]:
    if path is None:
        return DEFAULT_QUESTION_IDS, None
    value = json.loads(path.read_text(encoding="utf-8"))
    question_ids = value.get("question_ids") if isinstance(value, dict) else None
    if (
        not isinstance(question_ids, list)
        or not question_ids
        or not all(isinstance(item, str) and item for item in question_ids)
    ):
        raise PilotError("selection question_ids must be a non-empty string array")
    if len(question_ids) != len(set(question_ids)):
        raise PilotError("selection question_ids must be unique")
    return tuple(question_ids), hashlib.sha256(path.read_bytes()).hexdigest()


def _load_source(
    root: Path,
    run_id: str,
    question_ids: tuple[str, ...],
) -> tuple[Path, dict[str, Any]]:
    checkpoint_path = root / "data" / "runs" / run_id / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("targetQuestionIds") != list(question_ids):
        raise PilotError("checkpoint question selection does not match the frozen selection")
    if checkpoint.get("status") != "completed":
        raise PilotError("source MemoryBench run is not complete")
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
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "running",
        "model": MODEL,
        "claude_cli_version": _claude_version(),
        "source_run_id": run_id,
        "source_checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
        "memorybench_root": str(root),
        "question_ids": list(question_ids),
        "selection_sha256": selection_sha256,
        "source_provider": checkpoint.get("provider"),
        "source_benchmark": checkpoint.get("benchmark"),
        "system_prompt_sha256": _sha256_text(SYSTEM_PROMPT),
        "budget": {
            "max_call_usd": max_call_usd,
            "max_total_usd": max_total_usd,
            "spent_usd": 0.0,
        },
        "answers": {},
        "judgments": {},
    }


def _remaining_budget(report: dict[str, Any]) -> float:
    budget = report["budget"]
    return float(budget["max_total_usd"]) - float(budget["spent_usd"])


def _record_call_cost(report: dict[str, Any], cost: float) -> None:
    budget = report["budget"]
    budget["spent_usd"] = round(float(budget["spent_usd"]) + cost, 9)
    if float(budget["spent_usd"]) > float(budget["max_total_usd"]) + 1e-9:
        raise PilotError("pilot exceeded the total budget")


def load_question_dates(dataset_path: Path | None) -> dict[str, str]:
    """Map question_id to the dataset's question_date.

    MemoryBench carries `questionDate` in its checkpoint type, but the retrieval-only
    phase list this project runs (ingest/indexing/search) leaves it unset, so the
    answering prompt renders "Question Date: Not specified". Temporal questions of the
    form "how many days ago ..." are unanswerable without a reference date, and the
    answerer correctly declines rather than guessing. Reading the date from the pinned
    dataset restores it without altering retrieval or any stored data.
    """

    if dataset_path is None:
        return {}
    with dataset_path.open(encoding="utf-8") as stream:
        dataset = json.load(stream)
    return {
        str(item["question_id"]): str(item["question_date"])
        for item in dataset
        if item.get("question_date")
    }


def run_pilot(
    *,
    root: Path,
    run_id: str,
    output: Path,
    max_call_usd: float,
    max_total_usd: float,
    timeout_seconds: int,
    question_ids: tuple[str, ...] = DEFAULT_QUESTION_IDS,
    selection_sha256: str | None = None,
    gate_threshold_correct: int | None = 5,
    question_dates: dict[str, str] | None = None,
) -> dict[str, object]:
    checkpoint_path, checkpoint = _load_source(root, run_id, question_ids)
    if output.exists():
        report: dict[str, Any] = json.loads(output.read_text(encoding="utf-8"))
        if report.get("model") != MODEL:
            raise PilotError("existing pilot report uses a different model")
        if report.get("source_checkpoint_sha256") != hashlib.sha256(
            checkpoint_path.read_bytes()
        ).hexdigest():
            raise PilotError("existing pilot report uses a different source checkpoint")
        if report.get("question_ids") != list(question_ids):
            raise PilotError("existing pilot report uses a different question selection")
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
        )
        _atomic_write_json(output, report)

    questions = checkpoint["questions"]
    answers: dict[str, Any] = report["answers"]
    judgments: dict[str, Any] = report["judgments"]

    for question_id in question_ids:
        if question_id in answers:
            continue
        question = questions[question_id]
        result_path_value = question["phases"]["search"]["resultFile"]
        result_path = Path(result_path_value)
        if not result_path.is_absolute():
            result_path = root / result_path
        search_data = json.loads(result_path.read_text(encoding="utf-8"))
        resolved_date = (question_dates or {}).get(question_id) or question.get(
            "questionDate"
        )
        prompt = build_answer_prompt(
            question["question"],
            search_data.get("results", []),
            resolved_date,
        )
        remaining = _remaining_budget(report)
        allowed = min(max_call_usd, remaining)
        if allowed <= 0:
            raise PilotError("no total budget remains for answer generation")
        call = run_claude(prompt, max_call_usd=allowed, timeout_seconds=timeout_seconds)
        _record_call_cost(report, float(call["cost_usd"]))
        answers[question_id] = {
            "question_type": question["questionType"],
            "question_date": resolved_date,
            "question_date_source": (
                "dataset"
                if (question_dates or {}).get(question_id)
                else ("checkpoint" if question.get("questionDate") else "unresolved")
            ),
            "prompt_sha256": _sha256_text(prompt),
            "answer": call["result"],
            "cost_usd": call["cost_usd"],
            "duration_ms": call["duration_ms"],
            "model_usage": call["model_usage"],
        }
        _atomic_write_json(output, report)
        print(
            f"answered {question_id}: ${call['cost_usd']:.6f}, "
            f"total ${report['budget']['spent_usd']:.6f}",
            flush=True,
        )

    for question_id in question_ids:
        if question_id in judgments:
            continue
        question = questions[question_id]
        prompt = build_judge_prompt(
            question["question"],
            question["groundTruth"],
            answers[question_id]["answer"],
            question["questionType"],
        )
        remaining = _remaining_budget(report)
        allowed = min(max_call_usd, remaining)
        if allowed <= 0:
            raise PilotError("no total budget remains for judging")
        call = run_claude(prompt, max_call_usd=allowed, timeout_seconds=timeout_seconds)
        judgment = parse_judge_response(str(call["result"]))
        _record_call_cost(report, float(call["cost_usd"]))
        judgments[question_id] = {
            **judgment,
            "prompt_sha256": _sha256_text(prompt),
            "raw_response": call["result"],
            "cost_usd": call["cost_usd"],
            "duration_ms": call["duration_ms"],
            "model_usage": call["model_usage"],
        }
        _atomic_write_json(output, report)
        print(
            f"judged {question_id}: {judgment['label']}, "
            f"${call['cost_usd']:.6f}, total ${report['budget']['spent_usd']:.6f}",
            flush=True,
        )

    correct = sum(int(value["score"]) for value in judgments.values())
    gate_passed = (
        None if gate_threshold_correct is None else correct >= gate_threshold_correct
    )
    report["summary"] = {
        "total": len(question_ids),
        "correct": correct,
        "accuracy": correct / len(question_ids),
        "gate_threshold_correct": gate_threshold_correct,
        "evaluator_gate_passed": gate_passed,
        "same_model_answerer_and_judge": True,
    }
    report["status"] = "completed"
    _atomic_write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--memorybench-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-call-usd", type=float, default=1.0)
    parser.add_argument("--max-total-usd", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--selection-file", type=Path)
    parser.add_argument(
        "--dataset",
        type=Path,
        help=(
            "pinned LongMemEval dataset; supplies question_date, which the "
            "retrieval-only checkpoint does not carry"
        ),
    )
    parser.add_argument("--gate-threshold-correct", type=int)
    args = parser.parse_args()
    if args.max_call_usd <= 0 or args.max_total_usd <= 0:
        parser.error("budgets must be positive")
    if args.max_call_usd > args.max_total_usd:
        parser.error("per-call budget cannot exceed total budget")
    question_ids, selection_sha256 = load_selection(args.selection_file)
    gate_threshold_correct = args.gate_threshold_correct
    if gate_threshold_correct is None and args.selection_file is None:
        gate_threshold_correct = 5
    if gate_threshold_correct is not None and not (
        0 <= gate_threshold_correct <= len(question_ids)
    ):
        parser.error("gate threshold must be between zero and the selection size")
    question_dates = load_question_dates(args.dataset)
    report = run_pilot(
        root=args.memorybench_root.resolve(),
        run_id=args.run_id,
        output=args.output.resolve(),
        max_call_usd=args.max_call_usd,
        max_total_usd=args.max_total_usd,
        timeout_seconds=args.timeout_seconds,
        question_ids=question_ids,
        selection_sha256=selection_sha256,
        gate_threshold_correct=gate_threshold_correct,
        question_dates=question_dates,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(f"total cost: ${report['budget']['spent_usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
