#!/usr/bin/env python3
"""Single-arm kimi-k3 baseline answer run over a frozen LongMemEval selection.

Exists to re-measure the released store's answer quality after the question-date harness
defect was fixed (`docs/architecture/benchmarks/2026-08-03-question-date-harness-defect.md`).
Every paid answer run so far rendered "Question Date: Not specified", so temporal questions
of the form "how many days ago ..." were unanswerable and the answerer correctly declined.

The paired development runner is a two-arm instrument that requires a candidate replay and
is left untouched: it produced recorded evidence and must stay reproducible. This runner
reuses its exact frozen answerer and judge protocol by importing the same prompts, model,
system prompts, reasoning efforts, token limits, and three-vote majority rule, and changes
only two things: one arm instead of two, and a resolved question date.

That makes the result directly comparable to the baseline arm of
`kimi-k3-session-diverse-paired-development60-v1`, which covered the identical 60 questions
with the identical evaluator and no question date. One variable differs.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
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
    from scripts.run_memorybench_kimi_paired_development import load_api_key
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
else:  # pragma: no cover - direct execution path
    from run_memorybench_claude_pilot import (
        build_answer_prompt,
        build_judge_prompt,
        load_question_dates,
        parse_judge_response,
    )
    from run_memorybench_kimi_paired_development import load_api_key
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

EXPERIMENT_ID = "kimi-k3-question-date-baseline60-v1"
JUDGE_REPEATS = 3
ANSWER_MAX_CALL_USD = 0.25
JUDGE_MAX_CALL_USD = 0.05
DATASET_SHA256 = "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442"


class BaselineRunError(RuntimeError):
    """Raised when the run cannot proceed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _merge_checkpoints(paths: list[Path]) -> dict[str, Any]:
    questions: dict[str, Any] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "completed":
            raise BaselineRunError(f"checkpoint {path} is not completed")
        for question_id, entry in data.get("questions", {}).items():
            if question_id in questions:
                raise BaselineRunError(f"duplicate question across checkpoints: {question_id}")
            questions[question_id] = entry
    return questions


def _search_results(entry: dict[str, Any], checkpoint_path: Path) -> list[Any]:
    """Read a question's retrieved results, inline or from its sidecar file.

    MemoryBench stores `resultFile` relative to its own root, not to the checkpoint, and
    the checkpoint always sits at <root>/data/runs/<run-id>/checkpoint.json.
    """

    search = entry["phases"]["search"]
    if "results" in search:
        return list(search["results"])
    result_file = search.get("resultFile")
    if not result_file:
        raise BaselineRunError("question has neither inline results nor a resultFile")
    path = Path(result_file)
    if not path.is_absolute():
        path = checkpoint_path.parents[3] / result_file
    if not path.exists():
        raise BaselineRunError(f"retrieved-results file not found: {path}")
    return list(json.loads(path.read_text(encoding="utf-8")).get("results", []))


def _remaining(report: dict[str, Any]) -> float:
    budget = report["budget"]
    return float(budget["max_total_usd"]) - float(budget["spent_usd"])


def _call_cost(call: dict[str, Any]) -> float:
    """Read the provider-reported cost. run_kimi_call nests it under usage."""
    try:
        return float(call["usage"]["calculated_cost_usd"])
    except (KeyError, TypeError, ValueError) as error:
        raise BaselineRunError("kimi call returned no usable cost record") from error


def _record_cost(report: dict[str, Any], call: dict[str, Any]) -> None:
    report["budget"]["spent_usd"] = round(
        float(report["budget"]["spent_usd"]) + _call_cost(call), 8
    )


def _guarded_call(
    report: dict[str, Any],
    api_key: str,
    body: bytes,
    *,
    max_completion_tokens: int,
    max_call_usd: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Refuse a call whose worst case could exceed the remaining ledger."""
    worst = worst_case_cost_usd(body, max_completion_tokens)
    if worst > _remaining(report):
        raise BaselineRunError(
            f"worst-case ${worst:.6f} exceeds remaining ${_remaining(report):.6f}; stopping"
        )
    call = run_kimi_call(
        api_key,
        body,
        max_completion_tokens=max_completion_tokens,
        max_call_usd=max_call_usd,
        timeout_seconds=timeout_seconds,
    )
    _record_cost(report, call)
    return call


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    per_category: collections.Counter[str] = collections.Counter()
    totals: collections.Counter[str] = collections.Counter()
    correct = 0
    unresolved_dates = 0
    for entry in report["questions"].values():
        category = entry["question_type"]
        totals[category] += 1
        if entry.get("label") == "correct":
            correct += 1
            per_category[category] += 1
        if entry.get("question_date_source") == "unresolved":
            unresolved_dates += 1
    return {
        "answered": len(report["questions"]),
        "correct": correct,
        "categories": {
            category: {"correct": per_category[category], "total": totals[category]}
            for category in sorted(totals)
        },
        "questions_without_resolved_date": unresolved_dates,
        "spent_usd": report["budget"]["spent_usd"],
    }


def run_baseline(
    *,
    dataset: Path,
    selection: Path,
    checkpoints: list[Path],
    output: Path,
    api_key: str,
    max_total_usd: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    dataset_sha = _sha256(dataset)
    if dataset_sha != DATASET_SHA256:
        raise BaselineRunError(f"dataset digest {dataset_sha} does not match the frozen value")

    selection_data = json.loads(selection.read_text(encoding="utf-8"))
    question_ids = [str(q) for q in selection_data["question_ids"]]
    questions = _merge_checkpoints(checkpoints)
    missing = [q for q in question_ids if q not in questions]
    if missing:
        raise BaselineRunError(f"checkpoints are missing questions: {missing[:5]}")
    question_dates = load_question_dates(dataset)

    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        if report.get("model") != MODEL or report.get("experiment_id") != EXPERIMENT_ID:
            raise BaselineRunError("existing report belongs to a different experiment or model")
    else:
        report = {
            "schema_version": 1,
            "experiment_id": EXPERIMENT_ID,
            "model": MODEL,
            "status": "in-progress",
            "arm": "baseline",
            "judge_repeats": JUDGE_REPEATS,
            "question_ids": question_ids,
            "questions": {},
            "budget": {"max_total_usd": max_total_usd, "spent_usd": 0.0},
            "protocol": {
                "answer_system_prompt_sha256": _sha256_text(ANSWER_SYSTEM_PROMPT),
                "judge_system_prompt_sha256": _sha256_text(JUDGE_SYSTEM_PROMPT),
                "answer_effort": ANSWER_EFFORT,
                "judge_effort": JUDGE_EFFORT,
                "question_date_supplied": True,
                "comparable_to": "kimi-k3-session-diverse-paired-development60-v1 baseline arm",
                "single_variable_changed": "question_date resolved from the pinned dataset",
            },
            "input_identity": {
                "dataset_sha256": dataset_sha,
                "selection_sha256": _sha256(selection),
                "checkpoint_sha256": [_sha256(p) for p in checkpoints],
            },
            "started_at": datetime.now(UTC).isoformat(),
        }
        _atomic_write_json(output, report)

    pending = [q for q in question_ids if q not in report["questions"]]
    print(f"{len(pending)} of {len(question_ids)} questions pending", flush=True)

    for position, question_id in enumerate(pending, start=1):
        entry = questions[question_id]
        results = _search_results(entry, checkpoints[0])

        resolved_date = question_dates.get(question_id) or entry.get("questionDate")
        prompt = build_answer_prompt(entry["question"], results, resolved_date)
        answer_call = _guarded_call(
            report,
            api_key,
            build_kimi_request(
                prompt,
                system_prompt=ANSWER_SYSTEM_PROMPT,
                reasoning_effort=ANSWER_EFFORT,
                max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
                judge=False,
            ),
            max_completion_tokens=ANSWER_MAX_COMPLETION_TOKENS,
            max_call_usd=ANSWER_MAX_CALL_USD,
            timeout_seconds=timeout_seconds,
        )
        answer_text = answer_call["result"]

        judge_prompt = build_judge_prompt(
            entry["question"], entry["groundTruth"], answer_text, entry["questionType"]
        )
        votes: list[str] = []
        for _ in range(JUDGE_REPEATS):
            judge_call = _guarded_call(
                report,
                api_key,
                build_kimi_request(
                    judge_prompt,
                    system_prompt=JUDGE_SYSTEM_PROMPT,
                    reasoning_effort=JUDGE_EFFORT,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    judge=True,
                ),
                max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                max_call_usd=JUDGE_MAX_CALL_USD,
                timeout_seconds=timeout_seconds,
            )
            votes.append(str(parse_judge_response(judge_call["result"])["label"]))
        label = collections.Counter(votes).most_common(1)[0][0]

        report["questions"][question_id] = {
            "question_type": entry["questionType"],
            "question_date": resolved_date,
            "question_date_source": (
                "dataset"
                if question_dates.get(question_id)
                else ("checkpoint" if entry.get("questionDate") else "unresolved")
            ),
            "answer": answer_text,
            "prompt_sha256": _sha256_text(prompt),
            "judge_votes": votes,
            "judge_unanimous": len(set(votes)) == 1,
            "label": label,
        }
        _atomic_write_json(output, report)
        print(
            f"[{position}/{len(pending)}] {question_id} {label} "
            f"votes={votes} spent=${report['budget']['spent_usd']:.4f}",
            flush=True,
        )

    report["status"] = (
        "completed" if all(q in report["questions"] for q in question_ids) else "in-progress"
    )
    report["summary"] = _summary(report)
    report["finished_at"] = datetime.now(UTC).isoformat()
    _atomic_write_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keychain-service")
    parser.add_argument("--max-total-usd", type=float, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    api_key = load_api_key(
        keychain_service=args.keychain_service, environment=dict(os.environ)
    )
    report = run_baseline(
        dataset=args.dataset,
        selection=args.selection,
        checkpoints=[p.resolve() for p in args.checkpoint],
        output=args.output.resolve(),
        api_key=api_key,
        max_total_usd=args.max_total_usd,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
