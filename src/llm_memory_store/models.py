"""Public domain models for the memory store."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Literal

MemoryKind = Literal["turn", "fact", "preference", "summary", "event"]
MemoryRole = Literal["user", "assistant", "system", "tool"]
ScopeKind = Literal["private", "shared"]


@dataclass(frozen=True, slots=True)
class RelevanceFilter:
    """Explicit opt-in filtering applied after retrieval ranking."""

    strategy: Literal["relative_semantic_gap"]
    maximum_semantic_score_gap: float

    def __post_init__(self) -> None:
        if self.strategy != "relative_semantic_gap":
            raise ValueError("unsupported relevance filter strategy")
        gap = self.maximum_semantic_score_gap
        if not isinstance(gap, (int, float)) or isinstance(gap, bool):
            raise ValueError("maximum_semantic_score_gap must be numeric")
        if not math.isfinite(gap) or not 0 <= gap <= 1:
            raise ValueError("maximum_semantic_score_gap must be between 0 and 1")
        object.__setattr__(self, "maximum_semantic_score_gap", float(gap))

    @classmethod
    def relative(cls, maximum_semantic_score_gap: float = 0.20) -> RelevanceFilter:
        return cls("relative_semantic_gap", maximum_semantic_score_gap)

    @classmethod
    def parse(cls, value: str) -> RelevanceFilter:
        prefix = "relative:"
        if not value.startswith(prefix):
            raise ValueError("relevance filter must use relative:GAP, for example relative:0.20")
        try:
            gap = float(value.removeprefix(prefix))
        except ValueError as exc:
            raise ValueError("relative relevance gap must be numeric") from exc
        return cls.relative(gap)

    def to_dict(self) -> dict[str, str | float]:
        return {
            "strategy": self.strategy,
            "maximum_semantic_score_gap": self.maximum_semantic_score_gap,
        }


def _required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) > 256:
        raise ValueError(f"{field} must be at most 256 characters")
    return cleaned


@dataclass(frozen=True, slots=True)
class Scope:
    """A concrete, non-hierarchical memory scope."""

    kind: ScopeKind
    subject: str
    environment: str
    owner: str

    def __post_init__(self) -> None:
        if self.kind not in ("private", "shared"):
            raise ValueError("scope kind must be 'private' or 'shared'")
        object.__setattr__(self, "subject", _required(self.subject, "subject"))
        object.__setattr__(self, "environment", _required(self.environment, "environment"))
        object.__setattr__(self, "owner", _required(self.owner, "owner"))

    @classmethod
    def private(cls, subject: str, environment: str, agent_or_app: str) -> Scope:
        return cls("private", subject, environment, agent_or_app)

    @classmethod
    def shared(cls, subject: str, environment: str, pool: str) -> Scope:
        return cls("shared", subject, environment, pool)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    lineage_id: str
    version: int
    scope: Scope
    kind: MemoryKind
    role: str | None
    content: str
    status: str
    generation: int
    embedding_status: str
    embedding_error: str | None
    metadata: dict[str, Any]
    created_at: str
    expires_at: str | None
    supersedes_memory_id: str | None
    source_memory_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_memory_ids"] = list(self.source_memory_ids)
        return value


@dataclass(frozen=True, slots=True)
class RecallResult:
    memory: MemoryRecord
    score: float
    semantic_score: float
    recency_score: float
    distance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "trust_label": "untrusted_memory",
            "memory": self.memory.to_dict(),
            "score": self.score,
            "semantic_score": self.semantic_score,
            "recency_score": self.recency_score,
            "distance": self.distance,
        }


@dataclass(frozen=True, slots=True)
class DeletePreview:
    requested_memory_id: str | None
    requested_scope: Scope | None
    memory_ids: tuple[str, ...]
    lineage_ids: tuple[str, ...]
    kinds: dict[str, int]

    @property
    def count(self) -> int:
        return len(self.memory_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_memory_id": self.requested_memory_id,
            "requested_scope": self.requested_scope.to_dict() if self.requested_scope else None,
            "memory_ids": list(self.memory_ids),
            "lineage_ids": list(self.lineage_ids),
            "kinds": self.kinds,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class DeleteReceipt:
    preview: DeletePreview
    deleted_memories: int
    deleted_vectors: int
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview": self.preview.to_dict(),
            "deleted_memories": self.deleted_memories,
            "deleted_vectors": self.deleted_vectors,
            "verified": self.verified,
        }


@dataclass(frozen=True, slots=True)
class ExpiryPurgePreview:
    """A stable description of one cutoff-based expiry purge candidate set."""

    cutoff: str
    expired_memory_ids: tuple[str, ...]
    purge_memory_ids: tuple[str, ...]
    blocked_memory_ids: tuple[str, ...]
    blocking_memory_ids: tuple[str, ...]
    lineage_ids: tuple[str, ...]
    kinds: dict[str, int]
    digest: str

    @property
    def expired_count(self) -> int:
        return len(self.expired_memory_ids)

    @property
    def purge_count(self) -> int:
        return len(self.purge_memory_ids)

    @property
    def blocked_count(self) -> int:
        return len(self.blocked_memory_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cutoff": self.cutoff,
            "expired_memory_ids": list(self.expired_memory_ids),
            "purge_memory_ids": list(self.purge_memory_ids),
            "blocked_memory_ids": list(self.blocked_memory_ids),
            "blocking_memory_ids": list(self.blocking_memory_ids),
            "lineage_ids": list(self.lineage_ids),
            "kinds": self.kinds,
            "expired_count": self.expired_count,
            "purge_count": self.purge_count,
            "blocked_count": self.blocked_count,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class ExpiryPurgeReceipt:
    preview: ExpiryPurgePreview
    deleted_memories: int
    deleted_vectors: int
    deleted_provenance_edges: int
    committed_at: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "preview": self.preview.to_dict(),
            "deleted_memories": self.deleted_memories,
            "deleted_vectors": self.deleted_vectors,
            "deleted_provenance_edges": self.deleted_provenance_edges,
            "committed_at": self.committed_at,
            "verified": self.verified,
        }
