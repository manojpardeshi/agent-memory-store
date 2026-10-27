"""Local embedding providers and compatibility fingerprints."""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

_SENTINELS = (
    "memory compatibility sentinel: local tools and durable context",
    "query: preferences about private offline software",
)
_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)


def _normalize(vector: Iterable[float]) -> list[float]:
    values = [float(value) for value in vector]
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


@dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    provider: str
    model_name: str
    model_revision: str
    runtime_version: str
    dimension: int
    normalized: bool
    distance_metric: str
    behavior_fingerprint: str

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "runtime_version": self.runtime_version,
            "dimension": self.dimension,
            "normalized": self.normalized,
            "distance_metric": self.distance_metric,
            "behavior_fingerprint": self.behavior_fingerprint,
        }


@runtime_checkable
class Embedder(Protocol):
    provider: str
    model_name: str
    model_revision: str
    runtime_version: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


# Behaviour fingerprints hash sentinel embeddings to 8 decimals, so harmless numerical drift
# between ONNX Runtime releases changes them. Each group below was measured to be the same model's
# behaviour: cosine similarity 1.000000 on probe texts, at most 2.2e-4 absolute difference per
# component, and identical retrieval_v1/v2/v3 metrics (docs/architecture/benchmarks/
# 2026-10-27-embedding-runtime-equivalence.md). Stores open under any fingerprint in their group.
# Older releases without this table still require an exact match.
EQUIVALENT_FINGERPRINTS: tuple[frozenset[str], ...] = (
    frozenset(
        {
            # BAAI/bge-small-en-v1.5: ONNX Runtime 1.27 (FastEmbed 0.8.0 or 0.9.1; the certified
            # fingerprint) and ONNX Runtime 1.31.1 (FastEmbed 0.9.1)
            "36d7909ee7cda48a3603dddd95e79a27c6a92770ce888a55b77b1811d5e27c87",
            "625b4f337c44fb4b1dc03d07188dc0473bc93bbe3ad3607e0bf39683449fb635",
        }
    ),
)


def fingerprints_equivalent(first: str, second: str) -> bool:
    return first == second or any(
        first in group and second in group for group in EQUIVALENT_FINGERPRINTS
    )


def embedding_identity(embedder: Embedder) -> EmbeddingIdentity:
    digest = hashlib.sha256()
    for vector in (
        embedder.embed_documents([_SENTINELS[0]])[0],
        embedder.embed_query(_SENTINELS[1]),
    ):
        normalized = _normalize(vector)
        digest.update(",".join(f"{value:.8f}" for value in normalized).encode())
    return EmbeddingIdentity(
        provider=embedder.provider,
        model_name=embedder.model_name,
        model_revision=embedder.model_revision,
        runtime_version=embedder.runtime_version,
        dimension=embedder.dimension,
        normalized=True,
        distance_metric="cosine",
        behavior_fingerprint=digest.hexdigest(),
    )


class DeterministicEmbedder:
    """Small offline embedder for tests and development, not production quality."""

    provider = "deterministic-token-hash"
    model_name = "token-hash-v1"
    model_revision = "1"
    runtime_version = "1"

    def __init__(self, dimension: int = 64) -> None:
        if dimension < 8:
            raise ValueError("dimension must be at least 8")
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        tokens = _TOKEN_RE.findall(text.casefold())
        features = tokens + [f"{a}::{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        vector = [0.0] * self.dimension
        for feature in features:
            raw = hashlib.blake2b(feature.encode(), digest_size=16).digest()
            index = int.from_bytes(raw[:8], "little") % self.dimension
            sign = 1.0 if raw[8] & 1 else -1.0
            vector[index] += sign
        return _normalize(vector)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class FastEmbedder:
    """FastEmbed-backed local text embeddings."""

    provider = "fastembed"

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        model_revision: str = "fastembed-catalog",
        cache_dir: str | None = None,
        *,
        local_files_only: bool = False,
    ) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "FastEmbed is not installed. Run 'uv sync' or install llm-memory-store."
            ) from exc

        self.model_name = model_name
        self.model_revision = model_revision
        self.runtime_version = importlib.metadata.version("fastembed")
        supported = {item["model"]: item for item in TextEmbedding.list_supported_models()}
        if model_name not in supported:
            raise ValueError(f"unsupported FastEmbed model: {model_name}")
        self.dimension = int(supported[model_name]["dim"])
        kwargs = {"model_name": model_name}
        if cache_dir:
            kwargs["cache_dir"] = cache_dir
        if local_files_only:
            kwargs["local_files_only"] = True
        self._model = TextEmbedding(**kwargs)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_normalize(vector) for vector in self._model.passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return _normalize(next(iter(self._model.query_embed([text]))))
