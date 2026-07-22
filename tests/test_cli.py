from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.cli import main


def test_cli_vertical_slice(tmp_path, capsys) -> None:
    database = tmp_path / "memory.sqlite3"
    common = ["--db", str(database), "--embedder", "deterministic"]

    main(
        [
            "remember-turn",
            *common,
            "--subject",
            "me",
            "--environment",
            "test",
            "--agent",
            "codex",
            "--role",
            "user",
            "--content",
            "I prefer portable local software",
        ]
    )
    remembered = json.loads(capsys.readouterr().out)

    main(
        [
            "recall",
            *common,
            "--subject",
            "me",
            "--environment",
            "test",
            "--agent",
            "codex",
            "--query",
            "portable local software",
        ]
    )
    recalled = json.loads(capsys.readouterr().out)

    assert recalled["items"][0]["memory"]["memory_id"] == remembered["memory_id"]
    assert recalled["trust_label"] == "untrusted_memory"


def test_cli_broad_export_and_restore_require_confirmation(tmp_path, capsys) -> None:
    database = tmp_path / "memory.sqlite3"
    export = tmp_path / "export.json"

    with pytest.raises(SystemExit):
        main(
            [
                "export",
                "--db",
                str(database),
                "--embedder",
                "deterministic",
                "--destination",
                str(export),
                "--all-scopes",
            ]
        )
    assert "whole-store exports require --yes" in capsys.readouterr().err
    assert not export.exists()

    with pytest.raises(SystemExit):
        main(["restore", "--source", str(tmp_path / "backup.sqlite3"), "--db", str(database)])
    assert "restore requires --yes" in capsys.readouterr().err


def test_cli_relative_relevance_filter_is_explicit_and_may_return_fewer(tmp_path, capsys) -> None:
    database = tmp_path / "filtered.sqlite3"
    common = ["--db", str(database), "--embedder", "deterministic"]
    for content in ("synthetic cobalt editor preference", "unrelated lunar calendar"):
        main(
            [
                "remember",
                *common,
                "--subject",
                "me",
                "--environment",
                "test",
                "--owner",
                "app",
                "--kind",
                "fact",
                "--content",
                content,
            ]
        )
        capsys.readouterr()

    base = [
        "recall",
        *common,
        "--subject",
        "me",
        "--environment",
        "test",
        "--agent",
        "app",
        "--query",
        "synthetic cobalt editor preference",
        "--limit",
        "2",
    ]
    main(base)
    unfiltered = json.loads(capsys.readouterr().out)
    main([*base, "--relevance-filter", "relative:0"])
    filtered = json.loads(capsys.readouterr().out)

    assert len(unfiltered["items"]) == 2
    assert unfiltered["relevance_filter"] is None
    assert unfiltered["relevance_filter_policy"] == "uncertified_off"
    assert len(filtered["items"]) == 1
    assert filtered["relevance_filter"]["maximum_semantic_score_gap"] == 0
    assert filtered["relevance_filter_policy"] == "explicit_override"
    assert "fewer" in filtered["filtering_note"]

    main([*base, "--no-relevance-filter"])
    explicit_off = json.loads(capsys.readouterr().out)
    assert len(explicit_off["items"]) == 2
    assert explicit_off["relevance_filter_policy"] == "explicit_off"


def test_cli_expiry_purge_previews_then_requires_yes_to_execute(tmp_path, capsys) -> None:
    database = tmp_path / "purge.sqlite3"
    common = ["--db", str(database), "--embedder", "deterministic"]
    main(
        [
            "remember",
            *common,
            "--subject",
            "me",
            "--environment",
            "test",
            "--owner",
            "app",
            "--kind",
            "fact",
            "--content",
            "Expired CLI fixture",
            "--expires-at",
            "2000-01-01T00:00:00Z",
        ]
    )
    remembered = json.loads(capsys.readouterr().out)
    command = ["purge-expired", *common, "--as-of", "2001-01-01T00:00:00Z"]

    main(command)
    previewed = json.loads(capsys.readouterr().out)
    assert previewed["executed"] is False
    assert previewed["preview"]["purge_memory_ids"] == [remembered["memory_id"]]

    with pytest.raises(SystemExit):
        main([*command, "--yes"])
    assert "requires --expected-digest" in capsys.readouterr().err

    main([*command, "--yes", "--expected-digest", previewed["preview"]["digest"]])
    executed = json.loads(capsys.readouterr().out)
    assert executed["executed"] is True
    assert executed["receipt"]["deleted_memories"] == 1
    assert executed["receipt"]["verified"] is True


def test_cli_embedding_migration_previews_and_writes_report(tmp_path, capsys) -> None:
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "target.sqlite3"
    report = tmp_path / "migration-report.json"
    dataset = Path(__file__).parents[1] / "evaluation" / "retrieval_v1.json"
    with MemoryStore(source, DeterministicEmbedder(64)) as store:
        store.remember("fact", "CLI migration fixture", Scope.private("me", "test", "app"))
    command = [
        "migrate-embeddings",
        "--source",
        str(source),
        "--destination",
        str(destination),
        "--quality-dataset",
        str(dataset),
        "--report",
        str(report),
        "--source-embedder",
        "deterministic",
        "--source-dimension",
        "64",
        "--target-embedder",
        "deterministic",
        "--target-dimension",
        "96",
    ]

    main(command)
    previewed = json.loads(capsys.readouterr().out)
    assert previewed["executed"] is False
    assert not destination.exists()
    assert not report.exists()

    main(
        [
            *command,
            "--yes",
            "--expected-digest",
            previewed["preview"]["digest"],
            "--accept-quality-regression",
            "--quality-regression-reason",
            "CLI test permits deterministic dimension comparison",
        ]
    )
    completed = json.loads(capsys.readouterr().out)
    assert completed["published"] is True
    assert completed["verified"] is True
    assert destination.exists()
    assert json.loads(report.read_text())["published"] is True


def test_cli_json_import_previews_and_writes_report(tmp_path, capsys) -> None:
    source_database = tmp_path / "source.sqlite3"
    export = tmp_path / "export.json"
    destination = tmp_path / "imported.sqlite3"
    report = tmp_path / "import-report.json"
    with MemoryStore(source_database, DeterministicEmbedder(64)) as store:
        store.remember("fact", "CLI JSON import fixture", Scope.private("me", "test", "app"))
        store.export_json(export, all_scopes=True)
    command = [
        "import-json",
        "--source",
        str(export),
        "--destination",
        str(destination),
        "--report",
        str(report),
        "--embedder",
        "deterministic",
        "--dimension",
        "64",
    ]

    main(command)
    previewed = json.loads(capsys.readouterr().out)
    assert previewed["executed"] is False
    assert not destination.exists()

    main([*command, "--yes", "--expected-digest", previewed["preview"]["digest"]])
    completed = json.loads(capsys.readouterr().out)
    assert completed["published"] is True
    assert completed["verified"] is True
    assert json.loads(report.read_text())["imported_memories"] == 1
    assert report.stat().st_mode & 0o777 == 0o600
