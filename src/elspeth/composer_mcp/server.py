"""MCP server for ELSPETH pipeline composition.

Exposes discovery and mutation tools from the web composer, plus
session management tools, over the MCP protocol. Blob and secret
tools are excluded (no session database or secret service in CLI mode).

Layer: L3 (application). Imports from L0 (contracts), L3 (web.composer,
web.catalog, composer_mcp.session).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, TypedDict

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool
from pydantic import BaseModel

from elspeth.composer_mcp.session import SessionManager, SessionNotFoundError
from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.composer.state import CompositionState, PipelineMetadata
from elspeth.web.composer.tools import (
    _DISCOVERY_TOOLS,
    _MUTATION_TOOLS,
    execute_tool,
    get_tool_definitions,
    redact_source_storage_path,
)
from elspeth.web.composer.yaml_generator import generate_yaml

__all__ = ["create_server", "main"]

logger = logging.getLogger(__name__)


class _ValidationEntryPayload(TypedDict):
    component: str
    message: str
    severity: str


_EdgeContractPayload = TypedDict(
    "_EdgeContractPayload",
    {
        "from": str,
        "to": str,
        "producer_guarantees": list[str],
        "consumer_requires": list[str],
        "missing_fields": list[str],
        "satisfied": bool,
    },
)


class _ValidationPayload(TypedDict):
    is_valid: bool
    errors: list[_ValidationEntryPayload]
    warnings: list[_ValidationEntryPayload]
    suggestions: list[_ValidationEntryPayload]
    edge_contracts: list[_EdgeContractPayload]


# Composer tools exposed via MCP (excludes blob and secret tools).
_COMPOSER_TOOL_NAMES: frozenset[str] = frozenset(_DISCOVERY_TOOLS) | frozenset(_MUTATION_TOOLS)

# Session tool definitions (added on top of filtered composer tools).
_SESSION_TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "new_session",
        "description": "Create a new empty composition session. Returns session_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Pipeline name (default: 'Untitled Pipeline').",
                },
            },
            "required": [],
        },
    },
    {
        "name": "save_session",
        "description": "Save the current composition state to a session file.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to save to.",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "load_session",
        "description": "Load a previously saved composition session.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to load.",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "list_sessions",
        "description": "List all saved composition sessions.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "delete_session",
        "description": "Delete a saved composition session.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to delete.",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "generate_yaml",
        "description": "Generate ELSPETH pipeline YAML from the current composition state.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]

_SESSION_TOOL_NAMES: frozenset[str] = frozenset(d["name"] for d in _SESSION_TOOL_DEFS)


def _build_tool_defs() -> list[dict[str, Any]]:
    """Build the combined list of tool definitions for MCP registration.

    Filters the web composer tool definitions to only include discovery
    and mutation tools (excluding blob and secret tools), then appends
    the session management tools.

    Returns:
        List of tool definition dicts with ``name``, ``description``,
        and ``parameters`` keys.
    """
    composer_defs = [d for d in get_tool_definitions() if d["name"] in _COMPOSER_TOOL_NAMES]
    return composer_defs + list(_SESSION_TOOL_DEFS)


def _ensure_serializable(obj: Any) -> Any:
    """Recursively convert Pydantic models and other non-serializable types to plain dicts/lists."""
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if isinstance(obj, dict):
        return {k: _ensure_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_ensure_serializable(item) for item in obj]
    return obj


def _dispatch_tool(
    tool_name: str,
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    scratch_dir: Path,
    baseline: CompositionState | None = None,
) -> dict[str, Any]:
    """Dispatch a tool call and return a result dict.

    Session tools are handled locally. Composer tools delegate to
    ``execute_tool()``. Unknown tools return a failure dict.

    The result dict always has ``success``, ``state`` (serialized
    CompositionState), and may include ``data``.
    """
    if tool_name in _SESSION_TOOL_NAMES:
        return _dispatch_session_tool(tool_name, arguments, state, scratch_dir)

    if tool_name in _COMPOSER_TOOL_NAMES:
        result = execute_tool(tool_name, arguments, state, catalog, data_dir=None, baseline=baseline)
        response = result.to_dict()
        response["state"] = result.updated_state.to_dict()
        # Discovery tools return Pydantic models (PluginSummary, PluginSchemaInfo)
        # that aren't JSON-serializable. Recursively convert them.
        if "data" in response:
            response["data"] = _ensure_serializable(response["data"])
        return response

    return {
        "success": False,
        "error": f"Unknown tool: {tool_name}",
        "state": state.to_dict(),
    }


def _edge_contract_to_payload(contract: Any) -> _EdgeContractPayload:
    """Serialize an edge contract without leaking a dict[str, Any] return."""
    payload = contract.to_dict()
    return {
        "from": payload["from"],
        "to": payload["to"],
        "producer_guarantees": payload["producer_guarantees"],
        "consumer_requires": payload["consumer_requires"],
        "missing_fields": payload["missing_fields"],
        "satisfied": payload["satisfied"],
    }


def _validation_to_dict(validation: Any) -> _ValidationPayload:
    """Serialize validation for MCP session-tool error payloads."""
    return {
        "is_valid": validation.is_valid,
        "errors": [entry.to_dict() for entry in validation.errors],
        "warnings": [entry.to_dict() for entry in validation.warnings],
        "suggestions": [entry.to_dict() for entry in validation.suggestions],
        "edge_contracts": [_edge_contract_to_payload(contract) for contract in validation.edge_contracts],
    }


def _dispatch_session_tool(
    tool_name: str,
    arguments: dict[str, Any],
    state: CompositionState,
    scratch_dir: Path,
) -> dict[str, Any]:
    """Handle session management tools."""
    manager = SessionManager(scratch_dir)

    if tool_name == "new_session":
        name = arguments.get("name", "Untitled Pipeline")
        session_id, new_state = manager.new_session(name=name)
        manager.save(session_id, new_state)
        return {
            "success": True,
            "data": {"session_id": session_id, "name": name},
            "state": new_state.to_dict(),
        }

    if tool_name == "save_session":
        session_id = arguments["session_id"]
        manager.save(session_id, state)
        return {
            "success": True,
            "data": {"session_id": session_id},
            "state": state.to_dict(),
        }

    if tool_name == "load_session":
        session_id = arguments["session_id"]
        try:
            loaded = manager.load(session_id)
        except SessionNotFoundError:
            return {
                "success": False,
                "error": f"Session not found: {session_id}",
                "state": state.to_dict(),
            }
        return {
            "success": True,
            "data": {"session_id": session_id},
            "state": loaded.to_dict(),
        }

    if tool_name == "list_sessions":
        sessions = manager.list_sessions()
        return {
            "success": True,
            "data": {"sessions": sessions},
            "state": state.to_dict(),
        }

    if tool_name == "delete_session":
        session_id = arguments["session_id"]
        try:
            manager.delete(session_id)
        except SessionNotFoundError:
            return {
                "success": False,
                "error": f"Session not found: {session_id}",
                "state": state.to_dict(),
            }
        return {
            "success": True,
            "data": {"session_id": session_id},
            "state": state.to_dict(),
        }

    if tool_name == "generate_yaml":
        validation = state.validate()
        if not validation.is_valid:
            return {
                "success": False,
                "error": "Current composition state is invalid. Fix validation errors before calling generate_yaml.",
                "validation": _validation_to_dict(validation),
                "state": state.to_dict(),
            }
        yaml_str = generate_yaml(state)
        return {
            "success": True,
            "data": yaml_str,
            "state": state.to_dict(),
        }

    # Should not be reachable — _SESSION_TOOL_NAMES is derived from
    # _SESSION_TOOL_DEFS which is the only caller path.
    raise AssertionError(f"Unhandled session tool: {tool_name}")


def create_server(
    catalog: CatalogService,
    scratch_dir: Path,
) -> Server:
    """Create an MCP server for pipeline composition.

    Args:
        catalog: Plugin catalog for discovery tools.
        scratch_dir: Directory for session persistence.

    Returns:
        Configured MCP Server ready for stdio transport.
    """
    server = Server("elspeth-composer")

    # Mutable state container — list-of-one pattern allows the
    # inner closures to mutate without nonlocal.
    initial_state = CompositionState(
        source=None,
        nodes=(),
        edges=(),
        outputs=(),
        metadata=PipelineMetadata(),
        version=1,
    )
    state_ref: list[CompositionState] = [initial_state]
    # B5: Baseline for diff_pipeline — captured at session create/load.
    baseline_ref: list[CompositionState] = [initial_state]

    tool_defs = _build_tool_defs()

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=d["name"],
                description=d["description"],
                inputSchema=d["parameters"],
            )
            for d in tool_defs
        ]

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult | list[TextContent]:
        try:
            result = _dispatch_tool(
                name,
                arguments,
                state_ref[0],
                catalog,
                scratch_dir,
                baseline=baseline_ref[0],
            )
        except (ValueError, KeyError, TypeError) as exc:
            # Bad LLM arguments (wrong keys, invalid values) — report to agent
            return CallToolResult(
                content=[TextContent(type="text", text=f"Tool error: {exc!s}")],
                isError=True,
            )

        # Update server-side state from the result (BEFORE redaction —
        # the internal state needs storage paths for pipeline execution).
        if "state" in result:
            new_state = CompositionState.from_dict(result["state"])
            state_ref[0] = new_state
            # Capture baseline when session is created or loaded
            if name in ("new_session", "load_session"):
                baseline_ref[0] = new_state
            # B4: Redact storage paths from the response sent to the agent.
            result["state"] = redact_source_storage_path(result["state"])

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return server


async def run_server(catalog: CatalogService, scratch_dir: Path) -> None:
    """Run the MCP server with stdio transport."""
    server = create_server(catalog, scratch_dir)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    """CLI entry point for elspeth-composer MCP server."""
    parser = argparse.ArgumentParser(
        description="ELSPETH Composer MCP Server",
    )
    parser.add_argument(
        "--scratch-dir",
        type=Path,
        default=Path(".composer-scratch"),
        help="Directory for session persistence (default: .composer-scratch)",
    )
    args = parser.parse_args()

    # Lazy import to avoid pulling in the full catalog at module level.
    from elspeth.web.dependencies import create_catalog_service

    catalog = create_catalog_service()

    import asyncio

    asyncio.run(run_server(catalog, args.scratch_dir))
