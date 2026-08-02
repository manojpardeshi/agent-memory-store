#!/usr/bin/env python3
"""Apply blind human labels to the frozen paired Kimi development evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from scripts.analyze_kimi_paired_answer_run import ARMS, evaluate_gates
    from scripts.prepare_kimi_paired_human_audit import build_packet
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root.
    from analyze_kimi_paired_answer_run import ARMS, evaluate_gates
    from prepare_kimi_paired_human_audit import build_packet


class PairedHumanAuditError(RuntimeError):
    """Raised when a paired human audit is incomplete or inconsistent."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _score(item: dict[str, Any], side: str) -> int:
    value = item.get(f"{side}_human_score")
    if type(value) is not int or value not in (0, 1):
        raise PairedHumanAuditError(
            f"{item.get('audit_id', 'unknown')} {side}_human_score must be 0 or 1"
        )
    return value


def _unscored_packet(packet: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(packet)
    for item in normalized.get("items", []):
        for side in ("left", "right"):
            item[f"{side}_human_score"] = None
            item[f"{side}_human_notes"] = ""
    return normalized


def adjudicate(
    packet: dict[str, Any],
    key: dict[str, Any],
    machine: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Validate human scores, substitute them, and rerun every frozen gate."""

    if packet.get("status") != "awaiting-human-scores":
        raise PairedHumanAuditError("audit packet is not awaiting human scores")
    if packet.get("blinded_arms") is not True:
        raise PairedHumanAuditError("audit packet was not arm-blinded")
    if packet.get("candidate_answer_model") != machine.get("model"):
        raise PairedHumanAuditError("audit model differs from machine evidence")
    packet_items = packet.get("items")
    key_items = key.get("items")
    if not isinstance(packet_items, list) or not isinstance(key_items, list):
        raise PairedHumanAuditError("audit packet or key lacks items")
    if [item.get("audit_id") for item in packet_items] != [
        item.get("audit_id") for item in key_items
    ]:
        raise PairedHumanAuditError("audit packet order differs from its key")
    if len(packet_items) != int(packet.get("unique_questions", -1)) + int(
        packet.get("reliability_duplicate_items", -1)
    ):
        raise PairedHumanAuditError("audit packet item counts are inconsistent")

    packet_by_id = {item["audit_id"]: item for item in packet_items}
    originals = [item for item in key_items if item.get("duplicate_of_source_id") is None]
    unique_ids = [item["question_id"] for item in originals]
    if set(unique_ids) != set(machine.get("paired", {}).get("audit_question_ids", [])):
        raise PairedHumanAuditError("audit questions differ from machine-selected questions")
    if len(unique_ids) < int(contract["human_audit"]["minimum_unique_audit_questions"]):
        raise PairedHumanAuditError("audit has too few unique questions")

    human_scores: dict[str, dict[str, int]] = {}
    judge_comparisons: list[bool] = []
    category_by_question: dict[str, str] = {}
    for key_item in originals:
        audit_item = packet_by_id[key_item["audit_id"]]
        question_id = key_item["question_id"]
        category_by_question[question_id] = str(audit_item["question_type"])
        by_arm = {
            key_item["left_arm"]: _score(audit_item, "left"),
            key_item["right_arm"]: _score(audit_item, "right"),
        }
        if set(by_arm) != set(ARMS):
            raise PairedHumanAuditError("audit key does not map both arms")
        human_scores[question_id] = by_arm
        model_majority = key_item["selection_reason"]["model_judge_majority"]
        judge_comparisons.extend(by_arm[arm] == int(model_majority[arm]) for arm in ARMS)

    reliability_comparisons: list[bool] = []
    for duplicate in key_items:
        original_source = duplicate.get("duplicate_of_source_id")
        if original_source is None:
            continue
        original = next(
            (item for item in originals if item["source_id"] == original_source),
            None,
        )
        if original is None:
            raise PairedHumanAuditError("reliability duplicate lacks its original")
        duplicate_item = packet_by_id[duplicate["audit_id"]]
        original_item = packet_by_id[original["audit_id"]]
        for arm in ARMS:
            duplicate_side = "left" if duplicate["left_arm"] == arm else "right"
            original_side = "left" if original["left_arm"] == arm else "right"
            reliability_comparisons.append(
                _score(duplicate_item, duplicate_side)
                == _score(original_item, original_side)
            )
    expected_reliability = int(packet["reliability_duplicate_items"]) * 2
    if len(reliability_comparisons) != expected_reliability:
        raise PairedHumanAuditError("reliability comparison count is inconsistent")

    arms = copy.deepcopy(machine["arms"])
    for question_id, by_arm in human_scores.items():
        key_item = next(item for item in originals if item["question_id"] == question_id)
        model_majority = key_item["selection_reason"]["model_judge_majority"]
        category = category_by_question[question_id]
        for arm in ARMS:
            delta = by_arm[arm] - int(model_majority[arm])
            arms[arm]["majority_correct"] += delta
            arms[arm]["category_accuracy"][category]["correct"] += delta
    for arm in ARMS:
        arms[arm]["majority_accuracy"] = (
            arms[arm]["majority_correct"] / arms[arm]["questions"]
        )
        for category in arms[arm]["category_accuracy"].values():
            category["accuracy"] = category["correct"] / category["questions"]

    wins = sum(
        human_scores[question_id]["candidate"]
        > human_scores[question_id]["baseline"]
        for question_id in unique_ids
    )
    losses = sum(
        human_scores[question_id]["candidate"]
        < human_scores[question_id]["baseline"]
        for question_id in unique_ids
    )
    paired = {
        "wins": wins,
        "losses": losses,
        "ties": int(machine["question_count"]) - wins - losses,
        "accuracy_delta": (
            arms["candidate"]["majority_accuracy"]
            - arms["baseline"]["majority_accuracy"]
        ),
    }
    synthetic_report = {
        "model": machine["model"],
        "summary": {"failed_answer_calls": 0, "failed_judge_calls": 0},
        "budget": {"max_total_usd": contract["budget"]["maximum_total_cost_usd"]},
    }
    gate_results = evaluate_gates(
        report=synthetic_report,
        arm_metrics=arms,
        paired=paired,
        cost=machine["cost"],
        gates=contract["automated_gates"],
    )
    judge_human_agreement = sum(judge_comparisons) / len(judge_comparisons)
    intrarater_agreement = (
        sum(reliability_comparisons) / len(reliability_comparisons)
        if reliability_comparisons
        else 1.0
    )
    human_gate_results = {
        "minimum_judge_human_agreement": judge_human_agreement
        >= float(contract["human_audit"]["minimum_judge_human_agreement"]),
        "minimum_intrarater_agreement": intrarater_agreement
        >= float(contract["human_audit"]["minimum_intrarater_agreement"]),
    }
    automated_passed = all(gate_results.values())
    human_passed = all(human_gate_results.values())
    return {
        "schema_version": 1,
        "status": "passed" if automated_passed and human_passed else "failed",
        "model": machine["model"],
        "question_count": machine["question_count"],
        "unique_human_audit_questions": len(unique_ids),
        "reliability_duplicate_items": packet["reliability_duplicate_items"],
        "arms": arms,
        "paired": paired,
        "judge_human_agreement": judge_human_agreement,
        "intrarater_agreement": intrarater_agreement,
        "gate_results_after_human_substitution": gate_results,
        "human_gate_results": human_gate_results,
        "automated_gates_passed": automated_passed,
        "human_gates_passed": human_passed,
        "all_gates_passed": automated_passed and human_passed,
        "cost": machine["cost"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--machine", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    key = json.loads(args.key.read_text(encoding="utf-8"))
    machine = json.loads(args.machine.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    expected_packet, expected_key = build_packet(
        raw,
        checkpoint,
        contract,
        checkpoint_sha256=_sha256(args.checkpoint),
    )
    expected_key["source_sha256"] = {
        "raw": _sha256(args.raw),
        "checkpoint": _sha256(args.checkpoint),
        "contract": _sha256(args.contract),
    }
    if key != expected_key:
        raise PairedHumanAuditError("audit key differs from frozen source evidence")
    if _unscored_packet(packet) != expected_packet:
        raise PairedHumanAuditError("audit packet content changed outside human score fields")
    if machine.get("source_sha256", {}).get("raw") != expected_key["source_sha256"]["raw"]:
        raise PairedHumanAuditError("machine analysis identifies a different raw run")
    evidence = adjudicate(packet, key, machine, contract)
    evidence["source_sha256"] = {
        "packet": _sha256(args.packet),
        "key": _sha256(args.key),
        "machine": _sha256(args.machine),
        "contract": _sha256(args.contract),
        "raw": _sha256(args.raw),
        "checkpoint": _sha256(args.checkpoint),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["all_gates_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
