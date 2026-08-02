#!/usr/bin/env python3
"""Build reproducible development-only evidence for paired Kimi discordances."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ARMS = ("baseline", "candidate")
ALLOWED_PATTERNS = {
    "direct-answer-bearing-message-pruned",
    "direct-useful-message-added",
    "salience-or-wording-boundary",
    "unsupported-inference-after-context-perturbation",
}


class DiscordanceAnalysisError(RuntimeError):
    """Raised when diagnostic inputs differ from completed development evidence."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(values: list[float]) -> float:
    if not values:
        raise DiscordanceAnalysisError("cannot aggregate an empty metric")
    return sum(values) / len(values)


def _majority(raw: dict[str, Any], question_id: str, arm: str) -> tuple[int, list[int]]:
    try:
        records = raw["judgments"][question_id][arm]
    except (KeyError, TypeError) as exc:
        raise DiscordanceAnalysisError(f"missing judgments for {question_id}/{arm}") from exc
    if not isinstance(records, dict) or len(records) != 3:
        raise DiscordanceAnalysisError("each paired answer must have three judge votes")
    votes: list[int] = []
    for repeat in sorted(records, key=int):
        try:
            score = int(records[repeat]["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscordanceAnalysisError("judge vote is missing or malformed") from exc
        if score not in (0, 1):
            raise DiscordanceAnalysisError("judge vote must be zero or one")
        votes.append(score)
    return int(sum(votes) >= 2), votes


def _session_id(result: dict[str, Any]) -> str:
    session_id = result.get("metadata", {}).get("session_id")
    if not isinstance(session_id, str) or not session_id:
        raise DiscordanceAnalysisError("retrieved message lacks provenance session id")
    return session_id


def _answer_sessions(question: dict[str, Any]) -> set[str]:
    try:
        haystack = question["haystack_session_ids"]
        answer_ids = question["answer_session_ids"]
        question_id = question["question_id"]
        return {f"{question_id}-session-{haystack.index(answer_id)}" for answer_id in answer_ids}
    except (KeyError, TypeError, ValueError) as exc:
        raise DiscordanceAnalysisError("dataset answer-session mapping is invalid") from exc


def _validate_inputs(
    *,
    raw: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    dataset_path: Path,
    baseline_path: Path,
    candidate_path: Path,
    raw_path: Path,
    contract: dict[str, Any],
    contract_path: Path,
    labels: dict[str, Any],
) -> None:
    if raw.get("status") != "completed" or raw.get("model") != "kimi-k3":
        raise DiscordanceAnalysisError("paired Kimi run must be completed")
    if baseline.get("status") != "completed" or candidate.get("status") != "completed":
        raise DiscordanceAnalysisError("retrieval sources must be completed")
    if not str(contract.get("status", "")).startswith("frozen-before"):
        raise DiscordanceAnalysisError("paired contract was not preregistered")
    if (
        contract.get("selection", {}).get("validation_overlap") != 0
        or contract.get("selection", {}).get("reserve_overlap") != 0
    ):
        raise DiscordanceAnalysisError("development selection overlaps a sealed split")
    if raw.get("split_guard") != {
        "role": "development",
        "sealed": False,
        "sealed_validation_opened": False,
        "sealed_competitor_reserve_opened": False,
    }:
        raise DiscordanceAnalysisError("raw evidence did not preserve the split guard")
    identity = raw.get("input_identity", {})
    expected_hashes = {
        "contract_sha256": _sha256(contract_path),
        "selection_sha256": contract["selection"]["sha256"],
        "development_manifest_sha256": contract["selection"]["development_manifest_sha256"],
        "candidate_replay_sha256": _sha256(candidate_path),
        "baseline_checkpoint_sha256": [_sha256(baseline_path)],
    }
    for key, expected in expected_hashes.items():
        if identity.get(key) != expected:
            raise DiscordanceAnalysisError(f"raw input identity mismatch: {key}")
    if _sha256(dataset_path) != contract["sources"]["dataset_sha256"]:
        raise DiscordanceAnalysisError("dataset hash differs from frozen contract")
    if _sha256(baseline_path) != contract["sources"]["baseline_checkpoint_sha256"]:
        raise DiscordanceAnalysisError("baseline hash differs from frozen contract")
    if _sha256(candidate_path) != contract["sources"]["session_diverse_raw_sha256"]:
        raise DiscordanceAnalysisError("candidate hash differs from frozen contract")
    if (
        labels.get("scope") != "label-aware-non-tuning-diagnostic"
        or labels.get("tuning_authorized") is not False
    ):
        raise DiscordanceAnalysisError("diagnostic labels are not explicitly non-tuning")
    if labels.get("source_raw_sha256") != _sha256(raw_path):
        raise DiscordanceAnalysisError("diagnostic labels identify a different paired run")


def build_evidence(
    *,
    raw: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    dataset: list[dict[str, Any]],
    labels: dict[str, Any],
) -> dict[str, Any]:
    question_ids = raw.get("question_ids")
    if not isinstance(question_ids, list) or not question_ids:
        raise DiscordanceAnalysisError("paired run has no questions")
    if baseline.get("targetQuestionIds") != question_ids:
        raise DiscordanceAnalysisError("baseline question order differs from paired run")
    candidate_questions = candidate.get("questions", {})
    if not set(question_ids).issubset(candidate_questions):
        raise DiscordanceAnalysisError("candidate replay is missing paired questions")
    dataset_by_id = {row.get("question_id"): row for row in dataset}
    if not set(question_ids).issubset(dataset_by_id):
        raise DiscordanceAnalysisError("dataset is missing paired questions")

    discordant_ids = [
        question_id
        for question_id in question_ids
        if _majority(raw, question_id, "baseline")[0] != _majority(raw, question_id, "candidate")[0]
    ]
    label_items = labels.get("items", {})
    if set(label_items) != set(discordant_ids):
        raise DiscordanceAnalysisError("diagnostic labels must cover exactly the discordances")
    if any(item.get("pattern") not in ALLOWED_PATTERNS for item in label_items.values()):
        raise DiscordanceAnalysisError("diagnostic label uses an unsupported pattern")

    rows: list[dict[str, Any]] = []
    for question_id in discordant_ids:
        question = dataset_by_id[question_id]
        answer_sessions = _answer_sessions(question)
        baseline_results = baseline["questions"][question_id]["phases"]["search"]["results"]
        candidate_results = candidate_questions[question_id]["results"]
        baseline_ids = {result["memory_id"] for result in baseline_results}
        candidate_ids = {result["memory_id"] for result in candidate_results}
        removed = [
            (rank, result)
            for rank, result in enumerate(baseline_results, start=1)
            if result["memory_id"] not in candidate_ids
        ]
        added = [result for result in candidate_results if result["memory_id"] not in baseline_ids]
        baseline_sessions = [_session_id(result) for result in baseline_results]
        candidate_sessions = [_session_id(result) for result in candidate_results]
        baseline_score, baseline_votes = _majority(raw, question_id, "baseline")
        candidate_score, candidate_votes = _majority(raw, question_id, "candidate")
        baseline_bytes = int(raw["answers"][question_id]["baseline"]["context_json_bytes"])
        candidate_bytes = int(raw["answers"][question_id]["candidate"]["context_json_bytes"])
        rows.append(
            {
                "question_id": question_id,
                "question_type": question["question_type"],
                "direction": "candidate-win" if candidate_score else "baseline-win",
                "baseline": {"majority_score": baseline_score, "judge_votes": baseline_votes},
                "candidate": {"majority_score": candidate_score, "judge_votes": candidate_votes},
                "distinct_sessions": {
                    "baseline": len(set(baseline_sessions)),
                    "candidate": len(set(candidate_sessions)),
                    "gain": len(set(candidate_sessions)) - len(set(baseline_sessions)),
                },
                "answer_session_messages": {
                    "baseline": sum(sid in answer_sessions for sid in baseline_sessions),
                    "candidate": sum(sid in answer_sessions for sid in candidate_sessions),
                },
                "answer_session_coverage": {
                    "required": len(answer_sessions),
                    "baseline": len(answer_sessions & set(baseline_sessions)),
                    "candidate": len(answer_sessions & set(candidate_sessions)),
                },
                "context_changes": {
                    "removed_messages": len(removed),
                    "added_messages": len(added),
                    "removed_answer_session_messages": sum(
                        _session_id(result) in answer_sessions for _, result in removed
                    ),
                    "added_answer_session_messages": sum(
                        _session_id(result) in answer_sessions for result in added
                    ),
                    "removed_answer_session_baseline_ranks": [
                        rank for rank, result in removed if _session_id(result) in answer_sessions
                    ],
                },
                "context_json_bytes": {
                    "baseline": baseline_bytes,
                    "candidate": candidate_bytes,
                    "ratio": candidate_bytes / baseline_bytes,
                },
                "diagnosis": label_items[question_id],
            }
        )

    directions = Counter(row["direction"] for row in rows)
    categories: dict[str, dict[str, int]] = {}
    for category in sorted({row["question_type"] for row in rows}):
        category_rows = [row for row in rows if row["question_type"] == category]
        categories[category] = {
            "discordant": len(category_rows),
            "baseline_wins": sum(row["direction"] == "baseline-win" for row in category_rows),
            "candidate_wins": sum(row["direction"] == "candidate-win" for row in category_rows),
        }
    baseline_bytes_total = sum(row["context_json_bytes"]["baseline"] for row in rows)
    candidate_bytes_total = sum(row["context_json_bytes"]["candidate"] for row in rows)
    patterns = Counter(row["diagnosis"]["pattern"] for row in rows)
    return {
        "schema_version": 1,
        "status": "completed-development-only-non-tuning-diagnostic",
        "question_count": len(question_ids),
        "discordant_questions": len(rows),
        "baseline_wins": directions["baseline-win"],
        "candidate_wins": directions["candidate-win"],
        "categories": categories,
        "aggregate": {
            "distinct_sessions": {
                "baseline": sum(row["distinct_sessions"]["baseline"] for row in rows),
                "candidate": sum(row["distinct_sessions"]["candidate"] for row in rows),
                "mean_gain": _mean([float(row["distinct_sessions"]["gain"]) for row in rows]),
            },
            "answer_session_messages": {
                "baseline": sum(row["answer_session_messages"]["baseline"] for row in rows),
                "candidate": sum(row["answer_session_messages"]["candidate"] for row in rows),
                "removed": sum(
                    row["context_changes"]["removed_answer_session_messages"] for row in rows
                ),
                "added": sum(
                    row["context_changes"]["added_answer_session_messages"] for row in rows
                ),
            },
            "full_answer_session_coverage": {
                "baseline": sum(
                    row["answer_session_coverage"]["baseline"]
                    == row["answer_session_coverage"]["required"]
                    for row in rows
                ),
                "candidate": sum(
                    row["answer_session_coverage"]["candidate"]
                    == row["answer_session_coverage"]["required"]
                    for row in rows
                ),
            },
            "context_json_bytes": {
                "baseline": baseline_bytes_total,
                "candidate": candidate_bytes_total,
                "ratio": candidate_bytes_total / baseline_bytes_total,
                "questions_with_candidate_reduction": sum(
                    row["context_json_bytes"]["ratio"] < 1 for row in rows
                ),
            },
            "fully_unanimous_pairs": sum(
                len(set(row["baseline"]["judge_votes"])) == 1
                and len(set(row["candidate"]["judge_votes"])) == 1
                for row in rows
            ),
            "causal_patterns": dict(sorted(patterns.items())),
        },
        "questions": rows,
    }


def render_markdown(evidence: dict[str, Any]) -> str:
    aggregate = evidence["aggregate"]
    lines = [
        "# Kimi Paired Session-Diverse Discordance Diagnostic",
        "",
        "Date: 2026-08-02  ",
        "Status: completed development-only, label-aware, non-tuning diagnostic",
        "",
        "## Finding",
        "",
        (
            "The session-diverse policy increased session coverage but frequently removed "
            "the decisive message inside a retained answer session. Session-level recall "
            "therefore masked fact-level evidence loss."
        ),
        "",
        "## Aggregate evidence",
        "",
        (
            f"- Discordant questions: {evidence['discordant_questions']} "
            f"({evidence['baseline_wins']} baseline wins, "
            f"{evidence['candidate_wins']} candidate wins)."
        ),
        (
            f"- Distinct sessions: {aggregate['distinct_sessions']['baseline']} to "
            f"{aggregate['distinct_sessions']['candidate']} "
            f"({aggregate['distinct_sessions']['mean_gain']:.2f} more per question)."
        ),
        (
            "- Labeled answer-session messages: "
            f"{aggregate['answer_session_messages']['baseline']} to "
            f"{aggregate['answer_session_messages']['candidate']}; "
            f"{aggregate['answer_session_messages']['removed']} were removed and "
            f"{aggregate['answer_session_messages']['added']} added."
        ),
        (
            "- Full answer-session coverage: "
            f"{aggregate['full_answer_session_coverage']['baseline']}/"
            f"{evidence['discordant_questions']} baseline and "
            f"{aggregate['full_answer_session_coverage']['candidate']}/"
            f"{evidence['discordant_questions']} candidate."
        ),
        (
            f"- Context bytes: {aggregate['context_json_bytes']['baseline']:,} to "
            f"{aggregate['context_json_bytes']['candidate']:,} "
            f"({aggregate['context_json_bytes']['ratio']:.1%}); candidate was smaller "
            f"on {aggregate['context_json_bytes']['questions_with_candidate_reduction']}/"
            f"{evidence['discordant_questions']} questions."
        ),
        (
            "- Fully unanimous three-vote judge sets in both arms: "
            f"{aggregate['fully_unanimous_pairs']}/"
            f"{evidence['discordant_questions']}."
        ),
        "",
        "## Causal patterns",
        "",
    ]
    for pattern, count in aggregate["causal_patterns"].items():
        lines.append(f"- `{pattern}`: {count}")
    lines.extend(
        [
            "",
            "## Per-question evidence",
            "",
            (
                "| Question | Category | Outcome | Sessions B→C | "
                "Labeled messages B→C | Bytes ratio | Diagnosis |"
            ),
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in evidence["questions"]:
        lines.append(
            f"| `{row['question_id']}` | {row['question_type']} | {row['direction']} | "
            f"{row['distinct_sessions']['baseline']}→{row['distinct_sessions']['candidate']} | "
            f"{row['answer_session_messages']['baseline']}→"
            f"{row['answer_session_messages']['candidate']} | "
            f"{row['context_json_bytes']['ratio']:.3f} | `{row['diagnosis']['pattern']}` |"
        )
    lines.extend(
        [
            "",
            "## Reproducibility and scope",
            "",
            (
                "The analyzer verifies the frozen contract and development source hashes, "
                "derives each arm label by two-of-three judge majority, diffs retrieved "
                "messages by `memory_id`, and maps benchmark answer sessions to checkpoint "
                "session IDs by their position in `haystack_session_ids`. The diagnostic-label "
                "file covers exactly the computed discordant set and explicitly forbids tuning."
            ),
            "",
            (
                "The script accepts no human-audit key, validation manifest, or reserve "
                "manifest input. It does not authorize tuning, opening sealed validation, "
                "shipment, or external performance claims."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--baseline-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-replay", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--diagnostic-labels", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))  # noqa: E731
    raw = load(args.raw)
    baseline = load(args.baseline_checkpoint)
    candidate = load(args.candidate_replay)
    dataset = load(args.dataset)
    contract = load(args.contract)
    labels = load(args.diagnostic_labels)
    _validate_inputs(
        raw=raw,
        baseline=baseline,
        candidate=candidate,
        dataset_path=args.dataset,
        baseline_path=args.baseline_checkpoint,
        candidate_path=args.candidate_replay,
        raw_path=args.raw,
        contract=contract,
        contract_path=args.contract,
        labels=labels,
    )
    evidence = build_evidence(
        raw=raw,
        baseline=baseline,
        candidate=candidate,
        dataset=dataset,
        labels=labels,
    )
    evidence["source_sha256"] = {
        "raw": _sha256(args.raw),
        "baseline_checkpoint": _sha256(args.baseline_checkpoint),
        "candidate_replay": _sha256(args.candidate_replay),
        "dataset": _sha256(args.dataset),
        "contract": _sha256(args.contract),
        "diagnostic_labels": _sha256(args.diagnostic_labels),
    }
    for path in (args.output_json, args.output_md):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(evidence), encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "discordant": len(evidence["questions"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
