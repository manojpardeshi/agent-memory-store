from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import llm_memory_store.embeddings as embeddings
from llm_memory_store import DeterministicEmbedder, MemoryStore, Scope
from llm_memory_store.database import StoreCompatibilityError
from llm_memory_store.embeddings import EQUIVALENT_FINGERPRINTS, fingerprints_equivalent
from llm_memory_store.store import _certified_default_relevance_filter

ORT_127 = "36d7909ee7cda48a3603dddd95e79a27c6a92770ce888a55b77b1811d5e27c87"
ORT_131 = "625b4f337c44fb4b1dc03d07188dc0473bc93bbe3ad3607e0bf39683449fb635"


def test_equivalence_is_reflexive_symmetric_and_group_bound() -> None:
    assert fingerprints_equivalent("abc", "abc")
    assert fingerprints_equivalent(ORT_127, ORT_131) and fingerprints_equivalent(ORT_131, ORT_127)
    assert not fingerprints_equivalent(ORT_127, "0" * 64)
    assert any(ORT_127 in group and ORT_131 in group for group in EQUIVALENT_FINGERPRINTS)


def _identity(fingerprint: str, model: str = "BAAI/bge-small-en-v1.5", runtime: str = "9.9.9"):
    return SimpleNamespace(
        provider="fastembed",
        model_name=model,
        model_revision="fastembed-catalog",
        runtime_version=runtime,
        dimension=384,
        behavior_fingerprint=fingerprint,
    )


def test_certified_filter_follows_behaviour_not_the_runtime_version_string() -> None:
    assert _certified_default_relevance_filter(_identity(ORT_127)) is not None
    assert _certified_default_relevance_filter(_identity(ORT_131)) is not None
    assert _certified_default_relevance_filter(_identity("0" * 64)) is None
    assert _certified_default_relevance_filter(_identity(ORT_131, model="other/model")) is None


def _set_fingerprint(path: Path, value: str) -> None:
    connection = sqlite3.connect(path)
    connection.execute("UPDATE store_manifest SET behavior_fingerprint=?", (value,))
    connection.commit()
    connection.close()


def test_store_opens_under_an_equivalent_fingerprint_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "store.sqlite3"
    embedder = DeterministicEmbedder(64)
    with MemoryStore(path, embedder) as store:
        runtime_fp = store.embedding_identity.behavior_fingerprint
        store.remember("fact", "Opens across equivalent runtimes", Scope.private("me", "t", "e"))
    drifted = "d" * 64
    _set_fingerprint(path, drifted)
    with pytest.raises(StoreCompatibilityError, match="behavior_fingerprint"):
        MemoryStore(path, embedder)
    monkeypatch.setattr(embeddings, "EQUIVALENT_FINGERPRINTS", (frozenset({runtime_fp, drifted}),))
    with MemoryStore(path, embedder) as reopened:
        assert reopened.status()["memories"] == 1
