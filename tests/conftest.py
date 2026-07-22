from __future__ import annotations

from pathlib import Path

import pytest

from llm_memory_store import DeterministicEmbedder, MemoryStore


@pytest.fixture
def embedder() -> DeterministicEmbedder:
    return DeterministicEmbedder(64)


@pytest.fixture
def store(tmp_path: Path, embedder: DeterministicEmbedder):
    instance = MemoryStore(tmp_path / "memory.sqlite3", embedder)
    try:
        yield instance
    finally:
        instance.close()
