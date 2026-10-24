"""Optional local cross-encoder re-ranking for recall.

Re-ranking re-scores the first candidates of vector recall with a cross-encoder, which reads the
query and each memory together, and reorders them. It only reorders memories recall already
returned, so it cannot introduce a memory from another scope. The configuration below was tuned on
LongMemEval-S development questions and confirmed on the LoCoMo-10 held-out set
(docs/architecture/benchmarks/2026-10-24-rerank-locomo-heldout.md); it costs about 150 ms per
recall on a laptop CPU, which is why it is opt-in.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any, Protocol

DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
# Re-scored on each memory's first 512 characters: nearly all of the full-text gain at a fifth
# of the cost on long conversational turns.
RERANK_INPUT_CHARS = 512
# Exactly the first 20 vector candidates are re-scored, whatever the limit: the validated depth.
# Deeper re-ranking (30 or 50) raised distractor leakage past the retrieval_v3 gate in tuning.
RERANK_DEPTH = 20
# Vector recall depth the re-scored candidates are drawn from (the validated configuration).
RERANK_POOL = 50


class Reranker(Protocol):
    model_name: str

    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


def rerank_order(scores: Sequence[float], limit: int) -> list[int]:
    """Candidate indices by descending score, ties keeping candidate order, at most ``limit``.

    Modelled and proved in proofs/RerankOrder.v. NaN scores sort last.
    """

    def key(index: int) -> tuple[float, int]:
        value = scores[index]
        return (math.inf if math.isnan(value) else -value, index)

    return sorted(range(len(scores)), key=key)[:limit]


class FastEmbedReranker:
    """FastEmbed cross-encoder, loaded on first use. The default model is about 92 MB."""

    def __init__(
        self,
        model_name: str = DEFAULT_RERANK_MODEL,
        cache_dir: str | None = None,
        *,
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        self._cache_dir = cache_dir
        self._local_files_only = local_files_only
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "FastEmbed is not installed. Run 'uv sync' or install llm-memory-store."
                ) from exc
            kwargs: dict[str, Any] = {"model_name": self.model_name}
            if self._cache_dir:
                kwargs["cache_dir"] = self._cache_dir
            if self._local_files_only:
                kwargs["local_files_only"] = True
            self._model = TextCrossEncoder(**kwargs)
        return self._model

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        return [float(value) for value in self._load().rerank(query, list(documents))]


_TOKEN = re.compile(r"[^\W_]+")


class DeterministicReranker:
    """Offline word-overlap scorer for tests and development, not production quality."""

    model_name = "deterministic-word-overlap"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        terms = set(_TOKEN.findall(query.casefold()))
        return [
            len(terms & set(_TOKEN.findall(doc.casefold()))) / (len(terms) or 1)
            for doc in documents
        ]
