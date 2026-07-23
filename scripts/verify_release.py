#!/usr/bin/env python3
"""Run the reproducible local release gate and write ignored verification artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DASHBOARD = ROOT / "demo" / "dashboard"


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("+", shlex.join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_clean_main() -> str:
    status = run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        capture=True,
    ).stdout
    if status:
        raise SystemExit("Release verification requires a clean worktree.")

    branch = run(["git", "branch", "--show-current"], capture=True).stdout.strip()
    if branch != "main":
        raise SystemExit(f"Release verification requires branch main, found {branch!r}.")

    return run(["git", "rev-parse", "HEAD"], capture=True).stdout.strip()


def project_identity() -> tuple[str, str]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return str(project["name"]), str(project["version"])


def artifact_paths(name: str, version: str) -> list[Path]:
    normalized = name.replace("-", "_").replace(".", "_")
    artifacts = [
        DIST / f"{normalized}-{version}-py3-none-any.whl",
        DIST / f"{normalized}-{version}.tar.gz",
    ]
    missing = [str(path) for path in artifacts if not path.is_file()]
    if missing:
        raise SystemExit(f"Expected build artifacts are missing: {', '.join(missing)}")
    return artifacts


def artifact_records(paths: list[Path]) -> list[dict[str, str | int]]:
    return [
        {
            "path": str(path.relative_to(ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in paths
    ]


def run_gitleaks(binary: Path) -> None:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise SystemExit(f"Gitleaks executable is unavailable: {binary}")

    with tempfile.TemporaryDirectory(prefix="agent-memory-release-scan-") as temporary:
        scan_root = Path(temporary)
        archive = scan_root / "tree.tar"
        tree = scan_root / "tree"
        tree.mkdir()
        run(["git", "archive", "--format=tar", "--output", str(archive), "HEAD"])
        with tarfile.open(archive) as handle:
            handle.extractall(tree, filter="data")

        common = [
            str(binary),
            "--config",
            str(ROOT / ".gitleaks.toml"),
            "--max-archive-depth",
            "2",
            "--redact=100",
            "--report-format",
            "json",
        ]
        run(
            [
                common[0],
                "dir",
                *common[1:],
                "--report-path",
                str(scan_root / "tree.json"),
                str(tree),
            ]
        )
        run(
            [
                common[0],
                "git",
                *common[1:],
                "--log-opts=--all --full-history",
                "--report-path",
                str(scan_root / "history.json"),
                str(ROOT),
            ]
        )
        run(
            [
                common[0],
                "dir",
                *common[1:],
                "--report-path",
                str(scan_root / "artifacts.json"),
                str(DIST),
            ]
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-date-epoch",
        default=os.environ.get("SOURCE_DATE_EPOCH"),
        help="Required UTC Unix timestamp used for both reproducible builds.",
    )
    parser.add_argument(
        "--gitleaks-bin",
        type=Path,
        default=Path(found) if (found := shutil.which("gitleaks")) else None,
        help="Verified Gitleaks executable. Defaults to gitleaks on PATH.",
    )
    arguments = parser.parse_args()

    if arguments.source_date_epoch is None or not arguments.source_date_epoch.isdigit():
        raise SystemExit("--source-date-epoch must be a non-negative Unix timestamp.")
    if arguments.gitleaks_bin is None:
        raise SystemExit("--gitleaks-bin is required when gitleaks is not on PATH.")

    commit = require_clean_main()
    name, version = project_identity()
    build_env = os.environ.copy()
    build_env["SOURCE_DATE_EPOCH"] = arguments.source_date_epoch

    run(["git", "diff", "--check"])
    run(["uv", "lock", "--check"])
    run(["uv", "run", "pytest"])
    run(["uv", "run", "ruff", "check", "."])
    run(["npm", "ci"], cwd=DASHBOARD)
    run(["npm", "audit", "--audit-level=high"], cwd=DASHBOARD)
    run(["npm", "run", "lint"], cwd=DASHBOARD)
    run(["npm", "test"], cwd=DASHBOARD)

    with tempfile.TemporaryDirectory(prefix="agent-memory-audit-") as temporary:
        requirements = Path(temporary) / "requirements.txt"
        run(
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ]
        )
        run(
            [
                "uvx",
                "--from",
                "pip-audit==2.10.1",
                "pip-audit",
                "--requirement",
                str(requirements),
            ]
        )

    run(["uv", "build", "--clear"], env=build_env)
    first_build = artifact_records(artifact_paths(name, version))
    run(["uv", "build", "--clear"], env=build_env)
    paths = artifact_paths(name, version)
    second_build = artifact_records(paths)
    if first_build != second_build:
        raise SystemExit("The two builds produced different artifacts.")

    run(
        [
            "uvx",
            "--from",
            "twine==6.2.0",
            "twine",
            "check",
            *(str(path) for path in paths),
        ]
    )
    run_gitleaks(arguments.gitleaks_bin.resolve())

    checksum_lines = [f"{record['sha256']}  {record['path']}" for record in second_build]
    (DIST / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    verification = {
        "schema_version": 1,
        "project": name,
        "version": version,
        "commit": commit,
        "source_date_epoch": int(arguments.source_date_epoch),
        "artifacts": second_build,
        "gates": {
            "clean_main": "pass",
            "lock": "pass",
            "pytest": "pass",
            "ruff": "pass",
            "dashboard": "pass",
            "npm_audit": "pass",
            "pip_audit": "pass",
            "reproducible_build": "pass",
            "twine": "pass",
            "gitleaks_tree_history_artifacts": "pass",
        },
    }
    (DIST / "release-verification.json").write_text(
        json.dumps(verification, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verification, indent=2))


if __name__ == "__main__":
    main()
