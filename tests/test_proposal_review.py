from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from llm_memory_store import (
    DeterministicEmbedder,
    DeterministicRuleExtractor,
    MemoryStore,
    ProposalValidationError,
    Scope,
    accept_proposals,
    create_proposal_bundle,
    review_proposals,
    write_proposal_bundle,
)
from llm_memory_store.cli import main
from llm_memory_store.extraction import ExtractorIdentity
from llm_memory_store.models import MemoryRecord


class FixedExtractor:
    identity = ExtractorIdentity("test", "proposal-review", "1")

    def __init__(self, proposals: list[dict[str, object]]) -> None:
        self.proposals = proposals

    def extract(self, sources: Sequence[MemoryRecord]) -> object:
        source_id = sources[0].memory_id
        return {
            "proposals": [
                {**proposal, "source_memory_ids": [source_id]} for proposal in self.proposals
            ]
        }


class SplitSourceDuplicateExtractor:
    identity = ExtractorIdentity("test", "split-source-duplicates", "1")

    def extract(self, sources: Sequence[MemoryRecord]) -> object:
        return {
            "proposals": [
                {
                    "kind": "fact",
                    "content": "The same exact proposal",
                    "source_memory_ids": [source.memory_id],
                }
                for source in sources
            ]
        }


def _single_bundle(store: Any):
    scope = Scope.private("me", "proposal-review", "app")
    source = store.remember_turn("Fact: The ultraviolet release lane is selected.", "user", scope)
    bundle = create_proposal_bundle(store, [source.memory_id], scope, DeterministicRuleExtractor())
    return scope, source, bundle


def test_review_is_read_only_and_content_is_opt_in(store: Any) -> None:
    _, source, bundle = _single_bundle(store)
    proposal = bundle.proposals[0]
    before_changes = store.connection.total_changes
    before_rows = store.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    report = review_proposals(store, bundle)

    assert report.read_only is True
    assert report.proposals[0].primary_status == "new"
    assert report.proposals[0].acceptance_ready is True
    assert report.counts["acceptance_ready_count"] == 1
    assert store.connection.total_changes == before_changes
    assert store.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == before_rows
    default_json = json.dumps(report.to_dict())
    assert proposal.content not in default_json
    assert source.content not in default_json

    revealed = review_proposals(
        store, bundle, show_proposal_content=True, show_source_content=True
    ).to_dict()
    assert revealed["proposals"][0]["content"] == proposal.content
    assert revealed["sources"][0]["content"] == source.content
    assert store.connection.total_changes == before_changes


def test_exact_duplicate_and_kind_collision_are_narrow_deterministic_indicators(
    store: Any,
) -> None:
    scope = Scope.private("me", "proposal-review", "app")
    source = store.remember_turn("Two review candidates", "user", scope)
    bundle = create_proposal_bundle(
        store,
        [source.memory_id],
        scope,
        FixedExtractor(
            [
                {"kind": "fact", "content": "Alpha fact"},
                {"kind": "fact", "content": "Beta claim"},
            ]
        ),
    )
    duplicate = store.remember("fact", "Alpha   fact", scope)
    collision = store.remember("preference", "Beta claim", scope)

    report = review_proposals(store, bundle, show_proposal_content=True)
    by_content = {item.content: item for item in report.proposals}

    assert by_content["Alpha fact"].primary_status == "exact_duplicate"
    assert by_content["Alpha fact"].exact_duplicate_memory_ids == (duplicate.memory_id,)
    assert by_content["Alpha fact"].acceptance_ready is True
    assert by_content["Beta claim"].primary_status == "kind_collision"
    assert by_content["Beta claim"].kind_collision_memory_ids == (collision.memory_id,)
    assert by_content["Beta claim"].acceptance_ready is True


def test_exact_duplicates_inside_one_bundle_are_visible_before_acceptance(store: Any) -> None:
    scope = Scope.private("me", "proposal-review", "app")
    first_source = store.remember_turn("First exact source", "user", scope)
    second_source = store.remember_turn("Second exact source", "user", scope)
    bundle = create_proposal_bundle(
        store,
        [first_source.memory_id, second_source.memory_id],
        scope,
        SplitSourceDuplicateExtractor(),
    )

    report = review_proposals(store, bundle)

    assert len(report.proposals) == 2
    for proposal in report.proposals:
        assert proposal.primary_status == "exact_duplicate"
        assert len(proposal.exact_duplicate_proposal_ids) == 1
        assert proposal.exact_duplicate_proposal_ids[0] != proposal.proposal_id
        assert proposal.acceptance_ready is True


def test_kind_collisions_inside_one_bundle_are_visible_before_acceptance(store: Any) -> None:
    scope = Scope.private("me", "proposal-review", "app")
    source = store.remember_turn("Ambiguous typed source", "user", scope)
    bundle = create_proposal_bundle(
        store,
        [source.memory_id],
        scope,
        FixedExtractor(
            [
                {"kind": "fact", "content": "Identical visible content"},
                {"kind": "preference", "content": "Identical visible content"},
            ]
        ),
    )

    report = review_proposals(store, bundle)

    assert len(report.proposals) == 2
    for proposal in report.proposals:
        assert proposal.primary_status == "kind_collision"
        assert len(proposal.kind_collision_proposal_ids) == 1
        assert proposal.kind_collision_proposal_ids[0] != proposal.proposal_id
        assert proposal.acceptance_ready is True


def test_read_only_store_enforces_review_non_mutation_at_sqlite_boundary(store: Any) -> None:
    scope, _, bundle = _single_bundle(store)
    with MemoryStore(store.path, DeterministicEmbedder(64), read_only=True) as read_only_store:
        assert read_only_store.connection.execute("PRAGMA query_only").fetchone()[0] == 1
        report = review_proposals(read_only_store, bundle)
        assert report.proposals[0].primary_status == "new"
        with pytest.raises(sqlite3.OperationalError, match="readonly|read-only"):
            read_only_store.remember("fact", "Forbidden write", scope)


@pytest.mark.parametrize(
    "mutation, expected_status",
    [
        ("missing", "missing"),
        ("superseded", "superseded"),
        ("expired", "expired"),
        ("shape_changed", "shape_changed"),
        ("content_changed", "content_changed"),
    ],
)
def test_source_lifecycle_and_tamper_states_block_dependent_proposals(
    store: Any, mutation: str, expected_status: str
) -> None:
    _, source, bundle = _single_bundle(store)
    if mutation == "missing":
        store.forget(source.memory_id)
    elif mutation == "superseded":
        store.correct(source.memory_id, "Fact: The teal release lane is selected.")
    elif mutation == "expired":
        store.connection.execute(
            "UPDATE memories SET expires_at=? WHERE memory_id=?",
            ((datetime.now(UTC) - timedelta(days=1)).isoformat(), source.memory_id),
        )
    elif mutation == "shape_changed":
        store.connection.execute(
            "UPDATE memories SET kind='fact', role=NULL WHERE memory_id=?",
            (source.memory_id,),
        )
    elif mutation == "content_changed":
        changed = "Fact: Directly changed content"
        store.connection.execute(
            "UPDATE memories SET content=?, content_hash=? WHERE memory_id=?",
            (changed, hashlib.sha256(changed.encode()).hexdigest(), source.memory_id),
        )

    before = store.connection.total_changes
    report = review_proposals(store, bundle)

    assert report.sources[0].status == expected_status
    assert report.proposals[0].primary_status == "blocked_source"
    assert report.proposals[0].acceptance_ready is False
    assert store.connection.total_changes == before
    if mutation == "superseded":
        assert report.sources[0].replacement_memory_id is not None


def test_replay_reports_active_then_superseded_acceptance(store: Any) -> None:
    _, _, bundle = _single_bundle(store)
    proposal = bundle.proposals[0]
    receipt = accept_proposals(
        store, bundle, [proposal.proposal_id], expected_digest=bundle.bundle_digest
    )

    active = review_proposals(store, bundle).proposals[0]
    assert active.primary_status == "accepted_replay"
    assert active.replay_memory_id == receipt.accepted[0].memory_id
    assert active.acceptance_ready is True

    store.correct(receipt.accepted[0].memory_id, "A corrected durable fact")
    superseded = review_proposals(store, bundle).proposals[0]
    assert superseded.primary_status == "replayed_superseded"
    assert superseded.acceptance_ready is False
    with pytest.raises(ProposalValidationError, match="replayed_superseded"):
        accept_proposals(
            store, bundle, [proposal.proposal_id], expected_digest=bundle.bundle_digest
        )


def test_replay_of_expired_accepted_memory_is_not_acceptance_ready(store: Any) -> None:
    _, _, bundle = _single_bundle(store)
    proposal = bundle.proposals[0]
    receipt = accept_proposals(
        store, bundle, [proposal.proposal_id], expected_digest=bundle.bundle_digest
    )
    store.connection.execute(
        "UPDATE memories SET expires_at=? WHERE memory_id=?",
        (
            (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            receipt.accepted[0].memory_id,
        ),
    )

    replay = review_proposals(store, bundle).proposals[0]

    assert replay.primary_status == "replayed_expired"
    assert replay.acceptance_ready is False


def test_cli_review_requires_existing_store_and_writes_owner_only_report(
    tmp_path: Path, store: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    _, source, bundle = _single_bundle(store)
    artifact = tmp_path / "proposal.json"
    output = tmp_path / "review.json"
    write_proposal_bundle(bundle, artifact)
    runtime = ["--db", str(store.path), "--embedder", "deterministic"]

    main(["review-proposals", *runtime, "--proposal-file", str(artifact)])
    hidden = capsys.readouterr().out
    hidden_value = json.loads(hidden)
    assert hidden_value["report"]["read_only"] is True
    assert bundle.proposals[0].content not in hidden
    assert source.content not in hidden
    assert str(store.path) not in hidden
    assert str(artifact) not in hidden

    main(
        [
            "review-proposals",
            *runtime,
            "--proposal-file",
            str(artifact),
            "--output",
            str(output),
            "--show-proposal-content",
        ]
    )
    capsys.readouterr()
    written = json.loads(output.read_text())
    assert output.stat().st_mode & 0o777 == 0o600
    assert written["proposals"][0]["content"] == bundle.proposals[0].content
    assert "content" not in written["sources"][0]

    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(SystemExit):
        main(
            [
                "review-proposals",
                "--db",
                str(missing),
                "--embedder",
                "deterministic",
                "--proposal-file",
                str(artifact),
            ]
        )
    assert "existing --db" in capsys.readouterr().err
    assert not missing.exists()
