#!/usr/bin/env python3
"""Run a resumable Kimi judge audit over a blind, human-scored answer packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

if __package__:
    from scripts.run_memorybench_claude_pilot import (
        build_judge_prompt,
        parse_judge_response,
    )
    from scripts.run_memorybench_kimi_qualification import (
        JUDGE_EFFORT,
        JUDGE_MAX_COMPLETION_TOKENS,
        JUDGE_SYSTEM_PROMPT,
        MODEL,
        QualificationError,
        build_kimi_request,
        run_kimi_call,
        worst_case_cost_usd,
    )
else:
    from run_memorybench_claude_pilot import build_judge_prompt, parse_judge_response
    from run_memorybench_kimi_qualification import (
        JUDGE_EFFORT,
        JUDGE_MAX_COMPLETION_TOKENS,
        JUDGE_SYSTEM_PROMPT,
        MODEL,
        QualificationError,
        build_kimi_request,
        run_kimi_call,
        worst_case_cost_usd,
    )


class JudgeAuditError(RuntimeError):
    """Raised when the blind judge audit violates its frozen contract."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def validate_packet(packet: dict[str, Any]) -> list[dict[str, Any]]:
    items = packet.get("items")
    if packet.get("status") != "human-scored" or not isinstance(items, list):
        raise JudgeAuditError("packet must contain completed blind human scores")
    if len(items) != 30:
        raise JudgeAuditError("audit packet must contain exactly 30 items")
    audit_ids: set[str] = set()
    for item in items:
        audit_id = item.get("audit_id")
        if not isinstance(audit_id, str) or audit_id in audit_ids:
            raise JudgeAuditError("audit IDs must be unique strings")
        audit_ids.add(audit_id)
        if item.get("human_score") not in (0, 1):
            raise JudgeAuditError(f"invalid human score for {audit_id}")
        for field in ("question", "candidate_answer", "question_type"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise JudgeAuditError(f"invalid {field} for {audit_id}")
        reference = item.get("reference_answer_or_rubric")
        if isinstance(reference, bool) or not isinstance(reference, (str, int, float)):
            raise JudgeAuditError(f"invalid reference_answer_or_rubric for {audit_id}")
        if isinstance(reference, str) and not reference.strip():
            raise JudgeAuditError(f"invalid reference_answer_or_rubric for {audit_id}")
    return items


def build_audit_judge_prompt(item: dict[str, Any]) -> str:
    return build_judge_prompt(
        str(item["question"]),
        str(item["reference_answer_or_rubric"]),
        str(item["candidate_answer"]),
        str(item["question_type"]),
    )


def run_audit(
    *,
    packet_path: Path,
    output: Path,
    api_key: str,
    repeats: int,
    max_call_usd: float,
    max_total_usd: float,
    timeout_seconds: int,
    min_interval_seconds: float,
) -> dict[str, Any]:
    packet_bytes = packet_path.read_bytes()
    packet = json.loads(packet_bytes)
    items = validate_packet(packet)
    packet_sha256 = _sha256_bytes(packet_bytes)
    if repeats < 1 or repeats % 2 == 0:
        raise JudgeAuditError("judge repeats must be a positive odd number")

    if output.exists():
        report = json.loads(output.read_text(encoding="utf-8"))
        if report.get("packet_sha256") != packet_sha256:
            raise JudgeAuditError("existing audit output uses a different packet")
        if report.get("model") != MODEL or report.get("judge_repeats") != repeats:
            raise JudgeAuditError("existing audit output uses a different protocol")
        if report.get("budget", {}).get("max_total_usd") != max_total_usd:
            raise JudgeAuditError("existing audit output uses a different total budget")
        report["status"] = "running"
    else:
        report = {
            "schema_version": 1,
            "status": "running",
            "model": MODEL,
            "packet_sha256": packet_sha256,
            "audit_ids": [item["audit_id"] for item in items],
            "human_scores_excluded_from_model_prompts": True,
            "judge_repeats": repeats,
            "judge_protocol": {
                "reasoning_effort": JUDGE_EFFORT,
                "max_completion_tokens": JUDGE_MAX_COMPLETION_TOKENS,
                "strict_json_schema": True,
            },
            "budget": {
                "max_call_usd": max_call_usd,
                "max_total_usd": max_total_usd,
                "spent_usd": 0.0,
            },
            "judgments": {},
        }
        _atomic_write(output, report)

    for item in items:
        audit_id = item["audit_id"]
        item_judgments = report["judgments"].setdefault(audit_id, {})
        prompt = build_audit_judge_prompt(item)
        if str(item["human_score"]) in prompt and "human_score" in prompt:
            raise JudgeAuditError("human score leaked into model prompt")
        body = build_kimi_request(
            prompt,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            reasoning_effort=JUDGE_EFFORT,
            max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
            judge=True,
        )
        for repeat in range(repeats):
            repeat_key = str(repeat)
            if repeat_key in item_judgments:
                continue
            remaining = max_total_usd - float(report["budget"]["spent_usd"])
            required = worst_case_cost_usd(body, JUDGE_MAX_COMPLETION_TOKENS)
            if remaining + 1e-9 < required:
                raise JudgeAuditError("remaining budget cannot cover the next worst-case call")
            try:
                call = run_kimi_call(
                    api_key,
                    body,
                    max_completion_tokens=JUDGE_MAX_COMPLETION_TOKENS,
                    max_call_usd=max_call_usd,
                    timeout_seconds=timeout_seconds,
                )
                judgment = parse_judge_response(str(call["result"]))
            except QualificationError as error:
                raise JudgeAuditError(str(error)) from error
            cost = float(call["usage"]["calculated_cost_usd"])
            report["budget"]["spent_usd"] = round(
                float(report["budget"]["spent_usd"]) + cost, 9
            )
            item_judgments[repeat_key] = {
                **judgment,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "request_sha256": call["request_sha256"],
                "duration_ms": call["duration_ms"],
                "usage": call["usage"],
            }
            _atomic_write(output, report)
            print(
                f"judged {audit_id} repeat {repeat}: {judgment['label']}, "
                f"total ${report['budget']['spent_usd']:.6f}",
                flush=True,
            )
            if min_interval_seconds > 0:
                time.sleep(min_interval_seconds)

    report["status"] = "completed"
    _atomic_write(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-call-usd", type=float, default=0.50)
    parser.add_argument("--max-total-usd", type=float, default=3.0)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--min-interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    api_key = os.environ.get("MOONSHOT_API_KEY", "").strip()
    if not api_key:
        parser.error("MOONSHOT_API_KEY is required")
    report = run_audit(
        packet_path=args.packet.resolve(),
        output=args.output.resolve(),
        api_key=api_key,
        repeats=args.repeats,
        max_call_usd=args.max_call_usd,
        max_total_usd=args.max_total_usd,
        timeout_seconds=args.timeout_seconds,
        min_interval_seconds=args.min_interval_seconds,
    )
    print(f"completed {len(report['audit_ids'])} audit items")
    print(f"total cost: ${report['budget']['spent_usd']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
