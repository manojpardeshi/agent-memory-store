#!/usr/bin/env python3
"""Build a self-contained Kaggle kernel (script + metadata) for a list of questions.

usage: build_kernel.py SLUG RUN_PREFIX QID [QID ...]
Writes kaggle/kernel-<SLUG>/run.py and kernel-metadata.json (private, GPU, internet on).
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMBED = [
    "patches/memorybench-local.patch",
    "patches/llm-memory-store-provider/index.ts",
    "scripts/hosted-search-manifest.ts",
]
USER = "manojpardeshi111"


def main() -> int:
    slug, run_prefix, *questions = sys.argv[1:]
    if not questions:
        raise SystemExit(__doc__)
    files = {path: base64.b64encode((ROOT / path).read_bytes()).decode() for path in EMBED}
    template = (ROOT / "kaggle/runner_template.py").read_text()
    script = (
        template.replace("__QUESTIONS__", json.dumps(questions))
        .replace("__RUN_PREFIX__", json.dumps(run_prefix))
        .replace("__FILES__", json.dumps(files))
    )
    out = ROOT / "kaggle" / f"kernel-{slug}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.py").write_text(script)
    metadata = {
        "id": f"{USER}/{slug}",
        "title": slug,
        "code_file": "run.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (out / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
