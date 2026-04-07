"""Composition tools — discovery and mutation tools for the LLM composer.

Discovery tools delegate to CatalogService. Mutation tools modify
CompositionState and return ToolResult with validation.

Layer: L3 (application). Imports from L0 (contracts.freeze) and
L3 (web/composer/state, web/catalog/protocol).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select

from elspeth.contracts.freeze import deep_thaw, freeze_fields
from elspeth.web.catalog.protocol import CatalogService, PluginKind
from elspeth.web.composer.state import (
    CompositionState,
    EdgeSpec,
    NodeSpec,
    OutputSpec,
    PipelineMetadata,
    SourceSpec,
    ValidationSummary,
)
from elspeth.web.sessions.models import blobs_table

CatalogServiceProtocol = CatalogService  # Re-export for local use


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result of a tool execution.

    Attributes:
        success: Whether the operation succeeded.
        updated_state: Full state after mutation (or original if success=False).
        validation: Stage 1 validation result for the updated state.
        affected_nodes: Node IDs changed or with changed edges.
        data: Optional data payload for discovery tools.
    """

    success: bool
    updated_state: CompositionState
    validation: ValidationSummary
    affected_nodes: tuple[str, ...]
    data: Any = None

    def __post_init__(self) -> None:
        freeze_fields(self, "affected_nodes")
        if self.data is not None:
            freeze_fields(self, "data")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for LLM tool response."""
        result: dict[str, Any] = {
            "success": self.success,
            "validation": {
                "is_valid": self.validation.is_valid,
                "errors": list(self.validation.errors),
                "warnings": list(self.validation.warnings),
                "suggestions": list(self.validation.suggestions),
            },
            "affected_nodes": list(self.affected_nodes),
            "version": self.updated_state.version,
        }
        if self.data is not None:
            result["data"] = deep_thaw(self.data)
        return result


# --- Expression Grammar (static) ---

_EXPRESSION_GRAMMAR = """\
Gate Expression Syntax Reference
=================================

Variables:
  row      - The current row as a dict. Access fields via row['field_name'].

Field access:
  row['field_name']       Direct access (raises KeyError if missing)
  row.get('field_name')   Returns None if missing (NO default argument allowed)

Operators:
  ==, !=, <, >, <=, >=   Comparison
  and, or, not            Boolean logic
  in, not in              Membership test
  +, -, *, /, //, %       Arithmetic

Built-in functions (only these are allowed):
  len()    Length of a sequence or string
  abs()    Absolute value of a number

Type coercion functions (int, str, float, bool) are NOT available.
Types are guaranteed by the source schema — no coercion is needed in expressions.

Examples:
  row['confidence'] >= 0.85
  row['status'] == 'approved'
  row['category'] in ('A', 'B', 'C')
  row.get('optional_field') is not None
  row['score'] > 0.5 and row['status'] != 'rejected'
  len(row['name']) > 0

Forbidden:
  row.get('field', default)   Default values fabricate data — use 'is not None' test
  int(row['x'])               Type coercion — coerce at source schema instead
  Imports, lambdas, comprehensions, attribute access (except row.get)
"""


def get_expression_grammar() -> str:
    """Return the gate expression syntax reference."""
    return _EXPRESSION_GRAMMAR


# --- Tool Definitions for LLM ---


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return JSON Schema tool definitions for the LLM.

    Returns 27 tools: 8 discovery + 13 mutation + 3 blob tools + 3 secret tools.
    """
    return [
        # Discovery tools
        {
            "name": "list_sources",
            "description": "List available source plugins with name and summary.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "list_transforms",
            "description": "List available transform plugins with name and summary.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "list_sinks",
            "description": "List available sink plugins with name and summary.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_plugin_schema",
            "description": "Get the full configuration schema for a plugin.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plugin_type": {
                        "type": "string",
                        "enum": ["source", "transform", "sink"],
                        "description": "Plugin type.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Plugin name (e.g. 'csv').",
                    },
                },
                "required": ["plugin_type", "name"],
            },
        },
        {
            "name": "get_expression_grammar",
            "description": "Get the gate expression syntax reference.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        # Mutation tools
        {
            "name": "set_source",
            "description": "Set or replace the pipeline source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plugin": {"type": "string", "description": "Source plugin name."},
                    "on_success": {"type": "string", "description": "Connection name for downstream."},
                    "options": {"type": "object", "description": "Plugin-specific config."},
                    "on_validation_failure": {
                        "type": "string",
                        "enum": ["discard", "quarantine"],
                        "description": "How to handle validation failures.",
                    },
                },
                "required": ["plugin", "on_success", "options", "on_validation_failure"],
            },
        },
        {
            "name": "upsert_node",
            "description": "Add or update a pipeline node (transform, gate, aggregation, coalesce).",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique node identifier."},
                    "node_type": {
                        "type": "string",
                        "enum": ["transform", "gate", "aggregation", "coalesce"],
                    },
                    "plugin": {"type": ["string", "null"], "description": "Plugin name. Null for gates/coalesces."},
                    "input": {"type": "string", "description": "Input connection name."},
                    "on_success": {"type": ["string", "null"], "description": "Output connection. Null for gates."},
                    "on_error": {"type": ["string", "null"], "description": "Error output connection."},
                    "options": {"type": "object", "description": "Plugin-specific config."},
                    "condition": {"type": ["string", "null"], "description": "Gate expression."},
                    "routes": {"type": ["object", "null"], "description": "Gate route mapping."},
                    "fork_to": {"type": ["array", "null"], "items": {"type": "string"}, "description": "Fork destinations."},
                    "branches": {"type": ["array", "null"], "items": {"type": "string"}, "description": "Coalesce branch inputs."},
                    "policy": {"type": ["string", "null"], "description": "Coalesce policy."},
                    "merge": {"type": ["string", "null"], "description": "Coalesce merge strategy."},
                },
                "required": ["id", "node_type", "input"],
            },
        },
        {
            "name": "upsert_edge",
            "description": "Add or update a connection between nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique edge identifier."},
                    "from_node": {"type": "string", "description": "Source node ID or 'source'."},
                    "to_node": {"type": "string", "description": "Destination node ID or sink name."},
                    "edge_type": {
                        "type": "string",
                        "enum": ["on_success", "on_error", "route_true", "route_false", "fork"],
                    },
                    "label": {"type": ["string", "null"], "description": "Display label."},
                },
                "required": ["id", "from_node", "to_node", "edge_type"],
            },
        },
        {
            "name": "remove_node",
            "description": "Remove a node and all its edges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Node ID to remove."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "remove_edge",
            "description": "Remove an edge by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Edge ID to remove."},
                },
                "required": ["id"],
            },
        },
        {
            "name": "set_metadata",
            "description": "Update pipeline metadata (name and description only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "object",
                        "description": "Partial metadata update. Only included fields are changed.",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
                "required": ["patch"],
            },
        },
        {
            "name": "set_output",
            "description": "Add or replace a pipeline output (sink).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sink_name": {"type": "string", "description": "Sink name (connection point for edges/routes)."},
                    "plugin": {"type": "string", "description": "Sink plugin name (e.g. 'csv', 'json')."},
                    "options": {"type": "object", "description": "Plugin-specific config."},
                    "on_write_failure": {
                        "type": "string",
                        "enum": ["discard", "quarantine"],
                        "description": "How to handle write failures.",
                        "default": "discard",
                    },
                },
                "required": ["sink_name", "plugin", "options"],
            },
        },
        {
            "name": "remove_output",
            "description": "Remove a pipeline output (sink) by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sink_name": {"type": "string", "description": "Sink name to remove."},
                },
                "required": ["sink_name"],
            },
        },
        {
            "name": "patch_source_options",
            "description": "Apply a shallow merge-patch to the current source options. "
            "Keys in the patch overwrite existing keys. "
            "Keys set to null are deleted. Missing keys are unchanged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch": {
                        "type": "object",
                        "description": "Merge-patch to apply to source options.",
                    },
                },
                "required": ["patch"],
            },
        },
        {
            "name": "patch_node_options",
            "description": "Apply a shallow merge-patch to a node's options. "
            "Keys in the patch overwrite existing keys. "
            "Keys set to null are deleted. Missing keys are unchanged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "ID of the node to patch.",
                    },
                    "patch": {
                        "type": "object",
                        "description": "Merge-patch to apply to node options.",
                    },
                },
                "required": ["node_id", "patch"],
            },
        },
        {
            "name": "patch_output_options",
            "description": "Apply a shallow merge-patch to an output's options. "
            "Keys in the patch overwrite existing keys. "
            "Keys set to null are deleted. Missing keys are unchanged.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sink_name": {
                        "type": "string",
                        "description": "Name of the output (sink) to patch.",
                    },
                    "patch": {
                        "type": "object",
                        "description": "Merge-patch to apply to output options.",
                    },
                },
                "required": ["sink_name", "patch"],
            },
        },
        {
            "name": "set_pipeline",
            "description": "Atomically replace the entire pipeline. Provide the "
            "complete source, nodes, edges, outputs, and metadata in one call. "
            "This is more efficient than calling set_source + upsert_node + "
            "upsert_edge + set_output sequentially.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "object",
                        "description": "Source configuration: {plugin, options, on_success, on_validation_failure?}",
                    },
                    "nodes": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of node specs: [{id, input, plugin?, node_type, options?, on_success?, on_error?, condition?, routes?, fork_to?, branches?, policy?, merge?}]",
                    },
                    "edges": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of edge specs: [{id, from_node, to_node, edge_type}]",
                    },
                    "outputs": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "Array of output specs: [{name, plugin, options, on_write_failure?}]",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Pipeline metadata: {name?, description?}",
                    },
                },
                "required": ["source", "nodes", "edges", "outputs"],
            },
        },
        # Wave 4 tools
        {
            "name": "clear_source",
            "description": "Remove the source from the pipeline composition state.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "explain_validation_error",
            "description": "Get a human-readable explanation of a validation error "
            "with suggested fixes. Pass the exact error text from a validation result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_text": {
                        "type": "string",
                        "description": "The validation error message to explain.",
                    },
                },
                "required": ["error_text"],
            },
        },
        {
            "name": "list_models",
            "description": "List available LLM model identifiers that can be used "
            "in LLM transform nodes. Optionally filter by provider prefix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "Optional provider prefix to filter by (e.g. 'openrouter/', 'azure/').",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "preview_pipeline",
            "description": "Preview the current pipeline configuration — returns "
            "validation status, source summary, and node/output overview "
            "without executing. Use this to confirm the pipeline is set up "
            "correctly before running.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        # Blob tools
        {
            "name": "list_blobs",
            "description": "List uploaded/created files (blobs) in this session with metadata.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_blob_metadata",
            "description": "Get metadata for a specific blob (file) by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_id": {"type": "string", "description": "Blob ID."},
                },
                "required": ["blob_id"],
            },
        },
        {
            "name": "set_source_from_blob",
            "description": "Wire a blob as the pipeline source. Resolves the blob's storage path internally and infers the source plugin from its MIME type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_id": {"type": "string", "description": "Blob ID to use as source."},
                    "plugin": {"type": "string", "description": "Source plugin override (e.g. 'csv'). Inferred from MIME type if omitted."},
                    "on_success": {"type": "string", "description": "Node ID to route rows to after source."},
                    "on_validation_failure": {
                        "type": "string",
                        "enum": ["quarantine", "discard"],
                        "description": "How to handle validation failures.",
                        "default": "quarantine",
                    },
                },
                "required": ["blob_id", "on_success"],
            },
        },
        # Secret tools
        {
            "name": "list_secret_refs",
            "description": "List available secret references (API keys, credentials). Shows names and scopes, never values.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "validate_secret_ref",
            "description": "Check if a secret reference exists and is accessible to the current user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Secret reference name (e.g. 'OPENROUTER_API_KEY')."},
                },
                "required": ["name"],
            },
        },
        {
            "name": "wire_secret_ref",
            "description": "Place a secret reference marker in the pipeline config. The secret will be resolved at execution time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Secret reference name."},
                    "target": {
                        "type": "string",
                        "enum": ["source", "node", "output"],
                        "description": "Which component to wire the secret into.",
                    },
                    "target_id": {"type": "string", "description": "Node ID or output name (required for node/output targets)."},
                    "option_key": {"type": "string", "description": "Config option key to set (e.g. 'api_key')."},
                },
                "required": ["name", "target", "option_key"],
            },
        },
    ]


# --- Tool Registry ---

# Unified handler signature: (arguments, state, catalog, data_dir) -> ToolResult.
# Handlers that don't need all parameters ignore them.
ToolHandler = Callable[
    [dict[str, Any], CompositionState, CatalogServiceProtocol, str | None],
    ToolResult,
]


# Discovery tool handlers (normalized signatures)


def _handle_list_sources(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, catalog.list_sources())


def _handle_list_transforms(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, catalog.list_transforms())


def _handle_list_sinks(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, catalog.list_sinks())


def _handle_get_plugin_schema(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    try:
        schema = catalog.get_schema(arguments["plugin_type"], arguments["name"])
        return _discovery_result(state, schema)
    except (ValueError, KeyError) as exc:
        # ValueError: catalog contract for "unknown plugin/type"
        # KeyError: LLM omitted required argument (Tier 3)
        return _failure_result(state, str(exc))


def _handle_get_expression_grammar(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, get_expression_grammar())


# Mutation tool handler wrappers (normalize 2/3-arg handlers to 4-arg)


def _handle_upsert_node(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_upsert_node(arguments, state, catalog)


def _handle_upsert_edge(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_upsert_edge(arguments, state)


def _handle_remove_node(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_remove_node(arguments, state)


def _handle_remove_edge(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_remove_edge(arguments, state)


def _handle_set_metadata(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_set_metadata(arguments, state)


def _handle_set_output(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_set_output(arguments, state, catalog)


def _handle_remove_output(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_remove_output(arguments, state)


def _discovery_result(state: CompositionState, data: Any) -> ToolResult:
    """Build a ToolResult for a discovery (read-only) tool."""
    validation = state.validate()
    return ToolResult(
        success=True,
        updated_state=state,
        validation=validation,
        affected_nodes=(),
        data=data,
    )


def _failure_result(
    state: CompositionState,
    error_msg: str,
) -> ToolResult:
    """Build a ToolResult for a failed mutation."""
    validation = state.validate()
    return ToolResult(
        success=False,
        updated_state=state,
        validation=validation,
        affected_nodes=(),
        data={"error": error_msg},
    )


def _mutation_result(
    new_state: CompositionState,
    affected: tuple[str, ...],
) -> ToolResult:
    """Build a ToolResult for a successful mutation."""
    validation = new_state.validate()
    return ToolResult(
        success=True,
        updated_state=new_state,
        validation=validation,
        affected_nodes=affected,
    )


def _apply_merge_patch(
    target: Mapping[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Shallow merge-patch: overwrite or delete top-level keys in target."""
    result = dict(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


def _validate_plugin_name(
    catalog: CatalogServiceProtocol,
    plugin_type: PluginKind,
    name: str,
) -> str | None:
    """Return an error message if the plugin name is not in the catalog, or None if valid."""
    try:
        catalog.get_schema(plugin_type, name)
    except (ValueError, KeyError) as exc:
        return f"Unknown {plugin_type} plugin '{name}': {exc}"
    return None


# --- Blob helpers (sync — called from worker thread via compose()) ---

_MIME_TO_SOURCE_PLUGIN: dict[str, str] = {
    "text/csv": "csv",
    "application/json": "json",
    "application/x-jsonlines": "jsonl",
    "application/jsonl": "jsonl",
    "text/jsonl": "jsonl",
    "text/plain": "text",
}


def _sync_get_blob(engine: Engine, blob_id: str, session_id: str | None = None) -> dict[str, Any] | None:
    """Synchronous blob lookup for use in the tool executor thread."""
    with engine.connect() as conn:
        query = select(blobs_table).where(blobs_table.c.id == blob_id)
        if session_id is not None:
            query = query.where(blobs_table.c.session_id == session_id)
        row = conn.execute(query).first()
        if row is None:
            return None
        return {
            "id": row.id,
            "session_id": row.session_id,
            "filename": row.filename,
            "mime_type": row.mime_type,
            "size_bytes": row.size_bytes,
            "content_hash": row.content_hash,
            "storage_path": row.storage_path,
            "created_by": row.created_by,
            "source_description": row.source_description,
            "status": row.status,
        }


def _sync_list_blobs(engine: Engine, session_id: str) -> list[dict[str, Any]]:
    """Synchronous blob listing for use in the tool executor thread."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(blobs_table).where(blobs_table.c.session_id == session_id).order_by(blobs_table.c.created_at.desc()).limit(50)
        ).fetchall()
        return [
            {
                "id": row.id,
                "filename": row.filename,
                "mime_type": row.mime_type,
                "size_bytes": row.size_bytes,
                "created_by": row.created_by,
                "status": row.status,
            }
            for row in rows
        ]


def _allowed_source_directories(data_dir: str) -> tuple[Path, ...]:
    """Return the set of directories from which source paths are allowed.

    AD-4: Single shared helper used by composer tool validation,
    execution validation, and execution runtime guard.
    """
    base = Path(data_dir).resolve()
    return (base / "uploads", base / "blobs")


def _allowed_sink_directories(data_dir: str) -> tuple[Path, ...]:
    """Return the set of directories to which sink paths may write.

    AD-4 extension: Mirrors _allowed_source_directories for output paths.
    Sinks write to data_dir/outputs (not uploads, which is for ingestion).
    """
    base = Path(data_dir).resolve()
    return (base / "outputs", base / "blobs")


def _validate_source_path(
    options: dict[str, Any],
    data_dir: str | None,
) -> str | None:
    """S2: Validate that path/file options are under allowed source directories.

    Returns an error message if validation fails, None if OK.
    Uses Path.resolve() + is_relative_to() to defeat ../ traversal.
    """
    if data_dir is None:
        return None

    allowed = _allowed_source_directories(data_dir)

    for key in ("path", "file"):
        if key in options:
            raw = Path(options[key])
            resolved = (Path(data_dir).resolve() / raw).resolve() if not raw.is_absolute() else raw.resolve()
            if not any(resolved.is_relative_to(d) for d in allowed):
                return (
                    f"Path violation (S2): '{options[key]}' is outside the "
                    f"allowed directories. Source file paths "
                    f"must be under {data_dir}/uploads/ or {data_dir}/blobs/."
                )
    return None


def _execute_set_source(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    """Set or replace the pipeline source."""
    plugin = args["plugin"]
    # Validate plugin exists in catalog
    plugin_error = _validate_plugin_name(catalog, "source", plugin)
    if plugin_error is not None:
        return _failure_result(state, plugin_error)

    # S2: Validate source path allowlist
    options = args.get("options", {})
    path_error = _validate_source_path(options, data_dir)
    if path_error is not None:
        return _failure_result(state, path_error)

    source = SourceSpec(
        plugin=plugin,
        on_success=args["on_success"],
        options=options,
        on_validation_failure=args.get("on_validation_failure", "quarantine"),
    )
    new_state = state.with_source(source)
    return _mutation_result(new_state, ("source",))


def _execute_upsert_node(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
) -> ToolResult:
    """Add or update a pipeline node."""
    node_type = args["node_type"]
    plugin = args.get("plugin")

    # Validate plugin for types that require one
    if node_type in ("transform", "aggregation") and plugin is not None:
        plugin_error = _validate_plugin_name(catalog, "transform", plugin)
        if plugin_error is not None:
            return _failure_result(state, plugin_error)

    fork_to = args.get("fork_to")
    if fork_to is not None:
        fork_to = tuple(fork_to)

    branches = args.get("branches")
    if branches is not None:
        branches = tuple(branches)

    node = NodeSpec(
        id=args["id"],
        node_type=node_type,
        plugin=plugin,
        input=args["input"],
        on_success=args.get("on_success"),
        on_error=args.get("on_error"),
        options=args.get("options", {}),
        condition=args.get("condition"),
        routes=args.get("routes"),
        fork_to=fork_to,
        branches=branches,
        policy=args.get("policy"),
        merge=args.get("merge"),
    )

    node_id = args["id"]
    new_state = state.with_node(node)

    # Affected: the node itself plus nodes with edges referencing it
    affected = {node_id}
    for edge in new_state.edges:
        if edge.from_node == node_id or edge.to_node == node_id:
            affected.add(edge.from_node)
            affected.add(edge.to_node)

    return _mutation_result(new_state, tuple(sorted(affected)))


def _execute_upsert_edge(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    """Add or update an edge.

    When the edge targets an output (sink), synchronises the source
    node's connection field so that generate_yaml() produces a
    working pipeline.  Edges to non-output nodes are visual only.
    """
    from_node = args["from_node"]
    to_node = args["to_node"]
    edge_type = args["edge_type"]

    edge = EdgeSpec(
        id=args["id"],
        from_node=from_node,
        to_node=to_node,
        edge_type=edge_type,
        label=args.get("label"),
    )
    new_state = state.with_edge(edge)

    # Synchronise connection field when the edge targets an output.
    # generate_yaml() and the engine use on_success/on_error values
    # (not edges) to route data to sinks, so the connection field
    # must match the output name for the pipeline to work at runtime.
    output_names = {o.name for o in new_state.outputs}
    if to_node in output_names:
        if from_node == "source" and edge_type == "on_success":
            if new_state.source is not None and new_state.source.on_success != to_node:
                new_source = replace(new_state.source, on_success=to_node)
                new_state = new_state.with_source(new_source)
        else:
            node = next((n for n in new_state.nodes if n.id == from_node), None)
            if node is not None:
                if edge_type == "on_success" and node.on_success != to_node:
                    new_state = new_state.with_node(replace(node, on_success=to_node))
                elif edge_type == "on_error" and node.on_error != to_node:
                    new_state = new_state.with_node(replace(node, on_error=to_node))

    return _mutation_result(new_state, (from_node, to_node))


def _execute_remove_node(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    """Remove a node and its edges."""
    node_id = args["id"]

    # Collect affected nodes before removal (edges that reference this node)
    affected = {node_id}
    for edge in state.edges:
        if edge.from_node == node_id or edge.to_node == node_id:
            affected.add(edge.from_node)
            affected.add(edge.to_node)

    new_state = state.without_node(node_id)
    if new_state is None:
        return _failure_result(state, f"Node '{node_id}' not found.")

    return _mutation_result(new_state, tuple(sorted(affected)))


def _execute_remove_edge(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    """Remove an edge."""
    edge_id = args["id"]

    # Find the edge to get affected nodes
    edge = next((e for e in state.edges if e.id == edge_id), None)
    if edge is None:
        return _failure_result(state, f"Edge '{edge_id}' not found.")

    affected = (edge.from_node, edge.to_node)
    new_state = state.without_edge(edge_id)
    if new_state is None:
        return _failure_result(state, f"Edge '{edge_id}' not found.")

    return _mutation_result(new_state, affected)


def _execute_set_metadata(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    """Update pipeline metadata."""
    patch = args["patch"]

    new_state = state.with_metadata(patch)
    return _mutation_result(new_state, ())


def _execute_set_output(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
) -> ToolResult:
    """Add or replace a pipeline output (sink)."""
    plugin = args["plugin"]
    # Validate plugin exists in catalog
    plugin_error = _validate_plugin_name(catalog, "sink", plugin)
    if plugin_error is not None:
        return _failure_result(state, plugin_error)

    output = OutputSpec(
        name=args["sink_name"],
        plugin=plugin,
        options=args.get("options", {}),
        on_write_failure=args.get("on_write_failure", "discard"),
    )
    new_state = state.with_output(output)
    return _mutation_result(new_state, (args["sink_name"],))


def _execute_remove_output(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    """Remove a pipeline output (sink) by name."""
    sink_name = args["sink_name"]
    new_state = state.without_output(sink_name)
    if new_state is None:
        return _failure_result(state, f"Output '{sink_name}' not found.")
    return _mutation_result(new_state, (sink_name,))


# --- Blob tool handlers ---


def _handle_list_blobs(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")
    blobs = _sync_list_blobs(session_engine, session_id)
    return _discovery_result(state, blobs)


def _handle_get_blob_metadata(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")
    blob = _sync_get_blob(session_engine, arguments["blob_id"], session_id)
    if blob is None:
        return _failure_result(state, f"Blob '{arguments['blob_id']}' not found.")
    # Exclude storage_path from response
    safe_blob = {k: v for k, v in blob.items() if k != "storage_path"}
    return _discovery_result(state, safe_blob)


def _execute_set_source_from_blob(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")
    blob = _sync_get_blob(session_engine, arguments["blob_id"], session_id)
    if blob is None:
        return _failure_result(state, f"Blob '{arguments['blob_id']}' not found.")

    if blob["status"] != "ready":
        return _failure_result(state, f"Blob is not ready (status: {blob['status']}).")

    # Determine source plugin
    plugin = arguments.get("plugin") or _MIME_TO_SOURCE_PLUGIN.get(blob["mime_type"])
    if plugin is None:
        return _failure_result(
            state,
            f"Cannot infer source plugin for MIME type '{blob['mime_type']}'. Please specify the 'plugin' parameter explicitly.",
        )

    # Validate plugin exists
    try:
        catalog.get_schema("source", plugin)
    except (ValueError, KeyError) as exc:
        return _failure_result(state, f"Unknown source plugin '{plugin}': {exc}")

    source = SourceSpec(
        plugin=plugin,
        on_success=arguments["on_success"],
        options={"path": blob["storage_path"], "blob_ref": blob["id"]},
        on_validation_failure=arguments.get("on_validation_failure", "quarantine"),
    )
    new_state = state.with_source(source)
    return _mutation_result(new_state, ("source",))


# Blob tool handler type — extended signature with session context
BlobToolHandler = Callable[..., ToolResult]

# --- Secret tool handlers ---

# Secret tool handler type — extended signature with secret_service + user_id
SecretToolHandler = Callable[..., ToolResult]


def _handle_list_secret_refs(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    *,
    secret_service: Any | None = None,
    user_id: str | None = None,
) -> ToolResult:
    if secret_service is None or user_id is None:
        return _failure_result(state, "Secret tools require secret service context.")
    items = secret_service.list_refs(user_id)
    # Return inventory dicts — NEVER include values
    data = [{"name": item.name, "scope": item.scope, "available": item.available} for item in items]
    return _discovery_result(state, data)


def _handle_validate_secret_ref(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    *,
    secret_service: Any | None = None,
    user_id: str | None = None,
) -> ToolResult:
    if secret_service is None or user_id is None:
        return _failure_result(state, "Secret tools require secret service context.")
    name = arguments["name"]
    available = secret_service.has_ref(user_id, name)
    return _discovery_result(state, {"name": name, "available": available})


def _execute_wire_secret_ref(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    *,
    secret_service: Any | None = None,
    user_id: str | None = None,
) -> ToolResult:
    if secret_service is None or user_id is None:
        return _failure_result(state, "Secret tools require secret service context.")

    name = arguments["name"]
    target = arguments["target"]
    option_key = arguments["option_key"]
    target_id = arguments.get("target_id")

    # Validate the secret ref exists
    if not secret_service.has_ref(user_id, name):
        return _failure_result(state, f"Secret reference '{name}' not found or not accessible.")

    marker = {"secret_ref": name}

    if target == "source":
        if state.source is None:
            return _failure_result(state, "No source configured — set a source first.")
        patched_options = dict(deep_thaw(state.source.options))
        patched_options[option_key] = marker
        new_source = SourceSpec(
            plugin=state.source.plugin,
            on_success=state.source.on_success,
            options=patched_options,
            on_validation_failure=state.source.on_validation_failure,
        )
        new_state = state.with_source(new_source)
        return _mutation_result(new_state, ("source",))

    elif target == "node":
        if target_id is None:
            return _failure_result(state, "target_id is required for node targets.")
        node = next((n for n in state.nodes if n.id == target_id), None)
        if node is None:
            return _failure_result(state, f"Node '{target_id}' not found.")
        patched_options = dict(deep_thaw(node.options))
        patched_options[option_key] = marker
        new_node = NodeSpec(
            id=node.id,
            node_type=node.node_type,
            plugin=node.plugin,
            input=node.input,
            on_success=node.on_success,
            on_error=node.on_error,
            options=patched_options,
            condition=node.condition,
            routes=deep_thaw(node.routes) if node.routes is not None else None,
            fork_to=node.fork_to,
            branches=node.branches,
            policy=node.policy,
            merge=node.merge,
        )
        new_state = state.with_node(new_node)
        return _mutation_result(new_state, (target_id,))

    elif target == "output":
        if target_id is None:
            return _failure_result(state, "target_id is required for output targets.")
        output = next((o for o in state.outputs if o.name == target_id), None)
        if output is None:
            return _failure_result(state, f"Output '{target_id}' not found.")
        patched_options = dict(deep_thaw(output.options))
        patched_options[option_key] = marker
        new_output = OutputSpec(
            name=output.name,
            plugin=output.plugin,
            options=patched_options,
            on_write_failure=output.on_write_failure,
        )
        new_state = state.with_output(new_output)
        return _mutation_result(new_state, (target_id,))

    else:
        return _failure_result(state, f"Unknown target type: '{target}'.")


# --- Atomic set_pipeline handler ---


def _execute_set_pipeline(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    """Atomically replace the entire pipeline composition state."""
    # 1. Validate source plugin
    src_args = args["source"]
    src_plugin = src_args["plugin"]
    plugin_error = _validate_plugin_name(catalog, "source", src_plugin)
    if plugin_error is not None:
        return _failure_result(state, plugin_error)

    # S2: Validate source path allowlist (same check as _execute_set_source)
    src_options = src_args.get("options", {})
    path_error = _validate_source_path(src_options, data_dir)
    if path_error is not None:
        return _failure_result(state, path_error)

    # 2. Validate node plugins
    for node_args in args["nodes"]:
        node_type = node_args["node_type"]
        node_plugin = node_args.get("plugin")
        if node_type in ("transform", "aggregation") and node_plugin is not None:
            plugin_error = _validate_plugin_name(catalog, "transform", node_plugin)
            if plugin_error is not None:
                return _failure_result(state, plugin_error)

    # 3. Validate output plugins
    for out_args in args["outputs"]:
        out_plugin = out_args["plugin"]
        plugin_error = _validate_plugin_name(catalog, "sink", out_plugin)
        if plugin_error is not None:
            return _failure_result(state, plugin_error)

    # 4. Construct specs (same field extraction as individual handlers)
    try:
        source_spec = SourceSpec(
            plugin=src_plugin,
            on_success=src_args["on_success"],
            options=src_args.get("options", {}),
            on_validation_failure=src_args.get("on_validation_failure", "quarantine"),
        )

        node_specs = []
        for n in args["nodes"]:
            fork_to = n.get("fork_to")
            if fork_to is not None:
                fork_to = tuple(fork_to)
            branches = n.get("branches")
            if branches is not None:
                branches = tuple(branches)
            node_specs.append(
                NodeSpec(
                    id=n["id"],
                    node_type=n["node_type"],
                    plugin=n.get("plugin"),
                    input=n["input"],
                    on_success=n.get("on_success"),
                    on_error=n.get("on_error"),
                    options=n.get("options", {}),
                    condition=n.get("condition"),
                    routes=n.get("routes"),
                    fork_to=fork_to,
                    branches=branches,
                    policy=n.get("policy"),
                    merge=n.get("merge"),
                )
            )

        edge_specs = []
        for e in args["edges"]:
            edge_specs.append(
                EdgeSpec(
                    id=e["id"],
                    from_node=e["from_node"],
                    to_node=e["to_node"],
                    edge_type=e["edge_type"],
                    label=e.get("label"),
                )
            )

        output_specs = []
        for o in args["outputs"]:
            output_specs.append(
                OutputSpec(
                    name=o["name"],
                    plugin=o["plugin"],
                    options=o.get("options", {}),
                    on_write_failure=o.get("on_write_failure", "discard"),
                )
            )

        meta_raw = args.get("metadata")
        if meta_raw is None:
            meta = {}
        elif isinstance(meta_raw, dict):
            meta = meta_raw
        else:
            return _failure_result(state, "metadata must be an object.")
        metadata_spec = PipelineMetadata(
            name=meta.get("name", "Untitled Pipeline"),
            description=meta.get("description", ""),
        )
    except (KeyError, TypeError) as exc:
        return _failure_result(state, f"Invalid pipeline spec: {exc}")

    # 5. Build new state
    new_state = CompositionState(
        source=source_spec,
        nodes=tuple(node_specs),
        edges=tuple(edge_specs),
        outputs=tuple(output_specs),
        metadata=metadata_spec,
        version=state.version + 1,
    )

    # 6. Report all nodes + source + outputs as affected
    affected = ("source", *(n.id for n in node_specs), *(o.name for o in output_specs))
    return _mutation_result(new_state, affected)


def _handle_set_pipeline(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_set_pipeline(arguments, state, catalog, data_dir)


# --- Merge-patch mutation handlers ---


def _execute_patch_source_options(
    args: dict[str, Any],
    state: CompositionState,
    data_dir: str | None = None,
) -> ToolResult:
    if state.source is None:
        return _failure_result(state, "No source configured to patch.")
    patch = args["patch"]
    if not isinstance(patch, dict):
        return _failure_result(state, "patch must be an object.")
    new_options = _apply_merge_patch(state.source.options, patch)

    # S2: Validate patched source paths against allowlist
    path_error = _validate_source_path(new_options, data_dir)
    if path_error is not None:
        return _failure_result(state, path_error)

    new_source = SourceSpec(
        plugin=state.source.plugin,
        options=new_options,
        on_success=state.source.on_success,
        on_validation_failure=state.source.on_validation_failure,
    )
    new_state = state.with_source(new_source)
    return _mutation_result(new_state, ("source",))


def _handle_patch_source_options(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_patch_source_options(arguments, state, data_dir)


def _execute_patch_node_options(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    node_id = args["node_id"]
    patch = args["patch"]
    if not isinstance(patch, dict):
        return _failure_result(state, "patch must be an object.")
    current = next((n for n in state.nodes if n.id == node_id), None)
    if current is None:
        return _failure_result(state, f"Node '{node_id}' not found.")
    new_options = _apply_merge_patch(current.options, patch)
    new_node = NodeSpec(
        id=current.id,
        node_type=current.node_type,
        plugin=current.plugin,
        input=current.input,
        on_success=current.on_success,
        on_error=current.on_error,
        options=new_options,
        condition=current.condition,
        routes=current.routes,
        fork_to=current.fork_to,
        branches=current.branches,
        policy=current.policy,
        merge=current.merge,
    )
    new_state = state.with_node(new_node)
    return _mutation_result(new_state, (node_id,))


def _handle_patch_node_options(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_patch_node_options(arguments, state)


def _execute_patch_output_options(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    sink_name = args["sink_name"]
    patch = args["patch"]
    if not isinstance(patch, dict):
        return _failure_result(state, "patch must be an object.")
    current = next((o for o in state.outputs if o.name == sink_name), None)
    if current is None:
        return _failure_result(state, f"Output '{sink_name}' not found.")
    new_options = _apply_merge_patch(current.options, patch)
    new_output = OutputSpec(
        name=current.name,
        plugin=current.plugin,
        options=new_options,
        on_write_failure=current.on_write_failure,
    )
    new_state = state.with_output(new_output)
    return _mutation_result(new_state, (sink_name,))


def _handle_patch_output_options(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_patch_output_options(arguments, state)


# --- Wave 4 handlers ---


def _execute_clear_source(
    args: dict[str, Any],
    state: CompositionState,
) -> ToolResult:
    """Remove the pipeline source."""
    if state.source is None:
        return _failure_result(state, "No source configured to clear.")
    new_state = state.without_source()
    return _mutation_result(new_state, ("source",))


def _handle_clear_source(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_clear_source(arguments, state)


# Validation error pattern catalogue for explain_validation_error.
# Each entry: (regex pattern, explanation, suggested fix).
_VALIDATION_ERROR_PATTERNS: list[tuple[str, str, str]] = [
    (
        r"No source configured",
        "The pipeline has no data source. Every pipeline needs exactly one source to read input data from.",
        "Use set_source to configure a source plugin (e.g. csv, json, dataverse).",
    ),
    (
        r"No sinks configured",
        "The pipeline has no outputs. At least one sink is needed to write results.",
        "Use set_output to add an output (e.g. csv, json).",
    ),
    (
        r"references unknown node '(.+)' as from_node",
        "An edge references a node that doesn't exist in the pipeline as its source.",
        "Check the edge's from_node value. Either add the missing node with upsert_node or fix the edge with upsert_edge.",
    ),
    (
        r"references unknown node '(.+)' as to_node",
        "An edge references a node or output that doesn't exist in the pipeline as its target.",
        "Check the edge's to_node value. Either add the missing node/output or fix the edge.",
    ),
    (
        r"Duplicate node ID: '(.+)'",
        "Two nodes have the same ID. Each node must have a unique identifier.",
        "Rename one of the duplicate nodes using upsert_node with a different id.",
    ),
    (
        r"Duplicate output name: '(.+)'",
        "Two outputs have the same name. Each output must have a unique name.",
        "Rename one of the duplicate outputs using set_output with a different sink_name.",
    ),
    (
        r"Duplicate edge ID: '(.+)'",
        "Two edges have the same ID. Each edge must have a unique identifier.",
        "Remove the duplicate edge with remove_edge and re-add with a unique id.",
    ),
    (
        r"Gate '(.+)' is missing required field '(.+)'",
        "A gate node is missing a required configuration field (condition or routes).",
        "Update the gate with upsert_node, providing the missing field.",
    ),
    (
        r"Transform '(.+)' must not have '(.+)' field",
        "A transform node has a field that only gates should have (condition or routes).",
        "Update the node with upsert_node. Set node_type to 'gate' if routing is needed, or remove the field.",
    ),
    (
        r"Coalesce '(.+)' is missing required field '(.+)'",
        "A coalesce node is missing a required field (branches or policy).",
        "Update the coalesce node with upsert_node, providing the missing field.",
    ),
    (
        r"Aggregation '(.+)' is missing required field 'plugin'",
        "An aggregation node needs a plugin to define its aggregation behaviour.",
        "Update the aggregation with upsert_node, specifying the plugin name.",
    ),
    (
        r"input '(.+)' is not reachable",
        "A node's input connection point is not connected to any edge or the source's on_success target.",
        "Either add an edge targeting this node, or set the source's on_success to match the node's input.",
    ),
    (
        r"Unknown .+ plugin '(.+)'",
        "The specified plugin name is not available in the catalog.",
        "Use list_sources, list_transforms, or list_sinks to see available plugins.",
    ),
    (
        r"Path violation \(S2\)",
        "The source file path is outside the allowed directories.",
        "Source paths must be under the uploads/ or blobs/ directory. Upload a file first or use set_source_from_blob.",
    ),
]


def _execute_explain_validation_error(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    """Explain a validation error with human-readable diagnosis and fix."""
    import re

    error_text = args["error_text"]
    for pattern, explanation, fix in _VALIDATION_ERROR_PATTERNS:
        if re.search(pattern, error_text):
            return ToolResult(
                success=True,
                updated_state=state,
                validation=state.validate(),
                affected_nodes=(),
                data={
                    "error_text": error_text,
                    "explanation": explanation,
                    "suggested_fix": fix,
                },
            )
    # No match — return a generic response
    return ToolResult(
        success=True,
        updated_state=state,
        validation=state.validate(),
        affected_nodes=(),
        data={
            "error_text": error_text,
            "explanation": "This error is not in the known pattern catalogue.",
            "suggested_fix": "Review the error message and the pipeline structure. Use get_pipeline_state to inspect the current composition.",
        },
    )


def _execute_list_models(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    """List available LLM model identifiers."""
    try:
        import litellm

        all_models: list[str] = sorted(litellm.model_list)
    except (ImportError, AttributeError):
        all_models = []

    provider = args.get("provider")
    if provider and isinstance(provider, str):
        filtered = [m for m in all_models if m.startswith(provider)]
    else:
        filtered = all_models

    return ToolResult(
        success=True,
        updated_state=state,
        validation=state.validate(),
        affected_nodes=(),
        data={"models": filtered, "count": len(filtered)},
    )


def _execute_preview_pipeline(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
) -> ToolResult:
    """Preview pipeline configuration — dry-run validation with source summary.

    V1: Returns validation result + source/node/output summary without
    executing. Full data-flow preview (actually running the source and
    returning sample rows) is a future enhancement.
    """
    validation = state.validate()

    summary: dict[str, Any] = {
        "is_valid": validation.is_valid,
        "errors": list(validation.errors),
        "warnings": list(validation.warnings),
        "suggestions": list(validation.suggestions),
        "source": None,
        "node_count": len(state.nodes),
        "output_count": len(state.outputs),
        "nodes": [{"id": n.id, "node_type": n.node_type, "plugin": n.plugin} for n in state.nodes],
        "outputs": [{"name": o.name, "plugin": o.plugin} for o in state.outputs],
    }

    if state.source is not None:
        summary["source"] = {
            "plugin": state.source.plugin,
            "on_success": state.source.on_success,
            "has_schema_config": "schema_config" in state.source.options,
        }

    return ToolResult(
        success=True,
        updated_state=state,
        validation=validation,
        affected_nodes=(),
        data=summary,
    )


# --- Registries ---
# Must be after all handler definitions to avoid NameError.

_DISCOVERY_TOOLS: dict[str, ToolHandler] = {
    "list_sources": _handle_list_sources,
    "list_transforms": _handle_list_transforms,
    "list_sinks": _handle_list_sinks,
    "get_plugin_schema": _handle_get_plugin_schema,
    "get_expression_grammar": _handle_get_expression_grammar,
    "explain_validation_error": _execute_explain_validation_error,
    "list_models": _execute_list_models,
    "preview_pipeline": _execute_preview_pipeline,
}

# All discovery tools are cacheable. If a non-cacheable discovery tool is
# re-added in future (e.g. get_current_state which returns live mutable
# state), add it to _DISCOVERY_TOOLS but NOT to this frozenset.
_CACHEABLE_DISCOVERY_TOOLS: frozenset[str] = frozenset(_DISCOVERY_TOOLS.keys())

_MUTATION_TOOLS: dict[str, ToolHandler] = {
    "set_source": _execute_set_source,
    "upsert_node": _handle_upsert_node,
    "upsert_edge": _handle_upsert_edge,
    "remove_node": _handle_remove_node,
    "remove_edge": _handle_remove_edge,
    "set_metadata": _handle_set_metadata,
    "set_output": _handle_set_output,
    "remove_output": _handle_remove_output,
    "patch_source_options": _handle_patch_source_options,
    "patch_node_options": _handle_patch_node_options,
    "patch_output_options": _handle_patch_output_options,
    "set_pipeline": _handle_set_pipeline,
    "clear_source": _handle_clear_source,
}

# Blob tools use an extended handler signature with session context kwargs
_BLOB_DISCOVERY_TOOLS: dict[str, BlobToolHandler] = {
    "list_blobs": _handle_list_blobs,
    "get_blob_metadata": _handle_get_blob_metadata,
}

_BLOB_MUTATION_TOOLS: dict[str, BlobToolHandler] = {
    "set_source_from_blob": _execute_set_source_from_blob,
}

# Secret tools use an extended handler signature with secret_service + user_id kwargs
_SECRET_DISCOVERY_TOOLS: dict[str, SecretToolHandler] = {
    "list_secret_refs": _handle_list_secret_refs,
    "validate_secret_ref": _handle_validate_secret_ref,
}

_SECRET_MUTATION_TOOLS: dict[str, SecretToolHandler] = {
    "wire_secret_ref": _execute_wire_secret_ref,
}

# Module-level assertions: registries must not overlap.
_all_tools = (
    set(_DISCOVERY_TOOLS)
    | set(_MUTATION_TOOLS)
    | set(_BLOB_DISCOVERY_TOOLS)
    | set(_BLOB_MUTATION_TOOLS)
    | set(_SECRET_DISCOVERY_TOOLS)
    | set(_SECRET_MUTATION_TOOLS)
)
assert len(_all_tools) == (
    len(_DISCOVERY_TOOLS)
    + len(_MUTATION_TOOLS)
    + len(_BLOB_DISCOVERY_TOOLS)
    + len(_BLOB_MUTATION_TOOLS)
    + len(_SECRET_DISCOVERY_TOOLS)
    + len(_SECRET_MUTATION_TOOLS)
), "Tool registry overlap detected"

assert set(_DISCOVERY_TOOLS) >= _CACHEABLE_DISCOVERY_TOOLS, (
    f"Cacheable tools not in discovery registry: {_CACHEABLE_DISCOVERY_TOOLS - set(_DISCOVERY_TOOLS)}"
)


def is_discovery_tool(name: str) -> bool:
    """Return True if the tool is a discovery (read-only) tool."""
    return name in _DISCOVERY_TOOLS or name in _BLOB_DISCOVERY_TOOLS or name in _SECRET_DISCOVERY_TOOLS


def is_cacheable_discovery_tool(name: str) -> bool:
    """Return True if the tool's results can be cached within a compose() call."""
    return name in _CACHEABLE_DISCOVERY_TOOLS


# --- Tool Executor ---


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogServiceProtocol,
    data_dir: str | None = None,
    session_engine: Engine | None = None,
    session_id: str | None = None,
    secret_service: Any | None = None,
    user_id: str | None = None,
) -> ToolResult:
    """Execute a composition tool by name.

    Dispatches via registry dict. Discovery tools return data without
    modifying state. Mutation tools return ToolResult with updated state
    and validation. Unknown tool names return a failure result.

    Args:
        data_dir: Base data directory for S2 path allowlist enforcement.
            When provided, source options containing ``path`` or ``file``
            keys are restricted to ``{data_dir}/uploads/`` or ``{data_dir}/blobs/``.
        session_engine: SQLAlchemy engine for the session database.
            Required for blob tools to perform synchronous blob lookups.
        session_id: Current session ID. Required for blob tools.
        secret_service: WebSecretService instance. Required for secret tools.
        user_id: Current user ID. Required for secret tools.
    """
    # Check standard tools first
    handler = _DISCOVERY_TOOLS.get(tool_name) or _MUTATION_TOOLS.get(tool_name)
    if handler is not None:
        return handler(arguments, state, catalog, data_dir)

    # Check blob tools (extended signature with session context)
    blob_handler = _BLOB_DISCOVERY_TOOLS.get(tool_name) or _BLOB_MUTATION_TOOLS.get(tool_name)
    if blob_handler is not None:
        return blob_handler(
            arguments,
            state,
            catalog,
            data_dir,
            session_engine=session_engine,
            session_id=session_id,
        )

    # Check secret tools (extended signature with secret_service + user_id)
    secret_handler = _SECRET_DISCOVERY_TOOLS.get(tool_name) or _SECRET_MUTATION_TOOLS.get(tool_name)
    if secret_handler is not None:
        return secret_handler(
            arguments,
            state,
            catalog,
            data_dir,
            secret_service=secret_service,
            user_id=user_id,
        )

    return _failure_result(state, f"Unknown tool: {tool_name}")
