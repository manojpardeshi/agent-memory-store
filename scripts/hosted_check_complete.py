#!/usr/bin/env python3
"""Exit non-zero unless every manifest question reached a completed search in a run.

MemoryBench silently drops question ids it cannot find and still reports success, and a
run can exit 0 with questions unsearched. The batch driver calls this after each batch so
a partial run is never mistaken for a finished one.

usage: hosted_check_complete.py RUN_ID MANIFEST   (run from the MemoryBench root)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    run_id, manifest = sys.argv[1], sys.argv[2]
    wanted = json.loads(Path(manifest).read_text())["question_ids"]
    checkpoint = json.loads(Path(f"data/runs/{run_id}/checkpoint.json").read_text())
    questions = checkpoint.get("questions", {})
    missing = [
        q for q in wanted
        if q not in questions
        or questions[q].get("phases", {}).get("search", {}).get("status") != "completed"
    ]
    print(f"completeness {run_id}: {len(wanted) - len(missing)}/{len(wanted)} searched")
    if missing:
        print(f"incomplete: {missing[:10]}{' ...' if len(missing) > 10 else ''}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
