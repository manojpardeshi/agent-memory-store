from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_mcp_stdio_vertical_slice(tmp_path) -> None:
    async def run() -> None:
        environment = dict(os.environ)
        environment.update(
            {
                "LLM_MEMORY_DB": str(tmp_path / "memory.sqlite3"),
                "LLM_MEMORY_EMBEDDER": "deterministic",
            }
        )
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "llm_memory_store.mcp_server"],
            env=environment,
        )
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {
                "memory_remember_turn",
                "memory_recall",
                "memory_correct",
                "memory_preview_forget",
                "memory_forget",
                "memory_purge_expired",
                "memory_export",
                "memory_backup",
                "memory_status",
            } <= names
            recall_tool = next(tool for tool in tools.tools if tool.name == "memory_recall")
            assert recall_tool.description is not None
            assert "may return < limit" in recall_tool.description

            remembered = await session.call_tool(
                "memory_remember_turn",
                {
                    "content": "MCP remembers portable local software",
                    "role": "user",
                    "subject": "me",
                    "environment": "test",
                    "agent_or_app": "codex",
                },
            )
            assert remembered.isError is False

            recalled = await session.call_tool(
                "memory_recall",
                {
                    "query": "portable local software",
                    "subject": "me",
                    "environment": "test",
                    "agent_or_app": "codex",
                },
            )
            assert recalled.isError is False
            assert recalled.structuredContent is not None
            assert recalled.structuredContent["items"][0]["memory"]["content"] == (
                "MCP remembers portable local software"
            )

            for content in (
                "synthetic cobalt editor preference",
                "unrelated lunar calendar",
            ):
                remembered_filter_fixture = await session.call_tool(
                    "memory_remember",
                    {
                        "kind": "fact",
                        "content": content,
                        "subject": "me",
                        "environment": "filter-test",
                        "owner": "app",
                    },
                )
                assert remembered_filter_fixture.isError is False
            recall_arguments = {
                "query": "synthetic cobalt editor preference",
                "subject": "me",
                "environment": "filter-test",
                "agent_or_app": "app",
                "limit": 2,
            }
            unfiltered = await session.call_tool("memory_recall", recall_arguments)
            filtered = await session.call_tool(
                "memory_recall",
                {**recall_arguments, "relevance_filter": "relative:0"},
            )
            assert unfiltered.structuredContent is not None
            assert filtered.structuredContent is not None
            assert len(unfiltered.structuredContent["items"]) == 2
            assert unfiltered.structuredContent["relevance_filter"] is None
            assert unfiltered.structuredContent["relevance_filter_policy"] == "uncertified_off"
            assert len(filtered.structuredContent["items"]) == 1
            assert filtered.structuredContent["relevance_filter"] == {
                "strategy": "relative_semantic_gap",
                "maximum_semantic_score_gap": 0.0,
            }
            assert filtered.structuredContent["relevance_filter_policy"] == "explicit_override"
            explicitly_off = await session.call_tool(
                "memory_recall",
                {**recall_arguments, "relevance_filter": "off"},
            )
            assert explicitly_off.structuredContent is not None
            assert explicitly_off.structuredContent["relevance_filter_policy"] == "explicit_off"

            export_path = tmp_path / "mcp-export.json"
            export_preview = await session.call_tool(
                "memory_export",
                {
                    "destination": str(export_path),
                    "scope_kind": "private",
                    "subject": "me",
                    "environment": "test",
                    "owner": "codex",
                },
            )
            assert export_preview.isError is False
            assert export_preview.structuredContent["executed"] is False
            assert not export_path.exists()

            exported = await session.call_tool(
                "memory_export",
                {
                    "destination": str(export_path),
                    "scope_kind": "private",
                    "subject": "me",
                    "environment": "test",
                    "owner": "codex",
                    "confirm": True,
                },
            )
            assert exported.isError is False
            assert exported.structuredContent["executed"] is True
            assert export_path.stat().st_mode & 0o777 == 0o600

            backup_path = tmp_path / "mcp-backup.sqlite3"
            backup_preview = await session.call_tool(
                "memory_backup", {"destination": str(backup_path)}
            )
            assert backup_preview.isError is False
            assert backup_preview.structuredContent["executed"] is False
            assert not backup_path.exists()

            expired = await session.call_tool(
                "memory_remember",
                {
                    "kind": "fact",
                    "content": "Expired MCP fixture",
                    "subject": "me",
                    "environment": "purge-test",
                    "owner": "app",
                    "expires_at": "2000-01-01T00:00:00Z",
                },
            )
            assert expired.isError is False
            purge_preview = await session.call_tool(
                "memory_purge_expired", {"as_of": "2001-01-01T00:00:00Z"}
            )
            assert purge_preview.isError is False
            assert purge_preview.structuredContent is not None
            assert purge_preview.structuredContent["executed"] is False
            preview = purge_preview.structuredContent["preview"]
            unbound_confirm = await session.call_tool(
                "memory_purge_expired",
                {"as_of": preview["cutoff"], "confirm": True},
            )
            assert unbound_confirm.isError is True
            purged = await session.call_tool(
                "memory_purge_expired",
                {
                    "as_of": preview["cutoff"],
                    "confirm": True,
                    "expected_digest": preview["digest"],
                },
            )
            assert purged.isError is False
            assert purged.structuredContent is not None
            assert purged.structuredContent["receipt"]["deleted_memories"] == 1
            assert purged.structuredContent["receipt"]["verified"] is True

    asyncio.run(run())
