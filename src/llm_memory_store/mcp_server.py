"""MCP stdio adapter for the local memory store."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .embeddings import DeterministicEmbedder, FastEmbedder
from .models import RelevanceFilter, Scope
from .store import MemoryStore

mcp = FastMCP("Local LLM Memory", json_response=True)


@lru_cache(maxsize=1)
def get_store() -> MemoryStore:
    path = Path(os.environ.get("LLM_MEMORY_DB", "~/.llm-memory/memory.sqlite3")).expanduser()
    embedder_name = os.environ.get("LLM_MEMORY_EMBEDDER", "fastembed")
    if embedder_name == "deterministic":
        embedder = DeterministicEmbedder(64)
    else:
        embedder = FastEmbedder(
            model_name=os.environ.get("LLM_MEMORY_MODEL", "BAAI/bge-small-en-v1.5"),
            cache_dir=os.environ.get("LLM_MEMORY_MODEL_CACHE"),
        )
    ttl_value = float(os.environ.get("LLM_MEMORY_TURN_TTL_DAYS", "30"))
    return MemoryStore(path, embedder, default_turn_ttl_days=None if ttl_value == 0 else ttl_value)


@mcp.tool(name="memory_remember_turn")
def memory_remember_turn(
    content: str,
    role: str,
    subject: str = "me",
    environment: str = "personal",
    agent_or_app: str = "default",
    operation_id: str | None = None,
    expires_at: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Durably commit a raw turn to a private agent/application scope.

    occurred_at: when the message was sent (ISO 8601 with timezone), when importing history.
    """
    record = get_store().remember_turn(
        content,
        role,  # type: ignore[arg-type]
        Scope.private(subject, environment, agent_or_app),
        operation_id=operation_id,
        expires_at=expires_at,
        occurred_at=occurred_at,
    )
    return record.to_dict()


@mcp.tool(name="memory_remember")
def memory_remember(
    kind: str,
    content: str,
    scope_kind: str = "private",
    subject: str = "me",
    environment: str = "personal",
    owner: str = "default",
    source_memory_ids: list[str] | None = None,
    operation_id: str | None = None,
    expires_at: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    """Commit a typed fact, preference, summary, or event.

    occurred_at: when it happened (ISO 8601 with timezone), if earlier than now.
    """
    record = get_store().remember(
        kind,  # type: ignore[arg-type]
        content,
        Scope(scope_kind, subject, environment, owner),  # type: ignore[arg-type]
        source_memory_ids=source_memory_ids or (),
        operation_id=operation_id,
        expires_at=expires_at,
        occurred_at=occurred_at,
    )
    return record.to_dict()


@mcp.tool(name="memory_recall")
def memory_recall(
    query: str,
    subject: str = "me",
    environment: str = "personal",
    agent_or_app: str = "default",
    shared_pools: list[str] | None = None,
    limit: int = 5,
    max_characters: int = 4000,
    relevance_filter: str | None = "default",
    retrieval: str = "vector",
) -> dict[str, Any]:
    """Recall scopes; filter is default, off, or relative:GAP and may return < limit, even zero.

    retrieval is vector (default) or hybrid; hybrid adds keyword matching, which helps when the
    query repeats exact words, names, or numbers from the memory, and can hurt paraphrases.
    """

    store = get_store()
    if relevance_filter in (None, "default"):
        parsed_filter = store.default_relevance_filter
        filter_policy = "certified_default" if parsed_filter is not None else "uncertified_off"
    elif relevance_filter == "off":
        parsed_filter = None
        filter_policy = "explicit_off"
    else:
        parsed_filter = RelevanceFilter.parse(relevance_filter)
        filter_policy = "explicit_override"
    results = store.recall(
        query,
        Scope.private(subject, environment, agent_or_app),
        shared_pools=shared_pools or (),
        limit=limit,
        relevance_filter=parsed_filter,
        retrieval=retrieval,
    )
    bundle = store.context_bundle(query, results, max_characters=max_characters)
    bundle["retrieval"] = retrieval
    bundle["relevance_filter"] = parsed_filter.to_dict() if parsed_filter is not None else None
    bundle["relevance_filter_policy"] = filter_policy
    if parsed_filter is not None:
        bundle["filtering_note"] = (
            "Relevance filtering may return zero or fewer than the requested limit."
        )
    return bundle


@mcp.tool(name="memory_get")
def memory_get(memory_id: str) -> dict[str, Any]:
    """Inspect one memory by public ID, including versions and provenance."""
    return get_store().get(memory_id).to_dict()


@mcp.tool(name="memory_list")
def memory_list(
    scope_kind: str = "private",
    subject: str = "me",
    environment: str = "personal",
    owner: str = "default",
    include_superseded: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List recent memories from one exact scope."""
    scope = Scope(scope_kind, subject, environment, owner)  # type: ignore[arg-type]
    return [
        record.to_dict()
        for record in get_store().list_memories(
            scope, include_superseded=include_superseded, limit=limit
        )
    ]


@mcp.tool(name="memory_correct")
def memory_correct(
    memory_id: str, new_content: str, operation_id: str | None = None
) -> dict[str, Any]:
    """Create a corrected active version and supersede the previous version."""
    return get_store().correct(memory_id, new_content, operation_id=operation_id).to_dict()


@mcp.tool(name="memory_preview_forget")
def memory_preview_forget(memory_id: str) -> dict[str, Any]:
    """Preview the lineage and derived descendants affected by hard deletion."""
    return get_store().preview_forget(memory_id).to_dict()


@mcp.tool(name="memory_forget")
def memory_forget(memory_id: str, confirm: bool = False) -> dict[str, Any]:
    """Hard-delete a lineage and descendants; pass confirm=true to execute."""
    store = get_store()
    if not confirm:
        return {"executed": False, "preview": store.preview_forget(memory_id).to_dict()}
    return {"executed": True, "receipt": store.forget(memory_id).to_dict()}


@mcp.tool(name="memory_forget_scope")
def memory_forget_scope(
    scope_kind: str,
    subject: str,
    environment: str,
    owner: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Hard-delete an exact scope and derived descendants; confirm explicitly."""
    scope = Scope(scope_kind, subject, environment, owner)  # type: ignore[arg-type]
    store = get_store()
    if not confirm:
        return {"executed": False, "preview": store.preview_forget_scope(scope).to_dict()}
    return {"executed": True, "receipt": store.forget_scope(scope).to_dict()}


@mcp.tool(name="memory_purge_expired")
def memory_purge_expired(
    as_of: str | None = None,
    confirm: bool = False,
    expected_digest: str | None = None,
    force_current: bool = False,
) -> dict[str, Any]:
    """Preview expiry cleanup; confirm with its digest or explicit force_current."""

    store = get_store()
    if not confirm:
        if expected_digest is not None or force_current:
            raise ValueError("expected_digest and force_current require confirm=true")
        return {"executed": False, "preview": store.preview_expiry_purge(as_of).to_dict()}
    if expected_digest is None and not force_current:
        raise ValueError("confirm=true requires expected_digest or force_current=true")
    if expected_digest is not None and force_current:
        raise ValueError("select expected_digest or force_current, not both")
    return {
        "executed": True,
        "receipt": store.purge_expired(as_of, expected_digest=expected_digest).to_dict(),
    }


@mcp.tool(name="memory_export")
def memory_export(
    destination: str,
    scope_kind: str | None = None,
    subject: str = "me",
    environment: str = "personal",
    owner: str = "default",
    subject_only: bool = False,
    all_scopes: bool = False,
    confirm: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Export explicitly selected memory data; call again with confirm=true to write."""
    selector_count = int(scope_kind is not None) + int(subject_only) + int(all_scopes)
    if selector_count != 1:
        raise ValueError("select exactly one scope_kind, subject_only, or all_scopes")
    scope = None
    if scope_kind is not None and not subject_only:
        scope = Scope(scope_kind, subject, environment, owner)  # type: ignore[arg-type]
    selection = {
        "scope": scope.to_dict() if scope else None,
        "subject": subject if subject_only else None,
        "all_scopes": all_scopes,
        "destination": str(Path(destination).expanduser().resolve()),
        "overwrite": overwrite,
    }
    if not confirm:
        return {"executed": False, "selection": selection}
    result = get_store().export_json(
        destination,
        scope,
        subject=subject if subject_only else None,
        all_scopes=all_scopes,
        overwrite=overwrite,
    )
    return {"executed": True, "selection": selection, "result": result}


@mcp.tool(name="memory_backup")
def memory_backup(
    destination: str, confirm: bool = False, overwrite: bool = False
) -> dict[str, Any]:
    """Create a snapshot; call again with confirm=true to write the file."""
    resolved = str(Path(destination).expanduser().resolve())
    if not confirm:
        return {
            "executed": False,
            "destination": resolved,
            "overwrite": overwrite,
        }
    return {
        "executed": True,
        "result": get_store().backup(destination, overwrite=overwrite),
    }


@mcp.tool(name="memory_process_pending")
def memory_process_pending(limit: int = 100) -> dict[str, Any]:
    """Retry pending or failed local embeddings without a daemon."""
    return get_store().process_pending(limit)


@mcp.tool(name="memory_status")
def memory_status() -> dict[str, Any]:
    """Return schema, model, count, and integrity information."""
    return get_store().status()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
