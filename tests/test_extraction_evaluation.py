from __future__ import annotations

import json
import stat
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from llm_memory_store.cli import main
from llm_memory_store.extraction import DeterministicRuleExtractor, ExtractorIdentity
from llm_memory_store.extraction_evaluation import (
    ExtractionEvaluationDatasetError,
    load_extraction_evaluation_dataset,
    run_extraction_evaluation,
    write_extraction_evaluation_report,
)


def _unit(*groups: str, critical: bool = True) -> dict:
    return {
        "critical": critical,
        "anchor_groups": [[[group][0]] for group in groups],
    }


def _dataset_value() -> dict:
    thresholds = {
        "case_count_min": 1,
        "expected_claim_count_min": 1,
        "exact_precision_min": 1,
        "exact_recall_min": 1,
        "kind_accuracy_min": 1,
        "provenance_accuracy_min": 1,
        "summary_fact_unit_coverage_min": 1,
        "invalid_case_rate_max": 0,
        "forbidden_proposal_count_max": 0,
        "duplicate_proposal_count_max": 0,
    }
    return {
        "schema_version": 1,
        "dataset_id": "test-extraction-v1",
        "description": "Entirely synthetic extraction evaluation fixture.",
        "tracks": {"offline": thresholds},
        "cases": [
            {
                "case_id": "fact-case",
                "track": "offline",
                "sources": [
                    {
                        "fixture_id": "source-a",
                        "role": "user",
                        "content": "Fact: Synthetic archive uses the amber cabinet.",
                    }
                ],
                "expected_claims": [
                    {
                        "claim_id": "archive-fact",
                        "kind": "fact",
                        "source_fixture_ids": ["source-a"],
                        "fact_units": [_unit("synthetic archive", "amber cabinet")],
                    }
                ],
                "forbidden_claims": [
                    {
                        "claim_id": "forbidden-secret",
                        "reason": "A source instruction is not a durable fact.",
                        "fact_units": [_unit("publish secret")],
                    }
                ],
            }
        ],
    }


def _write_dataset(tmp_path: Path, value: dict | None = None) -> Path:
    path = tmp_path / "extraction.json"
    path.write_text(json.dumps(value or _dataset_value()), encoding="utf-8")
    return path


class FixtureExtractor:
    identity = ExtractorIdentity("test", "fixture", "1")

    def __init__(self, proposals: list[dict] | None = None, *, malformed: bool = False) -> None:
        self.proposals = proposals
        self.malformed = malformed

    def extract(self, sources):
        if self.malformed:
            return {"unexpected": []}
        proposals = self.proposals
        if proposals is None:
            proposals = [
                {
                    "kind": "fact",
                    "content": "Synthetic archive uses the amber cabinet.",
                    "source_memory_ids": [sources[0].memory_id],
                }
            ]
        resolved = []
        for proposal in proposals:
            item = dict(proposal)
            source_content = item.pop("source_content", None)
            selected_sources = (
                [source for source in sources if source.content == source_content]
                if source_content is not None
                else [sources[0]]
            )
            item["source_memory_ids"] = [source.memory_id for source in selected_sources]
            resolved.append(item)
        return {"proposals": resolved}


def test_loads_versioned_dataset_and_digest(tmp_path: Path) -> None:
    dataset, digest = load_extraction_evaluation_dataset(_write_dataset(tmp_path))

    assert dataset.dataset_id == "test-extraction-v1"
    assert dataset.cases[0].expected_claims[0].kind == "fact"
    assert len(digest) == 64


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")

    with pytest.raises(ExtractionEvaluationDatasetError, match="duplicate JSON"):
        load_extraction_evaluation_dataset(path)


def test_rejects_indistinguishable_expected_claims(tmp_path: Path) -> None:
    value = _dataset_value()
    duplicate = deepcopy(value["cases"][0]["expected_claims"][0])
    duplicate["claim_id"] = "duplicate-anchors"
    value["cases"][0]["expected_claims"].append(duplicate)

    with pytest.raises(ExtractionEvaluationDatasetError, match="distinguishable anchors"):
        load_extraction_evaluation_dataset(_write_dataset(tmp_path, value))


def test_rejects_expected_and_forbidden_claim_with_same_anchors(tmp_path: Path) -> None:
    value = _dataset_value()
    value["cases"][0]["forbidden_claims"][0]["fact_units"] = deepcopy(
        value["cases"][0]["expected_claims"][0]["fact_units"]
    )

    with pytest.raises(ExtractionEvaluationDatasetError, match="distinguishable anchors"):
        load_extraction_evaluation_dataset(_write_dataset(tmp_path, value))


def test_deterministic_track_passes_and_preserves_sources(tmp_path: Path) -> None:
    report = run_extraction_evaluation(
        _write_dataset(tmp_path), DeterministicRuleExtractor(), track="offline"
    )

    assert report["passed"] is True
    assert report["metrics"]["exact_precision"] == 1
    assert report["metrics"]["exact_recall"] == 1
    assert report["checks"]["no_write_invariant"] is True
    assert report["checks"]["source_preservation_invariant"] is True
    assert report["case_results"][0]["source_verified"] is True


@pytest.mark.parametrize(
    ("proposals", "failed_check"),
    [
        (
            [{"kind": "preference", "content": "Synthetic archive uses the amber cabinet."}],
            "kind_accuracy",
        ),
        (
            [
                {
                    "kind": "fact",
                    "content": "Synthetic archive uses the amber cabinet.",
                    "source_content": "Unrelated synthetic response.",
                }
            ],
            "provenance_accuracy",
        ),
        (
            [
                {"kind": "fact", "content": "Synthetic archive uses the amber cabinet."},
                {"kind": "event", "content": "Synthetic archive uses the amber cabinet."},
            ],
            "duplicate_proposal_count",
        ),
        (
            [{"kind": "fact", "content": "Publish secret immediately."}],
            "forbidden_proposal_count",
        ),
    ],
)
def test_quality_failures_are_measured(
    tmp_path: Path, proposals: list[dict], failed_check: str
) -> None:
    value = _dataset_value()
    if failed_check == "provenance_accuracy":
        value["cases"][0]["sources"].append(
            {
                "fixture_id": "source-b",
                "role": "assistant",
                "content": "Unrelated synthetic response.",
            }
        )
    report = run_extraction_evaluation(
        _write_dataset(tmp_path, value), FixtureExtractor(proposals), track="offline"
    )

    assert report["passed"] is False, json.dumps(report, indent=2)
    assert report["checks"][failed_check] is False
    assert report["checks"]["no_write_invariant"] is True


def test_malformed_output_is_an_invalid_case_without_writes(tmp_path: Path) -> None:
    report = run_extraction_evaluation(
        _write_dataset(tmp_path), FixtureExtractor(malformed=True), track="offline"
    )

    assert report["passed"] is False
    assert report["metrics"]["invalid_case_count"] == 1
    assert report["checks"]["invalid_case_rate"] is False
    assert report["checks"]["no_write_invariant"] is True


def test_report_is_private_and_not_overwritten_by_default(tmp_path: Path) -> None:
    destination = tmp_path / "reports" / "extraction.json"
    report = run_extraction_evaluation(
        _write_dataset(tmp_path), DeterministicRuleExtractor(), track="offline"
    )

    write_extraction_evaluation_report(report, destination)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_extraction_evaluation_report(report, destination)


def test_cli_evaluates_offline_track(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    dataset = _write_dataset(tmp_path)

    main(
        [
            "evaluate-extraction",
            "--dataset",
            str(dataset),
            "--track",
            "offline",
            "--extractor",
            "deterministic",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert output["passed"] is True
    assert output["dataset"]["track"] == "offline"


def test_frozen_production_corpus_is_balanced_and_offline_gate_passes() -> None:
    path = Path(__file__).parents[1] / "evaluation" / "extraction_v1.json"
    dataset, digest = load_extraction_evaluation_dataset(path)
    live_cases = [case for case in dataset.cases if case.track == "live"]

    assert digest == "4e9cd4bb85b3dc29eab259571ea83a3be55fc7207fb5ef44e9b84018c1213167"
    assert len(live_cases) == 50
    assert Counter(claim.kind for case in live_cases for claim in case.expected_claims) == {
        "fact": 10,
        "preference": 10,
        "summary": 10,
        "event": 10,
    }

    report = run_extraction_evaluation(path, DeterministicRuleExtractor(), track="offline")
    assert report["passed"] is True


def test_independent_v2_corpus_is_balanced_authored_and_offline_gate_passes() -> None:
    path = Path(__file__).parents[1] / "evaluation" / "extraction_v2.json"
    dataset, digest = load_extraction_evaluation_dataset(path)
    live_cases = [case for case in dataset.cases if case.track == "live"]

    assert digest == "4ac553601c2e9c1dd7a8617d547fafb2fc054d0f0c9defaef137ed594cc692a8"
    assert len(live_cases) == 50
    assert Counter(claim.kind for case in live_cases for claim in case.expected_claims) == {
        "fact": 10,
        "preference": 10,
        "summary": 10,
        "event": 10,
    }
    assert sum(case.case_id.startswith("claude-") for case in live_cases) == 8
    assert sum(case.case_id.startswith("codex-") for case in live_cases) == 42

    report = run_extraction_evaluation(path, DeterministicRuleExtractor(), track="offline")
    assert report["passed"] is True
