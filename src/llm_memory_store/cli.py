"""Command-line interface for the local memory store."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from .database import restore_database, secure_write_text
from .embeddings import DeterministicEmbedder, FastEmbedder, embedding_identity
from .evaluation import run_retrieval_evaluation, write_evaluation_report
from .extraction import (
    DeterministicRuleExtractor,
    OllamaProposalExtractor,
    accept_proposals,
    create_proposal_bundle,
    review_proposals,
    write_proposal_bundle,
)
from .extraction_evaluation import (
    run_extraction_evaluation,
    write_extraction_evaluation_report,
)
from .importing import import_json_store, preview_json_import
from .migration import MigrationQualityError, migrate_embeddings, preview_embedding_migration
from .models import RelevanceFilter, Scope
from .rerank import DeterministicReranker, FastEmbedReranker
from .store import MemoryStore, _certified_default_relevance_filter

DEFAULT_DB = Path(os.environ.get("LLM_MEMORY_DB", "~/.llm-memory/memory.sqlite3")).expanduser()


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _print(value: Any) -> None:
    print(json.dumps(value, default=_json_default, indent=2, sort_keys=True))


def _progress(operation: str):
    def report(completed: int, total: int) -> None:
        print(f"{operation}: embedded {completed}/{total} active memories", file=sys.stderr)

    return report


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--embedder", choices=("fastembed", "deterministic"), default="fastembed")
    parser.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    parser.add_argument("--model-cache", default=None)
    parser.add_argument(
        "--turn-ttl-days",
        type=float,
        default=float(os.environ.get("LLM_MEMORY_TURN_TTL_DAYS", "30")),
        help="Default raw-turn TTL; use 0 to disable",
    )


def _add_private_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--subject", default="me")
    parser.add_argument("--environment", default="personal")
    parser.add_argument("--agent", default="default")


def _add_any_scope_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope-kind", choices=("private", "shared"), default="private")
    parser.add_argument("--subject", default="me")
    parser.add_argument("--environment", default="personal")
    parser.add_argument("--owner", default="default", help="Agent/app or shared-pool name")


def _embedder(args: argparse.Namespace):
    if args.embedder == "deterministic":
        return DeterministicEmbedder(64)
    return FastEmbedder(
        model_name=args.model,
        cache_dir=args.model_cache,
        local_files_only=getattr(args, "offline", False),
    )


def _migration_embedder(args: argparse.Namespace, prefix: str):
    provider = getattr(args, f"{prefix}_embedder")
    if provider == "deterministic":
        return DeterministicEmbedder(getattr(args, f"{prefix}_dimension"))
    return FastEmbedder(
        model_name=getattr(args, f"{prefix}_model"),
        cache_dir=getattr(args, f"{prefix}_model_cache"),
        local_files_only=args.offline,
    )


def _store(args: argparse.Namespace) -> MemoryStore:
    ttl = None if args.turn_ttl_days == 0 else args.turn_ttl_days
    return MemoryStore(
        args.db,
        _embedder(args),
        default_turn_ttl_days=ttl,
        read_only=args.command == "review-proposals",
    )


def _scope_from_any(args: argparse.Namespace) -> Scope:
    return Scope(args.scope_kind, args.subject, args.environment, args.owner)


def _relevance_filter(value: str) -> RelevanceFilter:
    try:
        return RelevanceFilter.parse(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Initialize or validate a store")
    _add_runtime_args(init)

    turn = subparsers.add_parser("remember-turn", help="Commit a raw conversational turn")
    _add_runtime_args(turn)
    _add_private_scope_args(turn)
    turn.add_argument("--role", choices=("user", "assistant", "system", "tool"), required=True)
    turn.add_argument("--content", required=True)
    turn.add_argument("--operation-id")
    turn.add_argument("--expires-at")
    turn.add_argument("--occurred-at", help="When the message was sent, ISO 8601 with timezone")

    remember = subparsers.add_parser("remember", help="Commit a typed memory")
    _add_runtime_args(remember)
    _add_any_scope_args(remember)
    remember.add_argument(
        "--kind", choices=("fact", "preference", "summary", "event"), required=True
    )
    remember.add_argument("--content", required=True)
    remember.add_argument("--source", action="append", default=[])
    remember.add_argument("--operation-id")
    remember.add_argument("--expires-at")
    remember.add_argument("--occurred-at", help="When it happened, ISO 8601 with timezone")

    propose = subparsers.add_parser(
        "propose-extraction", help="Create a review-only typed-memory proposal artifact"
    )
    _add_runtime_args(propose)
    _add_any_scope_args(propose)
    propose.add_argument("--source", action="append", required=True)
    propose.add_argument("--output", type=Path, required=True)
    propose.add_argument(
        "--extractor", choices=("deterministic", "ollama"), default="deterministic"
    )
    propose.add_argument("--ollama-model", default="llama3.1:8b")
    propose.add_argument("--ollama-revision", default="unverified-local-tag")
    propose.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    propose.add_argument("--ollama-timeout", type=float, default=120.0)

    review = subparsers.add_parser(
        "review-proposals", help="Analyze a proposal artifact against the store without writing"
    )
    _add_runtime_args(review)
    review.add_argument("--proposal-file", type=Path, required=True)
    review.add_argument("--output", type=Path, help="Write an owner-only review report")
    review.add_argument(
        "--show-proposal-content",
        action="store_true",
        help="Include sensitive proposal text in the report",
    )
    review.add_argument(
        "--show-source-content",
        action="store_true",
        help="Include sensitive current source text in the report",
    )

    accept = subparsers.add_parser(
        "accept-proposals", help="Explicitly commit selected, revalidated proposals"
    )
    _add_runtime_args(accept)
    accept.add_argument("--proposal-file", type=Path, required=True)
    accept.add_argument("--proposal-id", action="append", required=True)
    accept.add_argument("--expected-digest", required=True)
    accept.add_argument("--yes", action="store_true", help="Confirm the selected durable writes")

    recall = subparsers.add_parser("recall", help="Recall from a private scope and named pools")
    _add_runtime_args(recall)
    _add_private_scope_args(recall)
    recall.add_argument("--query", required=True)
    recall.add_argument("--shared-pool", action="append", default=[])
    recall.add_argument("--limit", type=int, default=5)
    recall.add_argument("--max-characters", type=int, default=4000)
    recall.add_argument(
        "--retrieval",
        choices=("vector", "hybrid"),
        default="vector",
        help="hybrid adds keyword matching, for queries that repeat exact words or names",
    )
    recall.add_argument(
        "--rerank",
        action="store_true",
        help="re-score the top vector candidates with a local cross-encoder (about 150 ms more)",
    )
    recall_filter = recall.add_mutually_exclusive_group()
    recall_filter.add_argument(
        "--relevance-filter",
        type=_relevance_filter,
        help="Override filtering, for example relative:0.10; may return fewer than --limit",
    )
    recall_filter.add_argument(
        "--no-relevance-filter",
        action="store_true",
        help="Restore the legacy unfiltered top-K behavior",
    )

    get = subparsers.add_parser("get", help="Inspect one memory by public ID")
    _add_runtime_args(get)
    get.add_argument("--memory-id", required=True)

    list_parser = subparsers.add_parser("list", help="List recent memories")
    _add_runtime_args(list_parser)
    _add_any_scope_args(list_parser)
    list_parser.add_argument("--all-scopes", action="store_true")
    list_parser.add_argument("--include-superseded", action="store_true")
    list_parser.add_argument("--limit", type=int, default=100)

    correct = subparsers.add_parser("correct", help="Supersede a memory with corrected content")
    _add_runtime_args(correct)
    correct.add_argument("--memory-id", required=True)
    correct.add_argument("--content", required=True)
    correct.add_argument("--operation-id")

    preview = subparsers.add_parser("preview-forget", help="Preview a memory deletion cascade")
    _add_runtime_args(preview)
    preview.add_argument("--memory-id", required=True)

    forget = subparsers.add_parser("forget", help="Hard-delete a memory lineage and descendants")
    _add_runtime_args(forget)
    forget.add_argument("--memory-id", required=True)
    forget.add_argument("--yes", action="store_true", help="Execute instead of previewing")

    forget_scope = subparsers.add_parser("forget-scope", help="Hard-delete an exact scope")
    _add_runtime_args(forget_scope)
    _add_any_scope_args(forget_scope)
    forget_scope.add_argument("--yes", action="store_true", help="Execute instead of previewing")

    purge = subparsers.add_parser(
        "purge-expired", help="Preview or physically purge safely removable expired memories"
    )
    _add_runtime_args(purge)
    purge.add_argument("--as-of", help="Timezone-aware ISO 8601 cutoff; defaults to now")
    purge.add_argument("--expected-digest", help="Abort if the preview set has changed")
    purge.add_argument(
        "--force-current",
        action="store_true",
        help="Confirm the recomputed set without matching a prior preview digest",
    )
    purge.add_argument("--yes", action="store_true", help="Execute instead of previewing")

    export = subparsers.add_parser("export", help="Export logical memories as JSON")
    _add_runtime_args(export)
    export.add_argument("--destination", type=Path, required=True)
    export_selector = export.add_mutually_exclusive_group(required=True)
    export_selector.add_argument("--scope-kind", choices=("private", "shared"))
    export_selector.add_argument("--subject-only", action="store_true")
    export_selector.add_argument("--all-scopes", action="store_true")
    export.add_argument("--subject", default="me")
    export.add_argument("--environment", default="personal")
    export.add_argument("--owner", default="default")
    export.add_argument(
        "--yes", action="store_true", help="Confirm a subject-wide or whole-store export"
    )
    export.add_argument("--overwrite", action="store_true")

    backup = subparsers.add_parser("backup", help="Create a consistent SQLite snapshot")
    _add_runtime_args(backup)
    backup.add_argument("--destination", type=Path, required=True)
    backup.add_argument("--overwrite", action="store_true")
    backup.add_argument("--yes", action="store_true", help="Confirm overwriting an artifact")

    restore = subparsers.add_parser("restore", help="Restore a snapshot into a database path")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--db", type=Path, default=DEFAULT_DB)
    restore.add_argument("--yes", action="store_true", help="Confirm creation of the restored DB")

    process = subparsers.add_parser("process-pending", help="Retry pending/failed embeddings")
    _add_runtime_args(process)
    process.add_argument("--limit", type=int, default=100)

    status = subparsers.add_parser("status", help="Inspect store integrity and counts")
    _add_runtime_args(status)

    evaluate = subparsers.add_parser(
        "evaluate-retrieval",
        help="Run a versioned synthetic retrieval-quality gate",
    )
    evaluate.add_argument("--dataset", type=Path, required=True)
    evaluate.add_argument("--report", type=Path)
    evaluate.add_argument("--embedder", choices=("fastembed", "deterministic"), default="fastembed")
    evaluate.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    evaluate.add_argument("--model-cache", default=None)
    evaluate.add_argument(
        "--offline",
        action="store_true",
        help="Require the embedding model to exist in the local cache",
    )
    evaluate.add_argument("--overwrite", action="store_true")
    evaluate.add_argument("--retrieval", choices=("vector", "hybrid"), default="vector")
    evaluate.add_argument("--rerank", action="store_true")
    evaluation_filter = evaluate.add_mutually_exclusive_group()
    evaluation_filter.add_argument(
        "--relevance-filter",
        type=_relevance_filter,
        help="Override the identity-scoped default, for example relative:0.10",
    )
    evaluation_filter.add_argument(
        "--no-relevance-filter",
        action="store_true",
        help="Evaluate the legacy unfiltered top-K behavior",
    )

    extraction_evaluate = subparsers.add_parser(
        "evaluate-extraction",
        help="Run a frozen, review-only extraction-quality track",
    )
    extraction_evaluate.add_argument("--dataset", type=Path, required=True)
    extraction_evaluate.add_argument("--track", choices=("offline", "live"), required=True)
    extraction_evaluate.add_argument("--report", type=Path)
    extraction_evaluate.add_argument(
        "--extractor", choices=("deterministic", "ollama"), default="deterministic"
    )
    extraction_evaluate.add_argument("--ollama-model", default="llama3.1:8b")
    extraction_evaluate.add_argument("--ollama-revision", default="unverified-local-tag")
    extraction_evaluate.add_argument("--ollama-endpoint", default="http://127.0.0.1:11434")
    extraction_evaluate.add_argument("--ollama-timeout", type=float, default=120.0)
    extraction_evaluate.add_argument("--overwrite", action="store_true")

    migration = subparsers.add_parser(
        "migrate-embeddings", help="Preview or create a new store in another embedding space"
    )
    migration.add_argument("--source", type=Path, required=True)
    migration.add_argument("--destination", type=Path, required=True)
    migration.add_argument("--quality-dataset", type=Path, required=True)
    migration.add_argument("--report", type=Path, required=True)
    for prefix in ("source", "target"):
        migration.add_argument(
            f"--{prefix}-embedder",
            choices=("fastembed", "deterministic"),
            default="fastembed",
        )
        migration.add_argument(f"--{prefix}-model", default="BAAI/bge-small-en-v1.5")
        migration.add_argument(f"--{prefix}-model-cache", default=None)
        migration.add_argument(f"--{prefix}-dimension", type=int, default=64)
    migration.add_argument("--offline", action="store_true")
    migration.add_argument("--batch-size", type=int, default=64)
    migration.add_argument("--expected-digest")
    migration.add_argument("--force-current", action="store_true")
    migration.add_argument("--accept-quality-regression", action="store_true")
    migration.add_argument("--quality-regression-reason")
    migration.add_argument("--yes", action="store_true", help="Execute instead of previewing")

    json_import = subparsers.add_parser(
        "import-json", help="Preview or import a versioned JSON export into a new store"
    )
    json_import.add_argument("--source", type=Path, required=True)
    json_import.add_argument("--destination", type=Path, required=True)
    json_import.add_argument("--report", type=Path, required=True)
    json_import.add_argument(
        "--embedder", choices=("fastembed", "deterministic"), default="fastembed"
    )
    json_import.add_argument("--model", default="BAAI/bge-small-en-v1.5")
    json_import.add_argument("--model-cache", default=None)
    json_import.add_argument("--dimension", type=int, default=64)
    json_import.add_argument("--offline", action="store_true")
    json_import.add_argument("--batch-size", type=int, default=64)
    json_import.add_argument("--allow-missing-sources", action="store_true")
    json_import.add_argument("--expected-digest")
    json_import.add_argument("--force-current", action="store_true")
    json_import.add_argument("--yes", action="store_true", help="Execute instead of previewing")

    mcp = subparsers.add_parser("mcp", help="Run the stdio MCP server")
    _add_runtime_args(mcp)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "restore":
        if not args.yes:
            parser.error("restore requires --yes and a destination path that does not exist")
        restore_database(args.source.expanduser(), args.db.expanduser())
        _print({"restored": str(args.db.expanduser().resolve()), "source": str(args.source)})
        return
    if args.command == "accept-proposals" and not args.yes:
        parser.error("proposal acceptance requires --yes")
    if args.command == "review-proposals" and not args.db.expanduser().is_file():
        parser.error("proposal review requires an existing --db store")
    if args.command == "mcp":
        os.environ["LLM_MEMORY_DB"] = str(args.db.expanduser().resolve())
        os.environ["LLM_MEMORY_EMBEDDER"] = args.embedder
        os.environ["LLM_MEMORY_MODEL"] = args.model
        os.environ["LLM_MEMORY_TURN_TTL_DAYS"] = str(args.turn_ttl_days)
        if args.model_cache:
            os.environ["LLM_MEMORY_MODEL_CACHE"] = args.model_cache
        from .mcp_server import main as mcp_main

        mcp_main()
        return
    if args.command == "evaluate-retrieval":
        embedder = _embedder(args)
        effective_filter = (
            None
            if args.no_relevance_filter
            else (
                args.relevance_filter
                if args.relevance_filter is not None
                else _certified_default_relevance_filter(embedding_identity(embedder))
            )
        )
        report = run_retrieval_evaluation(
            args.dataset,
            embedder,
            relevance_filter=effective_filter,
            retrieval=args.retrieval,
            rerank=args.rerank,
            reranker=(
                FastEmbedReranker(cache_dir=args.model_cache, local_files_only=args.offline)
                if args.rerank and args.embedder == "fastembed"
                else DeterministicReranker()
                if args.rerank
                else None
            ),
        )
        if args.report:
            write_evaluation_report(report, args.report, overwrite=args.overwrite)
        _print(report)
        if not report["passed"]:
            raise SystemExit(1)
        return
    if args.command == "evaluate-extraction":
        if args.ollama_timeout <= 0:
            parser.error("--ollama-timeout must be positive")
        extractor = (
            DeterministicRuleExtractor()
            if args.extractor == "deterministic"
            else OllamaProposalExtractor(
                args.ollama_model,
                args.ollama_endpoint,
                revision=args.ollama_revision,
                timeout_seconds=args.ollama_timeout,
            )
        )
        report = run_extraction_evaluation(args.dataset, extractor, track=args.track)
        if args.report:
            write_extraction_evaluation_report(report, args.report, overwrite=args.overwrite)
        _print(report)
        if not report["passed"]:
            raise SystemExit(1)
        return
    if args.command == "migrate-embeddings":
        source_embedder = _migration_embedder(args, "source")
        target_embedder = _migration_embedder(args, "target")
        preview = preview_embedding_migration(
            args.source,
            args.destination,
            source_embedder,
            target_embedder,
            args.quality_dataset,
        )
        report_path = args.report.expanduser().resolve()
        if not args.yes:
            if (
                args.expected_digest
                or args.force_current
                or args.accept_quality_regression
                or args.quality_regression_reason
            ):
                parser.error("migration confirmation and override options require --yes")
            _print(
                {
                    "executed": False,
                    "preview": preview.to_dict(),
                    "report": str(report_path),
                }
            )
            return
        if args.expected_digest is None and not args.force_current:
            parser.error(
                "migration execution requires --expected-digest from a preview or --force-current"
            )
        if args.expected_digest is not None and args.force_current:
            parser.error("select --expected-digest or --force-current, not both")
        if args.accept_quality_regression and not (args.quality_regression_reason or "").strip():
            parser.error("--accept-quality-regression requires --quality-regression-reason")
        if args.quality_regression_reason and not args.accept_quality_regression:
            parser.error("--quality-regression-reason requires --accept-quality-regression")
        if report_path.exists():
            parser.error("migration report destination already exists")
        try:
            result = migrate_embeddings(
                args.source,
                args.destination,
                source_embedder,
                target_embedder,
                args.quality_dataset,
                expected_digest=args.expected_digest,
                accept_quality_regression=args.accept_quality_regression,
                quality_regression_reason=args.quality_regression_reason,
                batch_size=args.batch_size,
                progress_callback=_progress("embedding migration"),
            )
        except MigrationQualityError as exc:
            secure_write_text(report_path, json.dumps(exc.report, indent=2, sort_keys=True) + "\n")
            _print({**exc.report, "report": str(report_path)})
            raise SystemExit(1) from exc
        secure_write_text(report_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
        _print({**result, "report": str(report_path)})
        return
    if args.command == "import-json":
        embedder = (
            DeterministicEmbedder(args.dimension)
            if args.embedder == "deterministic"
            else FastEmbedder(
                model_name=args.model,
                cache_dir=args.model_cache,
                local_files_only=args.offline,
            )
        )
        preview = preview_json_import(
            args.source,
            args.destination,
            embedder,
            allow_missing_sources=args.allow_missing_sources,
        )
        report_path = args.report.expanduser().resolve()
        if not args.yes:
            if args.expected_digest or args.force_current:
                parser.error("import confirmation options require --yes")
            _print(
                {
                    "executed": False,
                    "preview": preview.to_dict(),
                    "report": str(report_path),
                }
            )
            return
        if args.expected_digest is None and not args.force_current:
            parser.error(
                "JSON import execution requires --expected-digest from a preview or --force-current"
            )
        if args.expected_digest is not None and args.force_current:
            parser.error("select --expected-digest or --force-current, not both")
        if report_path.exists():
            parser.error("import report destination already exists")
        result = import_json_store(
            args.source,
            args.destination,
            embedder,
            allow_missing_sources=args.allow_missing_sources,
            expected_digest=args.expected_digest,
            batch_size=args.batch_size,
            progress_callback=_progress("JSON import"),
        )
        secure_write_text(report_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
        _print({**result, "report": str(report_path)})
        return

    with _store(args) as store:
        if args.command == "init":
            _print(store.status())
        elif args.command == "remember-turn":
            scope = Scope.private(args.subject, args.environment, args.agent)
            _print(
                store.remember_turn(
                    args.content,
                    args.role,
                    scope,
                    operation_id=args.operation_id,
                    expires_at=args.expires_at,
                    occurred_at=args.occurred_at,
                )
            )
        elif args.command == "remember":
            _print(
                store.remember(
                    args.kind,
                    args.content,
                    _scope_from_any(args),
                    source_memory_ids=args.source,
                    operation_id=args.operation_id,
                    expires_at=args.expires_at,
                    occurred_at=args.occurred_at,
                )
            )
        elif args.command == "propose-extraction":
            if args.ollama_timeout <= 0:
                parser.error("--ollama-timeout must be positive")
            extractor = (
                DeterministicRuleExtractor()
                if args.extractor == "deterministic"
                else OllamaProposalExtractor(
                    args.ollama_model,
                    args.ollama_endpoint,
                    revision=args.ollama_revision,
                    timeout_seconds=args.ollama_timeout,
                )
            )
            bundle = create_proposal_bundle(store, args.source, _scope_from_any(args), extractor)
            destination = write_proposal_bundle(bundle, args.output)
            _print(
                {
                    "executed": False,
                    "proposal_file": str(destination),
                    "proposal_count": len(bundle.proposals),
                    "bundle_digest": bundle.bundle_digest,
                    "proposals": [proposal.to_dict() for proposal in bundle.proposals],
                }
            )
        elif args.command == "review-proposals":
            review_report = review_proposals(
                store,
                args.proposal_file,
                show_proposal_content=args.show_proposal_content,
                show_source_content=args.show_source_content,
            )
            review_file: str | None = None
            if args.output:
                destination = args.output.expanduser().resolve()
                secure_write_text(
                    destination,
                    json.dumps(review_report.to_dict(), indent=2, sort_keys=True) + "\n",
                )
                review_file = str(destination)
            _print(
                {
                    "executed": False,
                    "review_file": review_file,
                    "report": review_report,
                }
            )
        elif args.command == "accept-proposals":
            receipt = accept_proposals(
                store,
                args.proposal_file,
                args.proposal_id,
                expected_digest=args.expected_digest,
            )
            _print({"executed": True, "receipt": receipt})
        elif args.command == "recall":
            scope = Scope.private(args.subject, args.environment, args.agent)
            if args.no_relevance_filter:
                effective_filter = None
                filter_policy = "explicit_off"
            elif args.relevance_filter is not None:
                effective_filter = args.relevance_filter
                filter_policy = "explicit_override"
            else:
                effective_filter = store.default_relevance_filter
                filter_policy = (
                    "certified_default" if effective_filter is not None else "uncertified_off"
                )
            results = store.recall(
                args.query,
                scope,
                shared_pools=args.shared_pool,
                limit=args.limit,
                relevance_filter=effective_filter,
                retrieval=args.retrieval,
                rerank=args.rerank,
            )
            bundle = store.context_bundle(args.query, results, max_characters=args.max_characters)
            bundle["retrieval"] = args.retrieval
            bundle["rerank"] = args.rerank
            bundle["relevance_filter"] = (
                effective_filter.to_dict() if effective_filter is not None else None
            )
            bundle["relevance_filter_policy"] = filter_policy
            if effective_filter is not None:
                bundle["filtering_note"] = (
                    "Relevance filtering may return zero or fewer than the requested limit."
                )
            _print(bundle)
        elif args.command == "get":
            _print(store.get(args.memory_id))
        elif args.command == "list":
            scope = None if args.all_scopes else _scope_from_any(args)
            _print(
                [
                    record.to_dict()
                    for record in store.list_memories(
                        scope,
                        include_superseded=args.include_superseded,
                        limit=args.limit,
                    )
                ]
            )
        elif args.command == "correct":
            _print(store.correct(args.memory_id, args.content, operation_id=args.operation_id))
        elif args.command == "preview-forget":
            _print(store.preview_forget(args.memory_id))
        elif args.command == "forget":
            if args.yes:
                _print(store.forget(args.memory_id))
            else:
                _print(
                    {
                        "executed": False,
                        "preview": store.preview_forget(args.memory_id).to_dict(),
                    }
                )
        elif args.command == "forget-scope":
            scope = _scope_from_any(args)
            if args.yes:
                _print(store.forget_scope(scope))
            else:
                _print({"executed": False, "preview": store.preview_forget_scope(scope).to_dict()})
        elif args.command == "purge-expired":
            if args.yes:
                if args.expected_digest is None and not args.force_current:
                    parser.error(
                        "purge execution requires --expected-digest from a preview "
                        "or --force-current"
                    )
                if args.expected_digest is not None and args.force_current:
                    parser.error("select --expected-digest or --force-current, not both")
                _print(
                    {
                        "executed": True,
                        "receipt": store.purge_expired(
                            args.as_of, expected_digest=args.expected_digest
                        ).to_dict(),
                    }
                )
            else:
                if args.expected_digest or args.force_current:
                    parser.error("--expected-digest and --force-current require --yes")
                _print(
                    {
                        "executed": False,
                        "preview": store.preview_expiry_purge(args.as_of).to_dict(),
                    }
                )
        elif args.command == "export":
            if (args.subject_only or args.all_scopes) and not args.yes:
                parser.error("subject-wide and whole-store exports require --yes")
            if args.overwrite and not args.yes:
                parser.error("overwriting an export requires --yes")
            scope = None
            subject = args.subject if args.subject_only else None
            if args.scope_kind and not args.subject_only:
                scope = Scope(args.scope_kind, args.subject, args.environment, args.owner)
            _print(
                store.export_json(
                    args.destination,
                    scope,
                    subject=subject,
                    all_scopes=args.all_scopes,
                    overwrite=args.overwrite,
                )
            )
        elif args.command == "backup":
            if args.overwrite and not args.yes:
                parser.error("overwriting a backup requires --yes")
            _print(store.backup(args.destination, overwrite=args.overwrite))
        elif args.command == "process-pending":
            _print(store.process_pending(args.limit))
        elif args.command == "status":
            _print(store.status())
        else:
            raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
