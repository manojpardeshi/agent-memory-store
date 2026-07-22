"""Versioned, judge-free quality evaluation for extraction proposals."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import secure_write_text
from .embeddings import DeterministicEmbedder
from .extraction import ExtractionProposal, ProposalExtractor, create_proposal_bundle
from .models import Scope
from .store import MemoryStore

EXTRACTION_EVALUATION_SCHEMA_VERSION = 1
MAX_DATASET_BYTES = 2_000_000
MAX_CASES = 500
MAX_CASE_SOURCES = 20
MAX_CLAIMS_PER_CASE = 50
_SPACE = re.compile(r"[^\w]+", re.UNICODE)


class ExtractionEvaluationDatasetError(ValueError):
    """Raised when an extraction evaluation corpus is ambiguous or invalid."""


@dataclass(frozen=True, slots=True)
class ExtractionThresholds:
    case_count_min: int
    expected_claim_count_min: int
    exact_precision_min: float
    exact_recall_min: float
    kind_accuracy_min: float
    provenance_accuracy_min: float
    summary_fact_unit_coverage_min: float
    invalid_case_rate_max: float
    forbidden_proposal_count_max: int
    duplicate_proposal_count_max: int


@dataclass(frozen=True, slots=True)
class AnchorFactUnit:
    critical: bool
    anchor_groups: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class ExpectedExtractionClaim:
    claim_id: str
    kind: str
    source_fixture_ids: tuple[str, ...]
    fact_units: tuple[AnchorFactUnit, ...]


@dataclass(frozen=True, slots=True)
class ForbiddenExtractionClaim:
    claim_id: str
    reason: str
    fact_units: tuple[AnchorFactUnit, ...]


@dataclass(frozen=True, slots=True)
class ExtractionSource:
    fixture_id: str
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ExtractionEvaluationCase:
    case_id: str
    track: str
    sources: tuple[ExtractionSource, ...]
    expected_claims: tuple[ExpectedExtractionClaim, ...]
    forbidden_claims: tuple[ForbiddenExtractionClaim, ...]


@dataclass(frozen=True, slots=True)
class ExtractionEvaluationDataset:
    schema_version: int
    dataset_id: str
    description: str
    tracks: dict[str, ExtractionThresholds]
    cases: tuple[ExtractionEvaluationCase, ...]


def _normalized(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(part for part in _SPACE.split(text) if part)


def _required_string(value: object, field: str, maximum: int = 10_000) -> str:
    if not isinstance(value, str):
        raise ExtractionEvaluationDatasetError(f"{field} must be a string")
    cleaned = unicodedata.normalize("NFC", value).strip()
    if not cleaned:
        raise ExtractionEvaluationDatasetError(f"{field} must not be empty")
    if len(cleaned) > maximum:
        raise ExtractionEvaluationDatasetError(f"{field} must be at most {maximum} characters")
    return cleaned


def _exact_object(
    value: object, field: str, allowed: set[str], required: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ExtractionEvaluationDatasetError(f"{field} must be an object")
    missing = (required or allowed) - set(value)
    unknown = set(value) - allowed
    if missing:
        raise ExtractionEvaluationDatasetError(f"{field} is missing fields: {sorted(missing)}")
    if unknown:
        raise ExtractionEvaluationDatasetError(f"{field} has unknown fields: {sorted(unknown)}")
    return value


def _rate(value: object, field: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ExtractionEvaluationDatasetError(f"{field} must be between 0 and 1")
    return float(value)


def _count(value: object, field: str, maximum: int = 100_000) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= maximum:
        raise ExtractionEvaluationDatasetError(f"{field} must be an integer from 0 to {maximum}")
    return value


def _thresholds(value: object, field: str) -> ExtractionThresholds:
    item = _exact_object(
        value,
        field,
        {
            "case_count_min",
            "expected_claim_count_min",
            "exact_precision_min",
            "exact_recall_min",
            "kind_accuracy_min",
            "provenance_accuracy_min",
            "summary_fact_unit_coverage_min",
            "invalid_case_rate_max",
            "forbidden_proposal_count_max",
            "duplicate_proposal_count_max",
        },
    )
    thresholds = ExtractionThresholds(
        case_count_min=_count(item["case_count_min"], f"{field}.case_count_min", MAX_CASES),
        expected_claim_count_min=_count(
            item["expected_claim_count_min"], f"{field}.expected_claim_count_min"
        ),
        exact_precision_min=_rate(item["exact_precision_min"], f"{field}.exact_precision_min"),
        exact_recall_min=_rate(item["exact_recall_min"], f"{field}.exact_recall_min"),
        kind_accuracy_min=_rate(item["kind_accuracy_min"], f"{field}.kind_accuracy_min"),
        provenance_accuracy_min=_rate(
            item["provenance_accuracy_min"], f"{field}.provenance_accuracy_min"
        ),
        summary_fact_unit_coverage_min=_rate(
            item["summary_fact_unit_coverage_min"],
            f"{field}.summary_fact_unit_coverage_min",
        ),
        invalid_case_rate_max=_rate(
            item["invalid_case_rate_max"], f"{field}.invalid_case_rate_max"
        ),
        forbidden_proposal_count_max=_count(
            item["forbidden_proposal_count_max"],
            f"{field}.forbidden_proposal_count_max",
        ),
        duplicate_proposal_count_max=_count(
            item["duplicate_proposal_count_max"],
            f"{field}.duplicate_proposal_count_max",
        ),
    )
    if thresholds.case_count_min == 0:
        raise ExtractionEvaluationDatasetError(f"{field}.case_count_min must be positive")
    if thresholds.expected_claim_count_min == 0:
        raise ExtractionEvaluationDatasetError(f"{field}.expected_claim_count_min must be positive")
    return thresholds


def _fact_units(value: object, field: str) -> tuple[AnchorFactUnit, ...]:
    if not isinstance(value, list) or not value:
        raise ExtractionEvaluationDatasetError(f"{field} must be a non-empty array")
    units: list[AnchorFactUnit] = []
    for unit_index, raw_unit in enumerate(value):
        unit_field = f"{field}[{unit_index}]"
        unit = _exact_object(raw_unit, unit_field, {"critical", "anchor_groups"})
        if not isinstance(unit["critical"], bool):
            raise ExtractionEvaluationDatasetError(f"{unit_field}.critical must be boolean")
        raw_groups = unit["anchor_groups"]
        if not isinstance(raw_groups, list) or not raw_groups:
            raise ExtractionEvaluationDatasetError(
                f"{unit_field}.anchor_groups must be a non-empty array"
            )
        groups: list[tuple[str, ...]] = []
        for group_index, raw_group in enumerate(raw_groups):
            group_field = f"{unit_field}.anchor_groups[{group_index}]"
            if not isinstance(raw_group, list) or not raw_group:
                raise ExtractionEvaluationDatasetError(f"{group_field} must be a non-empty array")
            alternatives = tuple(
                _required_string(alternative, group_field, 100) for alternative in raw_group
            )
            normalized = tuple(_normalized(alternative) for alternative in alternatives)
            if any(len(alternative.replace(" ", "")) < 3 for alternative in normalized):
                raise ExtractionEvaluationDatasetError(
                    f"{group_field} alternatives must contain at least 3 alphanumeric characters"
                )
            if len(set(normalized)) != len(normalized):
                raise ExtractionEvaluationDatasetError(
                    f"{group_field} alternatives must be unique after normalization"
                )
            groups.append(alternatives)
        units.append(AnchorFactUnit(unit["critical"], tuple(groups)))
    return tuple(units)


def _string_ids(value: object, field: str, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise ExtractionEvaluationDatasetError(
            f"{field} must contain between 1 and {maximum} strings"
        )
    result = tuple(_required_string(item, field, 128) for item in value)
    if len(set(result)) != len(result):
        raise ExtractionEvaluationDatasetError(f"{field} must contain unique values")
    return result


def _expected_claim(value: object, field: str) -> ExpectedExtractionClaim:
    item = _exact_object(
        value,
        field,
        {"claim_id", "kind", "source_fixture_ids", "fact_units"},
    )
    kind = _required_string(item["kind"], f"{field}.kind", 32)
    if kind not in ("fact", "preference", "summary", "event"):
        raise ExtractionEvaluationDatasetError(f"{field}.kind is unsupported")
    return ExpectedExtractionClaim(
        claim_id=_required_string(item["claim_id"], f"{field}.claim_id", 128),
        kind=kind,
        source_fixture_ids=_string_ids(
            item["source_fixture_ids"], f"{field}.source_fixture_ids", MAX_CASE_SOURCES
        ),
        fact_units=_fact_units(item["fact_units"], f"{field}.fact_units"),
    )


def _forbidden_claim(value: object, field: str) -> ForbiddenExtractionClaim:
    item = _exact_object(value, field, {"claim_id", "reason", "fact_units"})
    return ForbiddenExtractionClaim(
        claim_id=_required_string(item["claim_id"], f"{field}.claim_id", 128),
        reason=_required_string(item["reason"], f"{field}.reason", 512),
        fact_units=_fact_units(item["fact_units"], f"{field}.fact_units"),
    )


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExtractionEvaluationDatasetError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _fact_units_fingerprint(
    fact_units: Sequence[AnchorFactUnit],
) -> tuple[tuple[tuple[str, ...], ...], ...]:
    return tuple(
        sorted(
            tuple(
                sorted(
                    tuple(sorted(_normalized(value) for value in group))
                    for group in unit.anchor_groups
                )
            )
            for unit in fact_units
        )
    )


def load_extraction_evaluation_dataset(
    path: str | Path,
) -> tuple[ExtractionEvaluationDataset, str]:
    source = Path(path).expanduser().resolve()
    with source.open("rb") as handle:
        raw = handle.read(MAX_DATASET_BYTES + 1)
    if len(raw) > MAX_DATASET_BYTES:
        raise ExtractionEvaluationDatasetError("extraction dataset exceeds the byte limit")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ExtractionEvaluationDatasetError("extraction dataset is not valid JSON") from exc
    root = _exact_object(
        value,
        "dataset",
        {"schema_version", "dataset_id", "description", "tracks", "cases"},
    )
    if root["schema_version"] != EXTRACTION_EVALUATION_SCHEMA_VERSION:
        raise ExtractionEvaluationDatasetError("unsupported extraction dataset schema version")
    raw_tracks = root["tracks"]
    if not isinstance(raw_tracks, dict) or not raw_tracks:
        raise ExtractionEvaluationDatasetError("tracks must be a non-empty object")
    tracks = {
        _required_string(name, "track name", 64): _thresholds(thresholds, f"tracks.{name}")
        for name, thresholds in raw_tracks.items()
    }
    raw_cases = root["cases"]
    if not isinstance(raw_cases, list) or not 1 <= len(raw_cases) <= MAX_CASES:
        raise ExtractionEvaluationDatasetError(
            f"cases must contain between 1 and {MAX_CASES} items"
        )
    cases: list[ExtractionEvaluationCase] = []
    for index, raw_case in enumerate(raw_cases):
        field = f"cases[{index}]"
        item = _exact_object(
            raw_case,
            field,
            {"case_id", "track", "sources", "expected_claims", "forbidden_claims"},
        )
        case_id = _required_string(item["case_id"], f"{field}.case_id", 128)
        track = _required_string(item["track"], f"{field}.track", 64)
        if track not in tracks:
            raise ExtractionEvaluationDatasetError(f"{field}.track is not declared")
        raw_sources = item["sources"]
        if not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= MAX_CASE_SOURCES:
            raise ExtractionEvaluationDatasetError(
                f"{field}.sources must contain between 1 and {MAX_CASE_SOURCES} items"
            )
        sources: list[ExtractionSource] = []
        for source_index, raw_source in enumerate(raw_sources):
            source_field = f"{field}.sources[{source_index}]"
            source_item = _exact_object(raw_source, source_field, {"fixture_id", "role", "content"})
            role = _required_string(source_item["role"], f"{source_field}.role", 32)
            if role not in ("user", "assistant", "system", "tool"):
                raise ExtractionEvaluationDatasetError(f"{source_field}.role is invalid")
            sources.append(
                ExtractionSource(
                    _required_string(source_item["fixture_id"], f"{source_field}.fixture_id", 128),
                    role,
                    _required_string(source_item["content"], f"{source_field}.content"),
                )
            )
        source_ids = {source.fixture_id for source in sources}
        if len(source_ids) != len(sources):
            raise ExtractionEvaluationDatasetError(f"{field}.sources fixture IDs must be unique")
        for claim_field in ("expected_claims", "forbidden_claims"):
            if (
                not isinstance(item[claim_field], list)
                or len(item[claim_field]) > MAX_CLAIMS_PER_CASE
            ):
                raise ExtractionEvaluationDatasetError(
                    f"{field}.{claim_field} must be an array of at most {MAX_CLAIMS_PER_CASE} items"
                )
        expected = tuple(
            _expected_claim(claim, f"{field}.expected_claims[{claim_index}]")
            for claim_index, claim in enumerate(item["expected_claims"])
        )
        forbidden = tuple(
            _forbidden_claim(claim, f"{field}.forbidden_claims[{claim_index}]")
            for claim_index, claim in enumerate(item["forbidden_claims"])
        )
        claim_ids = [claim.claim_id for claim in (*expected, *forbidden)]
        if len(set(claim_ids)) != len(claim_ids):
            raise ExtractionEvaluationDatasetError(f"{field} claim IDs must be unique")
        fingerprints = [
            _fact_units_fingerprint(claim.fact_units) for claim in (*expected, *forbidden)
        ]
        if len(set(fingerprints)) != len(fingerprints):
            raise ExtractionEvaluationDatasetError(
                f"{field} claims must have distinguishable anchors"
            )
        missing_sources = sorted(
            {
                fixture_id
                for claim in expected
                for fixture_id in claim.source_fixture_ids
                if fixture_id not in source_ids
            }
        )
        if missing_sources:
            raise ExtractionEvaluationDatasetError(
                f"{field} claims reference unknown sources: {missing_sources}"
            )
        cases.append(ExtractionEvaluationCase(case_id, track, tuple(sources), expected, forbidden))
    if len({case.case_id for case in cases}) != len(cases):
        raise ExtractionEvaluationDatasetError("case IDs must be unique")
    for track_name, thresholds in tracks.items():
        track_cases = [case for case in cases if case.track == track_name]
        expected_count = sum(len(case.expected_claims) for case in track_cases)
        if len(track_cases) < thresholds.case_count_min:
            raise ExtractionEvaluationDatasetError(
                f"track {track_name} has fewer cases than case_count_min"
            )
        if expected_count < thresholds.expected_claim_count_min:
            raise ExtractionEvaluationDatasetError(
                f"track {track_name} has fewer claims than expected_claim_count_min"
            )
    return (
        ExtractionEvaluationDataset(
            EXTRACTION_EVALUATION_SCHEMA_VERSION,
            _required_string(root["dataset_id"], "dataset_id", 128),
            _required_string(root["description"], "description", 1_000),
            tracks,
            tuple(cases),
        ),
        digest,
    )


def _unit_covered(content: str, unit: AnchorFactUnit) -> bool:
    normalized_content = f" {_normalized(content)} "
    for alternatives in unit.anchor_groups:
        if not any(
            f" {_normalized(alternative)} " in normalized_content for alternative in alternatives
        ):
            return False
    return True


def _claim_coverage(content: str, fact_units: Sequence[AnchorFactUnit]) -> tuple[int, int, bool]:
    covered = [_unit_covered(content, unit) for unit in fact_units]
    critical_missing = any(
        unit.critical and not is_covered
        for unit, is_covered in zip(fact_units, covered, strict=True)
    )
    return sum(covered), len(covered), critical_missing


def _content_match(content: str, fact_units: Sequence[AnchorFactUnit]) -> bool:
    covered, total, critical_missing = _claim_coverage(content, fact_units)
    return not critical_missing and covered / total >= 0.85


def _wilson(successes: int, total: int) -> dict[str, float]:
    if total == 0:
        return {"low": 0.0, "high": 1.0}
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return {"low": max(0.0, center - margin), "high": min(1.0, center + margin)}


def _safe_rate(numerator: int, denominator: int, *, empty: float = 1.0) -> float:
    return numerator / denominator if denominator else empty


def _proposal_detail(
    proposal: ExtractionProposal,
    public_to_fixture: dict[str, str],
    forbidden_matches: Sequence[str],
) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "kind": proposal.kind,
        "content": proposal.content,
        "source_fixture_ids": sorted(
            public_to_fixture.get(source_id, "<unknown>")
            for source_id in proposal.source_memory_ids
        ),
        "source_relation": proposal.source_relation,
        "confidence": proposal.confidence,
        "forbidden_matches": list(forbidden_matches),
    }


def _score_case(
    case: ExtractionEvaluationCase,
    proposals: Sequence[ExtractionProposal],
    public_to_fixture: dict[str, str],
) -> dict[str, Any]:
    expected_by_id = {claim.claim_id: claim for claim in case.expected_claims}
    candidates_by_claim: dict[str, list[tuple[ExtractionProposal, bool, bool]]] = defaultdict(list)
    ambiguous_proposals: set[str] = set()
    forbidden_by_proposal: dict[str, list[str]] = {}
    summary_best_coverage: dict[str, tuple[int, int, bool]] = {}
    for proposal in proposals:
        matching_claims = [
            claim
            for claim in case.expected_claims
            if _content_match(proposal.content, claim.fact_units)
        ]
        if len(matching_claims) > 1:
            ambiguous_proposals.add(proposal.proposal_id)
        elif matching_claims:
            claim = matching_claims[0]
            source_fixtures = tuple(
                sorted(
                    public_to_fixture.get(source_id, "<unknown>")
                    for source_id in proposal.source_memory_ids
                )
            )
            kind_correct = proposal.kind == claim.kind
            provenance_correct = source_fixtures == tuple(sorted(claim.source_fixture_ids))
            candidates_by_claim[claim.claim_id].append((proposal, kind_correct, provenance_correct))
        for claim in case.expected_claims:
            if claim.kind == "summary":
                coverage = _claim_coverage(proposal.content, claim.fact_units)
                previous = summary_best_coverage.get(claim.claim_id, (0, coverage[1], True))
                if coverage[0] > previous[0]:
                    summary_best_coverage[claim.claim_id] = coverage
        forbidden_by_proposal[proposal.proposal_id] = [
            claim.claim_id
            for claim in case.forbidden_claims
            if _content_match(proposal.content, claim.fact_units)
        ]

    matched: dict[str, tuple[ExtractionProposal, bool, bool]] = {}
    for claim_id, candidates in candidates_by_claim.items():
        matched[claim_id] = sorted(
            candidates,
            key=lambda item: (
                -(int(item[1]) + int(item[2])),
                -int(item[1]),
                -int(item[2]),
                item[0].proposal_id,
            ),
        )[0]
    exact_claim_ids = {
        claim_id for claim_id, (_, kind_ok, source_ok) in matched.items() if kind_ok and source_ok
    }
    normalized_contents = [_normalized(proposal.content) for proposal in proposals]
    duplicate_count = len(normalized_contents) - len(set(normalized_contents))
    forbidden_count = sum(bool(matches) for matches in forbidden_by_proposal.values())
    summary_covered = 0
    summary_total = 0
    summary_critical_missing = 0
    for claim in case.expected_claims:
        if claim.kind != "summary":
            continue
        covered, total, critical_missing = summary_best_coverage.get(
            claim.claim_id,
            (0, len(claim.fact_units), any(unit.critical for unit in claim.fact_units)),
        )
        summary_covered += covered
        summary_total += total
        summary_critical_missing += int(critical_missing)
    matched_proposal_ids = {value[0].proposal_id for value in matched.values()}
    return {
        "case_id": case.case_id,
        "track": case.track,
        "expected_claim_count": len(case.expected_claims),
        "proposal_count": len(proposals),
        "content_matched_claim_ids": sorted(matched),
        "exact_matched_claim_ids": sorted(exact_claim_ids),
        "unmatched_expected_claim_ids": sorted(set(expected_by_id) - set(matched)),
        "unmatched_proposal_ids": sorted(
            proposal.proposal_id
            for proposal in proposals
            if proposal.proposal_id not in matched_proposal_ids
        ),
        "kind_correct_count": sum(kind_ok for _, kind_ok, _ in matched.values()),
        "provenance_correct_count": sum(source_ok for _, _, source_ok in matched.values()),
        "forbidden_proposal_count": forbidden_count,
        "duplicate_proposal_count": duplicate_count,
        "ambiguous_content_match_count": len(ambiguous_proposals),
        "summary_fact_units_covered": summary_covered,
        "summary_fact_units_total": summary_total,
        "summary_critical_units_missing": summary_critical_missing,
        "proposals": [
            _proposal_detail(
                proposal, public_to_fixture, forbidden_by_proposal[proposal.proposal_id]
            )
            for proposal in proposals
        ],
    }


def run_extraction_evaluation(
    dataset_path: str | Path,
    extractor: ProposalExtractor,
    *,
    track: str,
) -> dict[str, Any]:
    """Run proposal generation without artifact creation or proposal acceptance."""

    dataset, dataset_digest = load_extraction_evaluation_dataset(dataset_path)
    if track not in dataset.tracks:
        raise ExtractionEvaluationDatasetError(f"unknown extraction evaluation track: {track}")
    cases = [case for case in dataset.cases if case.track == track]
    thresholds = dataset.tracks[track]
    started = time.perf_counter()
    case_results: list[dict[str, Any]] = []
    invalid_cases = 0
    no_write_violations = 0
    source_mutation_violations = 0
    with (
        tempfile.TemporaryDirectory(prefix="llm-memory-extraction-eval-") as directory,
        MemoryStore(
            Path(directory) / "evaluation.sqlite3",
            DeterministicEmbedder(64),
            default_turn_ttl_days=None,
        ) as store,
    ):
        for case in cases:
            scope = Scope.private(dataset.dataset_id, track, case.case_id)
            fixture_to_public: dict[str, str] = {}
            source_snapshots: dict[str, tuple[str, str, str]] = {}
            for source in case.sources:
                record = store.remember_turn(
                    source.content,
                    source.role,  # type: ignore[arg-type]
                    scope,
                    operation_id=f"{dataset.dataset_id}:{track}:{case.case_id}:{source.fixture_id}",
                )
                fixture_to_public[source.fixture_id] = record.memory_id
                source_snapshots[record.memory_id] = (
                    hashlib.sha256(record.content.encode("utf-8")).hexdigest(),
                    record.status,
                    record.content,
                )
            before_count = store.status()["memories"]
            error: dict[str, str] | None = None
            proposals: tuple[ExtractionProposal, ...] = ()
            try:
                bundle = create_proposal_bundle(
                    store,
                    list(fixture_to_public.values()),
                    scope,
                    extractor,
                )
                proposals = bundle.proposals
            except Exception as exc:  # model/runtime failures are case evidence
                invalid_cases += 1
                error = {
                    "type": type(exc).__name__,
                    "message": str(exc)[:500],
                }
            after_count = store.status()["memories"]
            no_write_verified = before_count == after_count
            no_write_violations += int(not no_write_verified)
            source_verified = True
            for public_id, snapshot in source_snapshots.items():
                current = store.get(public_id)
                current_snapshot = (
                    hashlib.sha256(current.content.encode("utf-8")).hexdigest(),
                    current.status,
                    current.content,
                )
                source_verified = source_verified and current_snapshot == snapshot
            source_mutation_violations += int(not source_verified)
            scored = _score_case(case, proposals, {v: k for k, v in fixture_to_public.items()})
            scored.update(
                {
                    "valid": error is None,
                    "error": error,
                    "no_write_verified": no_write_verified,
                    "source_verified": source_verified,
                }
            )
            case_results.append(scored)

    totals = Counter()
    kind_expected = Counter()
    kind_exact = Counter()
    for case, result in zip(cases, case_results, strict=True):
        for key in (
            "expected_claim_count",
            "proposal_count",
            "kind_correct_count",
            "provenance_correct_count",
            "forbidden_proposal_count",
            "duplicate_proposal_count",
            "ambiguous_content_match_count",
            "summary_fact_units_covered",
            "summary_fact_units_total",
            "summary_critical_units_missing",
        ):
            totals[key] += result[key]
        totals["content_match_count"] += len(result["content_matched_claim_ids"])
        totals["exact_match_count"] += len(result["exact_matched_claim_ids"])
        exact_ids = set(result["exact_matched_claim_ids"])
        for claim in case.expected_claims:
            kind_expected[claim.kind] += 1
            kind_exact[claim.kind] += int(claim.claim_id in exact_ids)

    precision = _safe_rate(totals["exact_match_count"], totals["proposal_count"])
    recall = _safe_rate(totals["exact_match_count"], totals["expected_claim_count"], empty=0.0)
    exact_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    kind_accuracy = _safe_rate(totals["kind_correct_count"], totals["content_match_count"])
    provenance_accuracy = _safe_rate(
        totals["provenance_correct_count"], totals["content_match_count"]
    )
    summary_coverage = _safe_rate(
        totals["summary_fact_units_covered"], totals["summary_fact_units_total"]
    )
    invalid_rate = _safe_rate(invalid_cases, len(cases), empty=0.0)
    metrics = {
        "case_count": len(cases),
        "expected_claim_count": totals["expected_claim_count"],
        "proposal_count": totals["proposal_count"],
        "exact_match_count": totals["exact_match_count"],
        "content_match_count": totals["content_match_count"],
        "exact_precision": precision,
        "exact_precision_wilson_95": _wilson(totals["exact_match_count"], totals["proposal_count"]),
        "exact_recall": recall,
        "exact_recall_wilson_95": _wilson(
            totals["exact_match_count"], totals["expected_claim_count"]
        ),
        "exact_f1": exact_f1,
        "content_recall": _safe_rate(
            totals["content_match_count"], totals["expected_claim_count"], empty=0.0
        ),
        "kind_accuracy": kind_accuracy,
        "provenance_accuracy": provenance_accuracy,
        "summary_fact_unit_coverage": summary_coverage,
        "summary_critical_units_missing": totals["summary_critical_units_missing"],
        "forbidden_proposal_count": totals["forbidden_proposal_count"],
        "duplicate_proposal_count": totals["duplicate_proposal_count"],
        "ambiguous_content_match_count": totals["ambiguous_content_match_count"],
        "invalid_case_count": invalid_cases,
        "invalid_case_rate": invalid_rate,
        "no_write_violation_count": no_write_violations,
        "source_mutation_violation_count": source_mutation_violations,
        "by_kind": {
            kind: {
                "expected": kind_expected[kind],
                "exact_matches": kind_exact[kind],
                "exact_recall": _safe_rate(kind_exact[kind], kind_expected[kind], empty=0.0),
            }
            for kind in ("fact", "preference", "summary", "event")
        },
        "runtime_seconds": time.perf_counter() - started,
    }
    checks = {
        "case_count": len(cases) >= thresholds.case_count_min,
        "expected_claim_count": totals["expected_claim_count"]
        >= thresholds.expected_claim_count_min,
        "exact_precision": precision >= thresholds.exact_precision_min,
        "exact_recall": recall >= thresholds.exact_recall_min,
        "kind_accuracy": kind_accuracy >= thresholds.kind_accuracy_min,
        "provenance_accuracy": provenance_accuracy >= thresholds.provenance_accuracy_min,
        "summary_fact_unit_coverage": summary_coverage >= thresholds.summary_fact_unit_coverage_min,
        "invalid_case_rate": invalid_rate <= thresholds.invalid_case_rate_max,
        "forbidden_proposal_count": totals["forbidden_proposal_count"]
        <= thresholds.forbidden_proposal_count_max,
        "duplicate_proposal_count": totals["duplicate_proposal_count"]
        <= thresholds.duplicate_proposal_count_max,
        "ambiguous_content_match_count": totals["ambiguous_content_match_count"] == 0,
        "no_write_invariant": no_write_violations == 0,
        "source_preservation_invariant": source_mutation_violations == 0,
    }
    return {
        "schema_version": 1,
        "completed_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "file_name": Path(dataset_path).name,
            "sha256": dataset_digest,
            "description": dataset.description,
            "track": track,
        },
        "extractor": extractor.identity.to_dict(),
        "thresholds": asdict(thresholds),
        "metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
        "scope_of_claim": (
            "single synthetic extraction track; conservative judge-free engineering evidence"
        ),
        "case_results": case_results,
    }


def write_extraction_evaluation_report(
    report: dict[str, Any], destination: str | Path, *, overwrite: bool = False
) -> None:
    secure_write_text(
        Path(destination).expanduser().resolve(),
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        overwrite=overwrite,
    )
