#!/usr/bin/env python3
"""Compare blind human, Kimi-majority, and frozen Claude judge labels."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class JudgeAuditAnalysisError(RuntimeError):
    """Raised when judge-audit evidence is incomplete or incompatible."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _majority(values: list[int]) -> int:
    if not values or len(values) % 2 == 0:
        raise JudgeAuditAnalysisError("votes must contain a positive odd count")
    return int(sum(values) > len(values) // 2)


def build_evidence(
    packet: dict[str, Any],
    key: dict[str, Any],
    kimi: dict[str, Any],
    gate_contract: dict[str, Any],
) -> dict[str, Any]:
    if packet.get("status") != "human-scored":
        raise JudgeAuditAnalysisError("human audit packet is not complete")
    if kimi.get("status") != "completed":
        raise JudgeAuditAnalysisError("Kimi judge audit is not complete")
    packet_items = {item["audit_id"]: item for item in packet["items"]}
    key_items = {item["audit_id"]: item for item in key["items"]}
    audit_ids = list(kimi.get("audit_ids", []))
    if set(audit_ids) != set(packet_items) or set(audit_ids) != set(key_items):
        raise JudgeAuditAnalysisError("audit IDs differ across packet, key, and Kimi run")
    if gate_contract.get("status") != "frozen-before-kimi-audit-judgments":
        raise JudgeAuditAnalysisError("gate contract was not frozen before judgments")

    rows: list[dict[str, int | bool | str]] = []
    unanimous = 0
    for audit_id in audit_ids:
        human = int(packet_items[audit_id]["human_score"])
        claude = int(key_items[audit_id]["frozen_claude_judge_score"])
        judgments = kimi["judgments"].get(audit_id, {})
        votes = [
            int(judgments[key]["score"]) for key in sorted(judgments, key=int)
        ]
        if len(votes) != int(kimi["judge_repeats"]):
            raise JudgeAuditAnalysisError(f"incomplete Kimi votes for {audit_id}")
        kimi_score = _majority(votes)
        is_unanimous = len(set(votes)) == 1
        unanimous += int(is_unanimous)
        rows.append(
            {
                "audit_id": audit_id,
                "human": human,
                "kimi": kimi_score,
                "claude": claude,
                "kimi_unanimous": is_unanimous,
            }
        )

    human_positive = [row for row in rows if row["human"] == 1]
    human_negative = [row for row in rows if row["human"] == 0]
    overall_agreement = sum(row["kimi"] == row["human"] for row in rows)
    positive_agreement = sum(row["kimi"] == 1 for row in human_positive)
    negative_agreement = sum(row["kimi"] == 0 for row in human_negative)
    kimi_positive = sum(int(row["kimi"]) for row in rows)
    human_positive_count = len(human_positive)
    gates = gate_contract["gates"]
    gate_results = {
        "overall_agreement": overall_agreement
        >= int(gates["minimum_overall_agreement"]),
        "human_positive_agreement": positive_agreement
        >= int(gates["minimum_human_positive_agreement"]),
        "human_negative_agreement": negative_agreement
        >= int(gates["minimum_human_negative_agreement"]),
        "positive_count_drift": abs(kimi_positive - human_positive_count)
        <= int(gates["maximum_absolute_positive_count_drift"]),
        "vote_unanimity": unanimous
        >= int(gates["minimum_unanimous_three_vote_items"]),
    }
    claude_human_agreement = sum(row["claude"] == row["human"] for row in rows)
    kimi_claude_agreement = sum(row["kimi"] == row["claude"] for row in rows)
    return {
        "schema_version": 1,
        "status": "passed" if all(gate_results.values()) else "failed",
        "model": kimi.get("model"),
        "audit_scope": gate_contract.get("audit_scope"),
        "candidate_answer_model": gate_contract.get("sample", {}).get(
            "candidate_answer_model"
        ),
        "not_evidence_for": gate_contract.get("not_evidence_for"),
        "questions": len(rows),
        "human_labels": {
            "positive": human_positive_count,
            "negative": len(human_negative),
        },
        "kimi_vs_human": {
            "overall_agreement": overall_agreement,
            "overall_rate": overall_agreement / len(rows),
            "human_positive_agreement": positive_agreement,
            "human_positive_total": len(human_positive),
            "human_negative_agreement": negative_agreement,
            "human_negative_total": len(human_negative),
            "kimi_positive_count": kimi_positive,
            "absolute_positive_count_drift": abs(
                kimi_positive - human_positive_count
            ),
            "unanimous_three_vote_items": unanimous,
        },
        "comparative_diagnostics": {
            "claude_vs_human_agreement": claude_human_agreement,
            "claude_vs_human_rate": claude_human_agreement / len(rows),
            "kimi_vs_claude_agreement": kimi_claude_agreement,
            "kimi_vs_claude_rate": kimi_claude_agreement / len(rows),
        },
        "gate_thresholds": gates,
        "gate_results": gate_results,
        "all_gates_passed": all(gate_results.values()),
        "cost_usd": float(kimi["budget"]["spent_usd"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--kimi", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = {
        "packet": args.packet,
        "key": args.key,
        "kimi": args.kimi,
        "gates": args.gates,
    }
    loaded = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in inputs.items()
    }
    evidence = build_evidence(
        loaded["packet"], loaded["key"], loaded["kimi"], loaded["gates"]
    )
    evidence["source_sha256"] = {
        name: _sha256(path) for name, path in inputs.items()
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["all_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
