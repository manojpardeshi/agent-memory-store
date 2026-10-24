#!/usr/bin/env python3
"""Check that product re-ranked recall reproduces the frozen held-out candidate exactly.

Compares `MemoryStore.recall(..., rerank=True)` with `make_rerank_arm` from
scripts/locomo_heldout.py (the code that passed LoCoMo look 1) on the tuning pool only: the
LongMemEval-S development 180 with the benchmark header stripped. Free and local.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from llm_memory_store import FastEmbedder, FastEmbedReranker, MemoryStore
from scripts.evaluate_hybrid_recall import copy_store, strip_benchmark_header
from scripts.locomo_heldout import make_rerank_arm
from scripts.memorybench_bridge import RANKED_CONTEXT_POLICY, MemoryBenchBridge
from scripts.run_within_session_expansion_stage1 import resolve_container

CACHE = "demo-artifacts/memorybench/fastembed-cache"


def main() -> int:
    dataset = {
        str(x["question_id"]): x
        for x in json.loads(Path("demo-artifacts/longmemeval_s_cleaned.json").read_text())
    }
    ids = json.loads(
        Path("evaluation/memorybench/longmemeval-kimi-development-v1.json").read_text()
    )["question_ids"]
    embedder = FastEmbedder(cache_dir=CACHE, local_files_only=True)
    reranker = FastEmbedReranker(cache_dir=CACHE, local_files_only=True)
    arm = make_rerank_arm(reranker.score)
    bridge = MemoryBenchBridge(
        Path("demo-artifacts/memorybench/stores"), embedder, context_policy=RANKED_CONTEXT_POLICY
    )
    same = differ = 0
    with tempfile.TemporaryDirectory() as scratch:
        for qid in ids:
            tag = resolve_container(bridge, str(qid))
            copy = Path(scratch) / "store.sqlite3"
            copy_store(bridge._database_path(tag), copy)
            strip_benchmark_header(copy)
            question, scope = dataset[str(qid)]["question"], bridge._scope(tag)
            with MemoryStore(
                copy, embedder, default_turn_ttl_days=None, reranker=reranker
            ) as store:
                frozen = [r.memory.memory_id for r in arm(store, scope, question)]
                product = [
                    r.memory.memory_id
                    for r in store.recall(
                        question, scope, limit=10, relevance_filter=None, rerank=True
                    )
                ]
            same += frozen == product
            differ += frozen != product
            for leftover in Path(scratch).iterdir():
                leftover.unlink()
    print(json.dumps({"questions": same + differ, "identical_top10": same, "different": differ}))
    return 0 if differ == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
