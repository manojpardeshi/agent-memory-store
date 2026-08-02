from __future__ import annotations

import copy

import pytest

from scripts.adjudicate_kimi_paired_human_audit import (
    PairedHumanAuditError,
    adjudicate,
)
from scripts.analyze_kimi_paired_answer_run import analyze_report
from scripts.prepare_kimi_paired_human_audit import build_packet
from tests.test_analyze_kimi_paired_answer_run import paired_inputs
from tests.test_prepare_kimi_paired_human_audit import _checkpoint


def _scored_inputs() -> tuple[dict, dict, dict, dict]:
    report, contract = paired_inputs()
    contract["human_audit"] = {
        "minimum_unique_audit_questions": 4,
        "replicate_fraction": 0.2,
        "minimum_intrarater_agreement": 0.9,
        "minimum_judge_human_agreement": 0.75,
    }
    packet, key = build_packet(
        report,
        _checkpoint(report),
        contract,
        checkpoint_sha256="baseline-source",
    )
    packet_by_id = {item["audit_id"]: item for item in packet["items"]}
    for key_item in key["items"]:
        packet_item = packet_by_id[key_item["audit_id"]]
        majority = key_item["selection_reason"]["model_judge_majority"]
        packet_item["left_human_score"] = majority[key_item["left_arm"]]
        packet_item["right_human_score"] = majority[key_item["right_arm"]]
    return packet, key, analyze_report(report, contract), contract


def test_adjudicate_substitutes_human_labels_and_passes_frozen_gates() -> None:
    packet, key, machine, contract = _scored_inputs()

    evidence = adjudicate(packet, key, machine, contract)

    assert evidence["status"] == "passed"
    assert evidence["arms"]["baseline"]["majority_correct"] == 42
    assert evidence["arms"]["candidate"]["majority_correct"] == 44
    assert evidence["judge_human_agreement"] == 1.0
    assert evidence["intrarater_agreement"] == 1.0
    assert evidence["all_gates_passed"] is True


def test_adjudicate_rejects_missing_score() -> None:
    packet, key, machine, contract = _scored_inputs()
    packet["items"][0]["left_human_score"] = None

    with pytest.raises(PairedHumanAuditError, match="must be 0 or 1"):
        adjudicate(packet, key, machine, contract)


def test_adjudicate_fails_intrarater_gate_on_changed_duplicate() -> None:
    packet, key, machine, contract = _scored_inputs()
    changed = copy.deepcopy(packet)
    duplicate_id = next(
        item["audit_id"] for item in key["items"] if item["duplicate_of_source_id"]
    )
    duplicate = next(item for item in changed["items"] if item["audit_id"] == duplicate_id)
    duplicate["left_human_score"] = 1 - duplicate["left_human_score"]

    evidence = adjudicate(changed, key, machine, contract)

    assert evidence["human_gate_results"]["minimum_intrarater_agreement"] is False
    assert evidence["all_gates_passed"] is False
