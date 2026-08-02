from __future__ import annotations

import json
from pathlib import Path

from scripts.run_session_diverse_development import _context_bytes, _write_atomic


def test_context_bytes_matches_formatted_raw_json() -> None:
    results = [{"memory": "snowman ☃", "metadata": {"session_id": "s1"}}]

    assert _context_bytes(results) == len(
        json.dumps(results, indent=2, ensure_ascii=False).encode("utf-8")
    )


def test_atomic_writer_replaces_complete_json(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    _write_atomic(output, {"status": "running"})
    _write_atomic(output, {"status": "completed"})

    assert json.loads(output.read_text()) == {"status": "completed"}
    assert not (tmp_path / ".report.json.tmp").exists()
