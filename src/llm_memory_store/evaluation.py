"""Versioned, synthetic retrieval-quality evaluation support."""

from __future__ import annotations

import hashlib
import json
import platform
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .database import secure_write_text
from .embeddings import Embedder
from .models import MemoryKind, MemoryRole, RelevanceFilter, Scope
from .store import MemoryStore


class EvaluationDatasetError(ValueError):
    """Raised when an evaluation dataset violates the versioned contract."""


@dataclass(frozen=True, slots=True)
class EvaluationMemory:
    fixture_id: str
    kind: MemoryKind
    content: str
    scope: Scope
    role: MemoryRole | None = None


@dataclass(frozen=True, slots=True)
class EvaluationQuery:
    query_id: str
    query: str
    private_scope: Scope
    shared_pools: tuple[str, ...]
    expected_fixture_ids: tuple[str, ...]
    distractor_fixture_ids: tuple[str, ...]
    inaccessible_fixture_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvaluationThresholds:
    query_count_min: int
    memory_kind_count_min: int
    recall_at_k_min: float
    mrr_min: float
    distractor_leak_rate_max: float
    scope_violation_count_max: int
    runtime_seconds_max: float


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    schema_version: int
    dataset_id: str
    description: str
    distractor_policy: str
    top_k: int
    memories: tuple[EvaluationMemory, ...]
    queries: tuple[EvaluationQuery, ...]
    thresholds: EvaluationThresholds


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDatasetError(f"{field} must be a non-empty string")
    return value.strip()


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise EvaluationDatasetError(f"{field} must be a non-empty list")
    values = tuple(_required_string(item, field) for item in value)
    if len(set(values)) != len(values):
        raise EvaluationDatasetError(f"{field} must not contain duplicates")
    return values


def _scope(value: Any, field: str) -> Scope:
    if not isinstance(value, dict):
        raise EvaluationDatasetError(f"{field} must be an object")
    try:
        return Scope(
            _required_string(value.get("kind"), f"{field}.kind"),  # type: ignore[arg-type]
            _required_string(value.get("subject"), f"{field}.subject"),
            _required_string(value.get("environment"), f"{field}.environment"),
            _required_string(value.get("owner"), f"{field}.owner"),
        )
    except ValueError as exc:
        raise EvaluationDatasetError(str(exc)) from exc


def _number(value: Any, field: str, *, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise EvaluationDatasetError(f"{field} must be numeric")
    result = float(value)
    if not minimum <= result <= maximum:
        raise EvaluationDatasetError(f"{field} must be between {minimum} and {maximum}")
    return result


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise EvaluationDatasetError(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise EvaluationDatasetError(f"{field} must be between {minimum} and {maximum}")
    return value


def _is_accessible(memory: EvaluationMemory, query: EvaluationQuery) -> bool:
    if memory.scope == query.private_scope:
        return True
    return (
        memory.scope.kind == "shared"
        and memory.scope.subject == query.private_scope.subject
        and memory.scope.environment == query.private_scope.environment
        and memory.scope.owner in query.shared_pools
    )


def load_evaluation_dataset(path: str | Path) -> tuple[EvaluationDataset, str]:
    """Load and validate a schema-v1 synthetic retrieval dataset."""

    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvaluationDatasetError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvaluationDatasetError("dataset root must be an object")
    if value.get("schema_version") != 1:
        raise EvaluationDatasetError("unsupported evaluation schema_version")

    raw_memories = value.get("memories")
    raw_queries = value.get("queries")
    raw_thresholds = value.get("thresholds")
    if not isinstance(raw_memories, list) or not raw_memories:
        raise EvaluationDatasetError("memories must be a non-empty list")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise EvaluationDatasetError("queries must be a non-empty list")
    if not isinstance(raw_thresholds, dict):
        raise EvaluationDatasetError("thresholds must be an object")

    memories: list[EvaluationMemory] = []
    for index, item in enumerate(raw_memories):
        if not isinstance(item, dict):
            raise EvaluationDatasetError(f"memories[{index}] must be an object")
        kind = _required_string(item.get("kind"), f"memories[{index}].kind")
        if kind not in {"turn", "fact", "preference", "summary", "event"}:
            raise EvaluationDatasetError(f"memories[{index}].kind is unsupported")
        role_value = item.get("role")
        role = None if role_value is None else _required_string(role_value, "role")
        if kind == "turn" and role not in {"user", "assistant", "system", "tool"}:
            raise EvaluationDatasetError(f"memories[{index}] turn requires a valid role")
        if kind != "turn" and role is not None:
            raise EvaluationDatasetError(f"memories[{index}] role is only valid for turns")
        memories.append(
            EvaluationMemory(
                fixture_id=_required_string(
                    item.get("fixture_id"), f"memories[{index}].fixture_id"
                ),
                kind=kind,  # type: ignore[arg-type]
                content=_required_string(item.get("content"), f"memories[{index}].content"),
                scope=_scope(item.get("scope"), f"memories[{index}].scope"),
                role=role,  # type: ignore[arg-type]
            )
        )
    memory_by_id = {memory.fixture_id: memory for memory in memories}
    if len(memory_by_id) != len(memories):
        raise EvaluationDatasetError("memory fixture_id values must be unique")

    queries: list[EvaluationQuery] = []
    for index, item in enumerate(raw_queries):
        if not isinstance(item, dict):
            raise EvaluationDatasetError(f"queries[{index}] must be an object")
        shared_pools_value = item.get("shared_pools", [])
        if not isinstance(shared_pools_value, list):
            raise EvaluationDatasetError(f"queries[{index}].shared_pools must be a list")
        shared_pools = tuple(
            _required_string(pool, f"queries[{index}].shared_pools") for pool in shared_pools_value
        )
        if len(set(shared_pools)) != len(shared_pools):
            raise EvaluationDatasetError(
                f"queries[{index}].shared_pools must not contain duplicates"
            )
        query = EvaluationQuery(
            query_id=_required_string(item.get("query_id"), f"queries[{index}].query_id"),
            query=_required_string(item.get("query"), f"queries[{index}].query"),
            private_scope=_scope(item.get("private_scope"), f"queries[{index}].private_scope"),
            shared_pools=shared_pools,
            expected_fixture_ids=_string_tuple(
                item.get("expected_fixture_ids"),
                f"queries[{index}].expected_fixture_ids",
            ),
            distractor_fixture_ids=_string_tuple(
                item.get("distractor_fixture_ids"),
                f"queries[{index}].distractor_fixture_ids",
            ),
            inaccessible_fixture_ids=_string_tuple(
                item.get("inaccessible_fixture_ids"),
                f"queries[{index}].inaccessible_fixture_ids",
            ),
        )
        if query.private_scope.kind != "private":
            raise EvaluationDatasetError(f"queries[{index}].private_scope must be private")
        referenced = (
            set(query.expected_fixture_ids)
            | set(query.distractor_fixture_ids)
            | set(query.inaccessible_fixture_ids)
        )
        missing = sorted(referenced - memory_by_id.keys())
        if missing:
            raise EvaluationDatasetError(
                f"queries[{index}] references unknown fixtures: {', '.join(missing)}"
            )
        if set(query.expected_fixture_ids) & set(query.distractor_fixture_ids):
            raise EvaluationDatasetError(f"queries[{index}] expected and distractor IDs overlap")
        if any(
            not _is_accessible(memory_by_id[item_id], query)
            for item_id in query.expected_fixture_ids
        ):
            raise EvaluationDatasetError(f"queries[{index}] expected fixture is inaccessible")
        if any(
            not _is_accessible(memory_by_id[item_id], query)
            for item_id in query.distractor_fixture_ids
        ):
            raise EvaluationDatasetError(f"queries[{index}] distractor fixture is inaccessible")
        if any(
            _is_accessible(memory_by_id[item_id], query)
            for item_id in query.inaccessible_fixture_ids
        ):
            raise EvaluationDatasetError(
                f"queries[{index}] inaccessible fixture is available to the query"
            )
        queries.append(query)
    if len({query.query_id for query in queries}) != len(queries):
        raise EvaluationDatasetError("query_id values must be unique")

    top_k = value.get("top_k")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 100:
        raise EvaluationDatasetError("top_k must be an integer between 1 and 100")
    thresholds = EvaluationThresholds(
        query_count_min=_integer(
            raw_thresholds.get("query_count_min"),
            "thresholds.query_count_min",
            minimum=1,
            maximum=1_000_000,
        ),
        memory_kind_count_min=_integer(
            raw_thresholds.get("memory_kind_count_min"),
            "thresholds.memory_kind_count_min",
            minimum=1,
            maximum=1_000_000,
        ),
        recall_at_k_min=_number(
            raw_thresholds.get("recall_at_k_min"),
            "thresholds.recall_at_k_min",
            minimum=0,
            maximum=1,
        ),
        mrr_min=_number(
            raw_thresholds.get("mrr_min"),
            "thresholds.mrr_min",
            minimum=0,
            maximum=1,
        ),
        distractor_leak_rate_max=_number(
            raw_thresholds.get("distractor_leak_rate_max"),
            "thresholds.distractor_leak_rate_max",
            minimum=0,
            maximum=1,
        ),
        scope_violation_count_max=_integer(
            raw_thresholds.get("scope_violation_count_max"),
            "thresholds.scope_violation_count_max",
            minimum=0,
            maximum=1_000_000,
        ),
        runtime_seconds_max=_number(
            raw_thresholds.get("runtime_seconds_max"),
            "thresholds.runtime_seconds_max",
            minimum=0.001,
            maximum=86_400,
        ),
    )
    dataset = EvaluationDataset(
        schema_version=1,
        dataset_id=_required_string(value.get("dataset_id"), "dataset_id"),
        description=_required_string(value.get("description"), "description"),
        distractor_policy=_required_string(value.get("distractor_policy"), "distractor_policy"),
        top_k=top_k,
        memories=tuple(memories),
        queries=tuple(queries),
        thresholds=thresholds,
    )
    return dataset, digest


def score_evaluation_rankings(
    dataset: EvaluationDataset,
    rankings: dict[str, list[str]],
    *,
    runtime_seconds: float,
) -> dict[str, Any]:
    """Compute dependency-free retrieval metrics and threshold checks."""

    expected_total = 0
    expected_hits = 0
    reciprocal_rank_total = 0.0
    distractor_total = 0
    distractor_hits = 0
    scope_violation_count = 0
    uniform_random_expected_distractor_hits = 0.0
    distractor_by_kind: dict[str, dict[str, int | float]] = {}
    distractor_by_access_mode: dict[str, dict[str, int | float]] = {}
    memory_by_id = {memory.fixture_id: memory for memory in dataset.memories}
    per_query: list[dict[str, Any]] = []
    for query in dataset.queries:
        retrieved = rankings.get(query.query_id, [])[: dataset.top_k]
        if len(retrieved) != len(set(retrieved)):
            raise ValueError(f"ranking contains duplicate IDs for {query.query_id}")
        expected = set(query.expected_fixture_ids)
        distractors = set(query.distractor_fixture_ids)
        inaccessible = set(query.inaccessible_fixture_ids)
        hits = expected.intersection(retrieved)
        leaked_distractors = distractors.intersection(retrieved)
        scope_violations = inaccessible.intersection(retrieved)
        accessible_candidate_count = sum(
            _is_accessible(memory, query) for memory in dataset.memories
        )
        uniform_random_leak_probability = min(1.0, dataset.top_k / accessible_candidate_count)
        uniform_random_expected_distractor_hits += uniform_random_leak_probability * len(
            distractors
        )
        expected_total += len(expected)
        expected_hits += len(hits)
        distractor_total += len(distractors)
        distractor_hits += len(leaked_distractors)
        scope_violation_count += len(scope_violations)
        access_mode = "shared-pool" if query.shared_pools else "private-exact"
        for fixture_id in distractors:
            kind = memory_by_id[fixture_id].kind
            kind_counts = distractor_by_kind.setdefault(
                kind,
                {"hits": 0, "total": 0, "uniform_random_expected_hits": 0.0},
            )
            kind_counts["total"] += 1
            kind_counts["hits"] += int(fixture_id in leaked_distractors)
            kind_counts["uniform_random_expected_hits"] += uniform_random_leak_probability
            access_counts = distractor_by_access_mode.setdefault(
                access_mode,
                {"hits": 0, "total": 0, "uniform_random_expected_hits": 0.0},
            )
            access_counts["total"] += 1
            access_counts["hits"] += int(fixture_id in leaked_distractors)
            access_counts["uniform_random_expected_hits"] += uniform_random_leak_probability
        first_relevant_rank = next(
            (
                index
                for index, fixture_id in enumerate(retrieved, start=1)
                if fixture_id in expected
            ),
            None,
        )
        reciprocal_rank = 0.0 if first_relevant_rank is None else 1 / first_relevant_rank
        reciprocal_rank_total += reciprocal_rank
        per_query.append(
            {
                "query_id": query.query_id,
                "retrieved_fixture_ids": retrieved,
                "expected_hits": sorted(hits),
                "first_relevant_rank": first_relevant_rank,
                "reciprocal_rank": reciprocal_rank,
                "distractor_leaks": sorted(leaked_distractors),
                "scope_violations": sorted(scope_violations),
                "accessible_candidate_count": accessible_candidate_count,
                "uniform_random_leak_probability": uniform_random_leak_probability,
            }
        )

    recall_at_k = expected_hits / expected_total
    mrr = reciprocal_rank_total / len(dataset.queries)
    distractor_leak_rate = distractor_hits / distractor_total
    uniform_random_distractor_leak_rate = uniform_random_expected_distractor_hits / distractor_total
    distractor_reduction_vs_uniform_random = 1 - (
        distractor_leak_rate / uniform_random_distractor_leak_rate
    )
    metrics = {
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "distractor_leak_rate": distractor_leak_rate,
        "scope_violation_count": scope_violation_count,
        "runtime_seconds": runtime_seconds,
        "expected_hits": expected_hits,
        "expected_total": expected_total,
        "distractor_hits": distractor_hits,
        "distractor_total": distractor_total,
        "uniform_random_distractor_leak_rate": uniform_random_distractor_leak_rate,
        "distractor_reduction_vs_uniform_random": distractor_reduction_vs_uniform_random,
    }
    thresholds = asdict(dataset.thresholds)
    kind_counts = {
        kind: sum(memory.kind == kind for memory in dataset.memories)
        for kind in ("turn", "fact", "preference", "summary", "event")
    }
    checks = {
        "query_count": len(dataset.queries) >= dataset.thresholds.query_count_min,
        "memory_kind_coverage": all(
            count >= dataset.thresholds.memory_kind_count_min for count in kind_counts.values()
        ),
        "recall_at_k": recall_at_k >= dataset.thresholds.recall_at_k_min,
        "mrr": mrr >= dataset.thresholds.mrr_min,
        "distractor_leak_rate": (
            distractor_leak_rate <= dataset.thresholds.distractor_leak_rate_max
        ),
        "scope_violation_count": (
            scope_violation_count <= dataset.thresholds.scope_violation_count_max
        ),
        "runtime_seconds": runtime_seconds <= dataset.thresholds.runtime_seconds_max,
    }
    return {
        "metrics": metrics,
        "thresholds": thresholds,
        "checks": checks,
        "passed": all(checks.values()),
        "query_results": per_query,
        "diagnostics": {
            "uniform_random_expected_distractor_hits": (uniform_random_expected_distractor_hits),
            "distractor_by_memory_kind": {
                kind: {
                    **counts,
                    "rate": counts["hits"] / counts["total"],
                    "uniform_random_rate": (
                        counts["uniform_random_expected_hits"] / counts["total"]
                    ),
                    "reduction_vs_uniform_random": 1
                    - (counts["hits"] / counts["uniform_random_expected_hits"]),
                }
                for kind, counts in sorted(distractor_by_kind.items())
            },
            "distractor_by_access_mode": {
                mode: {
                    **counts,
                    "rate": counts["hits"] / counts["total"],
                    "uniform_random_rate": (
                        counts["uniform_random_expected_hits"] / counts["total"]
                    ),
                    "reduction_vs_uniform_random": 1
                    - (counts["hits"] / counts["uniform_random_expected_hits"]),
                }
                for mode, counts in sorted(distractor_by_access_mode.items())
            },
        },
    }


def run_retrieval_evaluation(
    dataset_path: str | Path,
    embedder: Embedder,
    *,
    relevance_filter: RelevanceFilter | None = None,
    retrieval: str = "vector",
    rerank: bool = False,
    reranker: Any = None,
) -> dict[str, Any]:
    """Seed an isolated store, run the dataset, and return a reproducible report."""

    dataset, dataset_sha256 = load_evaluation_dataset(dataset_path)
    started = time.perf_counter()
    rankings: dict[str, list[str]] = {}
    ranking_details: dict[str, list[dict[str, Any]]] = {}
    with (
        tempfile.TemporaryDirectory(prefix="llm-memory-eval-") as directory,
        MemoryStore(Path(directory) / "evaluation.sqlite3", embedder, reranker=reranker) as store,
    ):
        embedding_identity = store.embedding_identity
        product_default_filter = store.default_relevance_filter
        public_to_fixture: dict[str, str] = {}
        for memory in dataset.memories:
            record = store.remember(
                memory.kind,
                memory.content,
                memory.scope,
                role=memory.role,
                operation_id=f"{dataset.dataset_id}:memory:{memory.fixture_id}",
            )
            if record.embedding_status != "ready":
                raise RuntimeError(
                    f"embedding failed for fixture {memory.fixture_id}: "
                    f"{record.embedding_error or record.embedding_status}"
                )
            public_to_fixture[record.memory_id] = memory.fixture_id
        for query in dataset.queries:
            accessible_candidate_count = sum(
                _is_accessible(memory, query) for memory in dataset.memories
            )
            results = store.recall(
                query.query,
                query.private_scope,
                shared_pools=query.shared_pools,
                limit=accessible_candidate_count,
                relevance_filter=relevance_filter,
                retrieval=retrieval,
                rerank=rerank,
            )
            rankings[query.query_id] = [
                public_to_fixture[result.memory.memory_id] for result in results
            ]
            ranking_details[query.query_id] = [
                {
                    "rank": rank,
                    "fixture_id": public_to_fixture[result.memory.memory_id],
                    "score": result.score,
                    "semantic_score": result.semantic_score,
                    "recency_score": result.recency_score,
                    "distance": result.distance,
                }
                for rank, result in enumerate(results, start=1)
            ]

    runtime_seconds = time.perf_counter() - started
    score = score_evaluation_rankings(
        dataset,
        rankings,
        runtime_seconds=runtime_seconds,
    )
    query_by_id = {query.query_id: query for query in dataset.queries}
    for result in score["query_results"]:
        query = query_by_id[result["query_id"]]
        details = ranking_details[result["query_id"]]
        result["retrieved_items"] = details[: dataset.top_k]
        result["expected_item_details"] = [
            item for item in details if item["fixture_id"] in query.expected_fixture_ids
        ]
        result["distractor_item_details"] = [
            item for item in details if item["fixture_id"] in query.distractor_fixture_ids
        ]
    kind_counts = {
        kind: sum(memory.kind == kind for memory in dataset.memories)
        for kind in ("turn", "fact", "preference", "summary", "event")
    }
    return {
        "schema_version": 1,
        "evaluation_id": f"{dataset.dataset_id}:{dataset_sha256[:12]}",
        "completed_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "file_name": Path(dataset_path).name,
            "sha256": dataset_sha256,
            "description": dataset.description,
            "distractor_policy": dataset.distractor_policy,
            "memory_count": len(dataset.memories),
            "query_count": len(dataset.queries),
            "kind_counts": kind_counts,
            "top_k": dataset.top_k,
            "synthetic_only": True,
        },
        "embedding": embedding_identity.to_dict(),
        "retrieval_config": {
            "limit": dataset.top_k,
            "retrieval": retrieval,
            **({"rerank": getattr(reranker, "model_name", "default")} if rerank else {}),
            "relevance_filter": (
                relevance_filter.to_dict() if relevance_filter is not None else None
            ),
            "product_default_for_identity": relevance_filter == product_default_filter,
        },
        "runtime": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "scope_of_claim": (
            "single synthetic retrieval corpus; heuristic product gate, not a universal benchmark"
        ),
        **score,
    }


def write_evaluation_report(
    report: dict[str, Any], destination: str | Path, *, overwrite: bool = False
) -> None:
    secure_write_text(
        Path(destination).expanduser().resolve(),
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        overwrite=overwrite,
    )
