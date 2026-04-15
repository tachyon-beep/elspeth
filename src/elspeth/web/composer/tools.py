"""Composition tools — discovery and mutation tools for the LLM composer.

Discovery tools delegate to CatalogService. Mutation tools modify
CompositionState and return ToolResult with validation.

Layer: L3 (application). Imports from L0 (contracts.freeze) and
L3 (web/composer/state, web/catalog/protocol).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine, delete, func, select, update

from elspeth.contracts.freeze import deep_thaw, freeze_fields
from elspeth.web.blobs.service import _source_references_blob, content_hash, sanitize_filename
from elspeth.web.catalog.protocol import CatalogService, PluginKind
from elspeth.web.composer.redaction import redact_source_storage_path
from elspeth.web.composer.state import (
    CompositionState,
    EdgeSpec,
    NodeSpec,
    OutputSpec,
    PipelineMetadata,
    SourceSpec,
    ValidationSummary,
    _source_options_have_schema,
    _validate_gate_expression,
)
from elspeth.web.paths import allowed_sink_directories, allowed_source_directories
from elspeth.web.sessions.models import blob_run_links_table, blobs_table, composition_states_table, runs_table


def _compute_validation_delta(
    before: ValidationSummary,
    after: ValidationSummary,
) -> dict[str, Any]:
    """Compute new/resolved entries between two validation states.

    Compares by (component, message) tuple since ValidationEntry
    instances are recreated on each validate() call (no stable identity).
    """
    before_errors = {(e.component, e.message) for e in before.errors}
    after_errors = {(e.component, e.message) for e in after.errors}
    before_warnings = {(w.component, w.message) for w in before.warnings}
    after_warnings = {(w.component, w.message) for w in after.warnings}

    new_errors = [e.to_dict() for e in after.errors if (e.component, e.message) not in before_errors]
    resolved_errors = [e.to_dict() for e in before.errors if (e.component, e.message) not in after_errors]
    new_warnings = [w.to_dict() for w in after.warnings if (w.component, w.message) not in before_warnings]
    resolved_warnings = [w.to_dict() for w in before.warnings if (w.component, w.message) not in after_warnings]

    return {
        "new_errors": new_errors,
        "resolved_errors": resolved_errors,
        "new_warnings": new_warnings,
        "resolved_warnings": resolved_warnings,
    }


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Result of a tool execution.

    Attributes:
        success: Whether the operation succeeded.
        updated_state: Full state after mutation (or original if success=False).
        validation: Stage 1 validation result for the updated state.
        affected_nodes: Node IDs changed or with changed edges.
        data: Optional data payload for discovery tools.
        prior_validation: Validation from before the mutation. When set,
            to_dict() includes a ``validation_delta`` showing new and
            resolved entries so the agent can focus on what changed.
    """

    success: bool
    updated_state: CompositionState
    validation: ValidationSummary
    affected_nodes: tuple[str, ...]
    data: Any = None
    prior_validation: ValidationSummary | None = None

    def __post_init__(self) -> None:
        freeze_fields(self, "affected_nodes")
        if self.data is not None:
            freeze_fields(self, "data")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for LLM tool response.

        Validation entries are serialized as structured dicts with
        component, message, and severity fields (B2 requirement).

        When prior_validation is set, includes a validation_delta with
        new_errors, resolved_errors, new_warnings, resolved_warnings to
        help the agent focus on what changed rather than re-reading the
        full validation state.
        """

        result: dict[str, Any] = {
            "success": self.success,
            "validation": {
                "is_valid": self.validation.is_valid,
                "errors": [e.to_dict() for e in self.validation.errors],
                "warnings": [e.to_dict() for e in self.validation.warnings],
                "suggestions": [e.to_dict() for e in self.validation.suggestions],
            },
            "affected_nodes": list(self.affected_nodes),
            "version": self.updated_state.version,
        }
        if self.data is not None:
            result["data"] = deep_thaw(self.data)

        if self.prior_validation is not None:
            result["validation_delta"] = _compute_validation_delta(
                self.prior_validation,
                self.validation,
            )

        return result


def diff_states(
    baseline: CompositionState,
    current: CompositionState,
    *,
    baseline_validation: ValidationSummary | None = None,
    current_validation: ValidationSummary | None = None,
) -> dict[str, Any]:
    """Compare two composition states and return a structured change summary.

    Reports added, removed, and modified nodes/edges/outputs, plus source
    and metadata changes. Used by the diff_pipeline MCP tool (B5).

    Args:
        baseline_validation: Pre-computed validation for the baseline state.
        current_validation: Pre-computed validation for the current state.
    """
    changes: dict[str, Any] = {
        "from_version": baseline.version,
        "to_version": current.version,
        "source_changed": False,
        "metadata_changed": False,
        "nodes": {"added": [], "removed": [], "modified": []},
        "edges": {"added": [], "removed": [], "modified": []},
        "outputs": {"added": [], "removed": [], "modified": []},
    }

    # Source
    if baseline.source != current.source:
        changes["source_changed"] = True
        if baseline.source is None:
            changes["source_detail"] = "added"
        elif current.source is None:
            changes["source_detail"] = "removed"
        else:
            changes["source_detail"] = "modified"

    # Metadata
    if baseline.metadata != current.metadata:
        changes["metadata_changed"] = True

    # Nodes
    baseline_nodes = {n.id: n for n in baseline.nodes}
    current_nodes = {n.id: n for n in current.nodes}
    for nid in current_nodes:
        if nid not in baseline_nodes:
            changes["nodes"]["added"].append(nid)
        elif current_nodes[nid] != baseline_nodes[nid]:
            changes["nodes"]["modified"].append(nid)
    for nid in baseline_nodes:
        if nid not in current_nodes:
            changes["nodes"]["removed"].append(nid)

    # Edges
    baseline_edges = {e.id: e for e in baseline.edges}
    current_edges = {e.id: e for e in current.edges}
    for eid in current_edges:
        if eid not in baseline_edges:
            changes["edges"]["added"].append(eid)
        elif current_edges[eid] != baseline_edges[eid]:
            changes["edges"]["modified"].append(eid)
    for eid in baseline_edges:
        if eid not in current_edges:
            changes["edges"]["removed"].append(eid)

    # Outputs
    baseline_outputs = {o.name: o for o in baseline.outputs}
    current_outputs = {o.name: o for o in current.outputs}
    for name in current_outputs:
        if name not in baseline_outputs:
            changes["outputs"]["added"].append(name)
        elif current_outputs[name] != baseline_outputs[name]:
            changes["outputs"]["modified"].append(name)
    for name in baseline_outputs:
        if name not in current_outputs:
            changes["outputs"]["removed"].append(name)

    # Validation delta — reuse pre-computed validations when available
    if baseline_validation is None:
        baseline_validation = baseline.validate()
    if current_validation is None:
        current_validation = current.validate()
    baseline_warnings = {e.message for e in baseline_validation.warnings}
    current_warnings = {e.message for e in current_validation.warnings}
    changes["warnings_introduced"] = sorted(current_warnings - baseline_warnings)
    changes["warnings_resolved"] = sorted(baseline_warnings - current_warnings)

    # Summary stats
    total = sum(len(changes[k][action]) for k in ("nodes", "edges", "outputs") for action in ("added", "removed", "modified"))
    total += int(changes["source_changed"]) + int(changes["metadata_changed"])
    changes["total_changes"] = total

    return changes


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

    Returns 32 tools: 9 discovery + 13 mutation + 7 blob tools + 3 secret tools.
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
                        "description": "How to handle validation failures. Use 'discard' to drop invalid rows, "
                        "'quarantine' for the built-in quarantine sink, or a sink name to divert failed rows.",
                    },
                },
                "required": ["plugin", "on_success", "options", "on_validation_failure"],
            },
        },
        {
            "name": "upsert_node",
            "description": (
                "Add or update a pipeline node. "
                "Fields are node_type-dependent: "
                "transform/aggregation use plugin+options; "
                "gate uses condition+routes (or fork_to); "
                "coalesce uses branches+policy+merge. "
                "Omit fields that don't apply to your node_type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique node identifier."},
                    "node_type": {
                        "type": "string",
                        "enum": ["transform", "gate", "aggregation", "coalesce"],
                    },
                    "plugin": {
                        "type": ["string", "null"],
                        "description": "Plugin name. Required for transform/aggregation. Null for gate/coalesce.",
                    },
                    "input": {"type": "string", "description": "Input connection name."},
                    "on_success": {
                        "type": ["string", "null"],
                        "description": "Output connection. Required for transform/aggregation/coalesce. Null for gates (routing is via condition/routes).",
                    },
                    "on_error": {"type": ["string", "null"], "description": "Error output connection (transform/aggregation only)."},
                    "options": {"type": "object", "description": "Plugin-specific config (transform/aggregation only)."},
                    "condition": {"type": ["string", "null"], "description": "Boolean expression (gate only). Evaluated per row."},
                    "routes": {
                        "type": ["object", "null"],
                        "description": "Route mapping {true: sink_or_node, false: sink_or_node} (gate only, mutually exclusive with fork_to).",
                    },
                    "fork_to": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Fork destinations — row is copied to all listed paths (gate only, mutually exclusive with routes).",
                    },
                    "branches": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "Input branch names to merge (coalesce only).",
                    },
                    "policy": {"type": ["string", "null"], "description": "Merge trigger policy (coalesce only)."},
                    "merge": {"type": ["string", "null"], "description": "Field merge strategy (coalesce only)."},
                    "trigger": {
                        "type": ["object", "null"],
                        "description": "Batch trigger config (aggregation only). At least one of: {count: int, timeout_seconds: float, condition: string}.",
                    },
                    "output_mode": {
                        "type": ["string", "null"],
                        "enum": ["passthrough", "transform", None],
                        "description": "Aggregation output mode (aggregation only). Defaults to 'transform' if omitted.",
                    },
                    "expected_output_count": {
                        "type": ["integer", "null"],
                        "description": "Expected number of output rows from aggregation (aggregation only). Optional.",
                    },
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
                        "description": "How to handle per-row write failures. Use 'discard' to drop with audit record, or a sink name (e.g. 'results_failures') to divert failed rows to that failsink.",
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
                        "properties": {
                            "plugin": {"type": "string"},
                            "options": {"type": "object"},
                            "on_success": {"type": "string"},
                            "on_validation_failure": {
                                "type": "string",
                                "description": "How to handle validation failures. Use 'discard' to drop invalid rows, "
                                "'quarantine' for the built-in quarantine sink, or a sink name to divert failed rows.",
                            },
                        },
                        "required": ["plugin", "options", "on_success"],
                    },
                    "nodes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "node_type": {"type": "string"},
                                "plugin": {"type": "string"},
                                "input": {"type": "string"},
                                "on_success": {"type": "string"},
                                "on_error": {"type": "string"},
                                "options": {"type": "object"},
                                "condition": {"type": "string"},
                                "routes": {"type": "object"},
                                "fork_to": {"type": "array"},
                                "branches": {"type": "array"},
                                "policy": {"type": "string"},
                                "merge": {"type": "string"},
                                "trigger": {"type": "object"},
                                "output_mode": {"type": "string"},
                                "expected_output_count": {"type": "integer"},
                            },
                            "required": ["id", "node_type", "input"],
                        },
                        "description": "Array of node specs: [{id, input, plugin?, node_type, options?, on_success?, on_error?, condition?, routes?, fork_to?, branches?, policy?, merge?, trigger?, output_mode?, expected_output_count?}]",
                    },
                    "edges": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "from_node": {"type": "string"},
                                "to_node": {"type": "string"},
                                "edge_type": {"type": "string"},
                                "label": {"type": "string"},
                            },
                            "required": ["id", "from_node", "to_node", "edge_type"],
                        },
                        "description": "Array of edge specs: [{id, from_node, to_node, edge_type}]",
                    },
                    "outputs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sink_name": {"type": "string"},
                                "plugin": {"type": "string"},
                                "options": {"type": "object"},
                                "on_write_failure": {"type": "string"},
                            },
                            "required": ["sink_name", "plugin", "options"],
                        },
                        "description": "Array of output specs: [{sink_name, plugin, options, on_write_failure?}]",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Pipeline metadata: {name?, description?}",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                        },
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
            "description": "List available LLM model identifiers. Without a provider "
            "filter, returns provider names and counts. With a provider filter, "
            "returns matching model IDs (capped at limit).",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "Provider prefix to filter by (e.g. 'openrouter/', 'azure/'). "
                        "Omit to get a provider summary instead of individual models.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max models to return (default 50).",
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
        {
            "name": "get_pipeline_state",
            "description": "Inspect the full current pipeline state including all "
            "options for source, nodes, and outputs. Use this during correction "
            "loops to see what is currently configured before patching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "component": {
                        "type": "string",
                        "description": "Optional: return only one component — 'source', a node ID, or an output name. Omit for full state.",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "diff_pipeline",
            "description": "Show what changed since the session was loaded or created. "
            "Returns added, removed, and modified nodes/edges/outputs, "
            "plus warnings introduced or resolved.",
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
            "description": "Wire a blob as the pipeline source. Resolves the blob's storage path internally and infers the source plugin from its MIME type. "
            "Use 'options' for plugin-specific config (e.g., 'column' and 'schema' for text sources).",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_id": {"type": "string", "description": "Blob ID to use as source."},
                    "plugin": {"type": "string", "description": "Source plugin override (e.g. 'csv'). Inferred from MIME type if omitted."},
                    "on_success": {"type": "string", "description": "Node ID to route rows to after source."},
                    "on_validation_failure": {
                        "type": "string",
                        "description": "How to handle validation failures. Use 'discard' to drop invalid rows, "
                        "'quarantine' for the built-in quarantine sink, or a sink name to divert failed rows.",
                        "default": "quarantine",
                    },
                    "options": {
                        "type": "object",
                        "description": "Plugin-specific config (merged with blob path). Required fields vary by plugin: "
                        "text sources need 'column' (output field name) and 'schema' (e.g., {mode: 'observed'}).",
                    },
                },
                "required": ["blob_id", "on_success"],
            },
        },
        {
            "name": "create_blob",
            "description": "Create a new file (blob) from inline content. "
            "Use this to create seed input files (URLs, JSON, CSV snippets) "
            "mid-conversation without requiring manual upload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename for the blob (e.g. 'urls.csv', 'seed.json').",
                    },
                    "mime_type": {
                        "type": "string",
                        "enum": [
                            "text/plain",
                            "application/json",
                            "text/csv",
                            "application/x-jsonlines",
                            "application/jsonl",
                            "text/jsonl",
                        ],
                        "description": "MIME type of the content.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The file content as a string.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description of the file's purpose.",
                    },
                },
                "required": ["filename", "mime_type", "content"],
            },
        },
        {
            "name": "update_blob",
            "description": "Update the content of an existing blob (file). Overwrites the file content while preserving metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_id": {
                        "type": "string",
                        "description": "ID of the blob to update.",
                    },
                    "content": {
                        "type": "string",
                        "description": "New file content.",
                    },
                },
                "required": ["blob_id", "content"],
            },
        },
        {
            "name": "delete_blob",
            "description": "Delete a blob (file) and its storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_id": {
                        "type": "string",
                        "description": "ID of the blob to delete.",
                    },
                },
                "required": ["blob_id"],
            },
        },
        {
            "name": "get_blob_content",
            "description": "Retrieve the content of a blob (file) for inspection. Large files are truncated to 50,000 characters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "blob_id": {
                        "type": "string",
                        "description": "ID of the blob to read.",
                    },
                },
                "required": ["blob_id"],
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
    [dict[str, Any], CompositionState, CatalogService, str | None],
    ToolResult,
]


# Discovery tool handlers (normalized signatures)


def _handle_list_sources(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, catalog.list_sources())


def _handle_list_transforms(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, catalog.list_transforms())


def _handle_list_sinks(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, catalog.list_sinks())


def _handle_get_plugin_schema(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
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
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _discovery_result(state, get_expression_grammar())


# Mutation tool handler wrappers (normalize 2/3-arg handlers to 4-arg)


def _handle_upsert_node(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_upsert_node(arguments, state, catalog)


def _handle_upsert_edge(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_upsert_edge(arguments, state)


def _handle_remove_node(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_remove_node(arguments, state)


def _handle_remove_edge(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_remove_edge(arguments, state)


def _handle_set_metadata(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_set_metadata(arguments, state)


def _handle_set_output(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_set_output(arguments, state, catalog, data_dir)


def _handle_remove_output(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
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
    *,
    prior_validation: ValidationSummary | None = None,
) -> ToolResult:
    """Build a ToolResult for a successful mutation."""
    validation = new_state.validate()
    return ToolResult(
        success=True,
        updated_state=new_state,
        validation=validation,
        affected_nodes=affected,
        prior_validation=prior_validation,
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
    catalog: CatalogService,
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

_MIME_TO_SOURCE: dict[str, tuple[str, dict[str, str]]] = {
    "text/csv": ("csv", {}),
    "application/json": ("json", {}),
    "application/x-jsonlines": ("json", {"format": "jsonl"}),
    "application/jsonl": ("json", {"format": "jsonl"}),
    "text/jsonl": ("json", {"format": "jsonl"}),
    "text/plain": ("text", {}),
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

    allowed = allowed_source_directories(data_dir)

    for key in ("path", "file"):
        if key in options:
            raw = Path(options[key])
            resolved = (Path(data_dir).resolve() / raw).resolve() if not raw.is_absolute() else raw.resolve()
            if not any(resolved.is_relative_to(d) for d in allowed):
                return (
                    f"Path violation (S2): '{options[key]}' is outside the "
                    f"allowed directories. Source file paths "
                    f"must be under {data_dir}/blobs/."
                )
    return None


def _validate_sink_path(
    options: dict[str, Any],
    data_dir: str | None,
) -> str | None:
    """Validate that sink path options are under allowed output directories.

    Returns an error message if validation fails, None if OK.
    Mirrors _validate_source_path but uses _allowed_sink_directories.
    """
    if data_dir is None:
        return None

    allowed = allowed_sink_directories(data_dir)

    for key in ("path", "file"):
        if key in options:
            raw = Path(options[key])
            resolved = (Path(data_dir).resolve() / raw).resolve() if not raw.is_absolute() else raw.resolve()
            if not any(resolved.is_relative_to(d) for d in allowed):
                return (
                    f"Path violation (S2): '{options[key]}' is outside the "
                    f"allowed directories. Sink output paths "
                    f"must be under {data_dir}/outputs/ or {data_dir}/blobs/."
                )
    return None


def _prevalidate_plugin_options(
    plugin_type: PluginKind,
    plugin_name: str,
    options: dict[str, Any],
    *,
    injected_fields: dict[str, Any] | None = None,
) -> str | None:
    """Pre-validate plugin options against the plugin's config model.

    Catches missing required options (e.g., schema, operations) and
    malformed values (e.g., invalid field specs) BEFORE storing them in
    CompositionState. Returns None if valid, or a descriptive error
    message suitable for returning to the LLM agent.

    The plugin's own Pydantic config model is the authority — this
    function asks the plugin what it needs rather than hardcoding
    knowledge about individual plugins.

    Secret-ref markers (``{"secret_ref": "NAME"}``) are stripped before
    validation. The underlying Pydantic errors are filtered to exclude
    errors on secret-ref'd fields — those fields ARE provisioned, just
    deferred to execution time when ``resolve_secret_refs`` replaces them
    with actual values.

    Args:
        plugin_type: "source", "transform", or "sink".
        plugin_name: Plugin name (e.g., "csv", "value_transform").
        options: Options dict as provided by the LLM agent.
        injected_fields: Synthetic values for fields that come from
            other parts of the pipeline spec (e.g., on_validation_failure
            for sources). Merged into options for validation only —
            not stored.
    """
    from pydantic import ValidationError

    from elspeth.plugins.infrastructure.config_base import PluginConfigError
    from elspeth.plugins.infrastructure.validation import (
        UnknownPluginTypeError,
        get_sink_config_model,
        get_source_config_model,
        get_transform_config_model,
    )

    try:
        if plugin_type == "source":
            config_cls = get_source_config_model(plugin_name)
        elif plugin_type == "transform":
            config_cls = get_transform_config_model(plugin_name, options)
        elif plugin_type == "sink":
            config_cls = get_sink_config_model(plugin_name)
        else:
            # PluginKind is Literal["source", "transform", "sink"] — unreachable.
            raise AssertionError(f"_prevalidate_plugin_options: unexpected plugin_type={plugin_type!r}")
    except UnknownPluginTypeError:
        # Plugin name not in registry — let engine validation catch it later.
        return None
    except ValueError as exc:
        # Config model selection raised (e.g. unknown LLM provider) — surface it.
        return f"Invalid options for {plugin_type} '{plugin_name}': {exc}"

    if config_cls is None:
        return None

    # Options may contain frozen containers (MappingProxyType, tuple) from
    # CompositionState.  Thaw them so Pydantic receives plain dicts/lists.
    merged = deep_thaw(options)
    if injected_fields:
        for k, v in injected_fields.items():
            if k not in merged:
                merged[k] = v

    # Strip secret_ref markers before validation.  A secret-ref'd field
    # IS provisioned (the user called wire_secret_ref), just deferred to
    # execution time.  Stripping it may cause Pydantic to report
    # "field required" — we filter those errors out below.
    secret_ref_keys: set[str] = set()
    for key, value in list(merged.items()):
        if isinstance(value, Mapping) and len(value) == 1 and "secret_ref" in value and isinstance(value["secret_ref"], str):
            secret_ref_keys.add(key)
            del merged[key]

    try:
        config_cls.from_dict(merged, plugin_name=plugin_name)
        return None
    except PluginConfigError as exc:
        if not secret_ref_keys:
            # No secret refs were stripped — report the error as-is.
            msg = exc.cause if exc.cause is not None else str(exc)
            return f"Invalid options for {plugin_type} '{plugin_name}': {msg}"

        # Secret refs were stripped.  Filter out errors on those fields.
        cause = exc.__cause__
        if not isinstance(cause, ValidationError):
            # ValueError path (model validators) — can't filter per-field.
            msg = exc.cause if exc.cause is not None else str(exc)
            return f"Invalid options for {plugin_type} '{plugin_name}': {msg}"

        remaining = [e for e in cause.errors() if not (e["loc"] and e["loc"][0] in secret_ref_keys)]
        if not remaining:
            return None

        # Re-format only the non-secret errors.
        lines = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in remaining)
        return f"Invalid options for {plugin_type} '{plugin_name}': {lines}"


_WEB_ONLY_SOURCE_KEYS = frozenset({"blob_ref"})


def _prevalidate_source(
    plugin_name: str,
    options: dict[str, Any],
    on_validation_failure: str = "quarantine",
) -> str | None:
    """Pre-validate source options, injecting on_validation_failure and filtering web-only keys."""
    filtered = {k: v for k, v in options.items() if k not in _WEB_ONLY_SOURCE_KEYS}
    return _prevalidate_plugin_options(
        "source",
        plugin_name,
        filtered,
        injected_fields={"on_validation_failure": on_validation_failure},
    )


def _prevalidate_transform(plugin_name: str, options: dict[str, Any]) -> str | None:
    """Pre-validate transform options."""
    return _prevalidate_plugin_options("transform", plugin_name, options)


def _prevalidate_sink(plugin_name: str, options: dict[str, Any]) -> str | None:
    """Pre-validate sink options."""
    return _prevalidate_plugin_options("sink", plugin_name, options)


def _execute_set_source(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
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

    on_vf = args.get("on_validation_failure", "quarantine")
    prevalidation_error = _prevalidate_source(plugin, options, on_vf)
    if prevalidation_error is not None:
        return _failure_result(state, prevalidation_error)

    source = SourceSpec(
        plugin=plugin,
        on_success=args["on_success"],
        options=options,
        on_validation_failure=on_vf,
    )
    new_state = state.with_source(source)
    return _mutation_result(new_state, ("source",))


def _execute_upsert_node(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
) -> ToolResult:
    """Add or update a pipeline node."""
    node_type = args["node_type"]
    plugin = args.get("plugin")

    # Validate plugin for types that require one.
    # Gates and coalesces intentionally have plugin=None (they're expression-based or
    # structural, not plugin-driven), so the "and plugin is not None" guard covers them.
    # NodeSpec documents this: "plugin: Plugin name. None for gates and coalesces."
    if node_type in ("transform", "aggregation") and plugin is not None:
        plugin_error = _validate_plugin_name(catalog, "transform", plugin)
        if plugin_error is not None:
            return _failure_result(state, plugin_error)

        node_options = args.get("options", {})
        prevalidation_error = _prevalidate_transform(plugin, node_options)
        if prevalidation_error is not None:
            return _failure_result(state, prevalidation_error)

    # Validate gate condition expression at composition time.
    # Gives the LLM immediate feedback on syntax/security errors.
    condition = args.get("condition")
    if node_type == "gate" and condition is not None:
        expr_error = _validate_gate_expression(condition)
        if expr_error is not None:
            return _failure_result(state, f"Node '{args['id']}': {expr_error}")

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
        trigger=args.get("trigger"),
        output_mode=args.get("output_mode"),
        expected_output_count=args.get("expected_output_count"),
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
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    """Add or replace a pipeline output (sink)."""
    plugin = args["plugin"]
    # Validate plugin exists in catalog
    plugin_error = _validate_plugin_name(catalog, "sink", plugin)
    if plugin_error is not None:
        return _failure_result(state, plugin_error)

    # S2: Validate sink path allowlist (mirrors source path check)
    sink_options = args.get("options", {})
    path_error = _validate_sink_path(sink_options, data_dir)
    if path_error is not None:
        return _failure_result(state, path_error)

    prevalidation_error = _prevalidate_sink(plugin, sink_options)
    if prevalidation_error is not None:
        return _failure_result(state, prevalidation_error)

    output = OutputSpec(
        name=args["sink_name"],
        plugin=plugin,
        options=sink_options,
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
    catalog: CatalogService,
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
    catalog: CatalogService,
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
    catalog: CatalogService,
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

    # Determine source plugin and any format-specific options
    mime_extra: dict[str, str] = {}
    explicit_plugin = arguments.get("plugin")
    if explicit_plugin:
        plugin = explicit_plugin
    else:
        mime_entry = _MIME_TO_SOURCE.get(blob["mime_type"])
        if mime_entry is None:
            return _failure_result(
                state,
                f"Cannot infer source plugin for MIME type '{blob['mime_type']}'. Please specify the 'plugin' parameter explicitly.",
            )
        plugin, mime_extra = mime_entry

    # Validate plugin exists
    try:
        catalog.get_schema("source", plugin)
    except (ValueError, KeyError) as exc:
        return _failure_result(state, f"Unknown source plugin '{plugin}': {exc}")

    # Merge caller-provided options with blob-derived options.
    # Caller options come first, then we overlay the authoritative blob fields.
    # This allows callers to provide plugin-specific config (schema, column, etc.)
    # while ensuring path and blob_ref always reflect the actual blob.
    caller_options = arguments.get("options", {})
    merged_options = {
        **caller_options,
        **mime_extra,
        "path": blob["storage_path"],
        "blob_ref": blob["id"],
    }

    # Pre-validate options against the plugin's config model.
    on_vf = arguments.get("on_validation_failure", "quarantine")
    prevalidation_error = _prevalidate_source(plugin, merged_options, on_vf)
    if prevalidation_error is not None:
        return _failure_result(state, prevalidation_error)

    source = SourceSpec(
        plugin=plugin,
        on_success=arguments["on_success"],
        options=merged_options,
        on_validation_failure=on_vf,
    )
    new_state = state.with_source(source)
    return _mutation_result(new_state, ("source",))


_ALLOWED_BLOB_MIME_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "application/json",
        "text/csv",
        "application/x-jsonlines",
        "application/jsonl",
        "text/jsonl",
    }
)

# Default per-session blob storage quota (matches BlobServiceImpl).
_BLOB_QUOTA_BYTES: int = 500 * 1024 * 1024


def _blob_storage_path(data_dir: str, session_id: str, blob_id: str, filename: str) -> Path:
    """Compute blob storage path matching BlobServiceImpl layout.

    Pattern: {data_dir}/blobs/{session_id}/{blob_id}_{filename}
    """
    return Path(data_dir).resolve() / "blobs" / session_id / f"{blob_id}_{filename}"


def _check_blob_quota(conn: Any, session_id: str, additional_bytes: int) -> str | None:
    """Check if adding bytes would exceed the session blob quota.

    Returns an error message if quota exceeded, None if OK.
    Runs inside an existing transaction for TOCTOU safety.
    """
    current_total = conn.execute(
        select(func.coalesce(func.sum(blobs_table.c.size_bytes), 0)).where(blobs_table.c.session_id == session_id)
    ).scalar()
    current_total = int(current_total)
    if current_total + additional_bytes > _BLOB_QUOTA_BYTES:
        return f"Session blob quota exceeded: {current_total + additional_bytes} bytes would exceed {_BLOB_QUOTA_BYTES} byte limit."
    return None


def _execute_create_blob(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    """Create a new blob (file) in the session from inline content.

    Uses the same storage layout and safety functions as BlobServiceImpl:
    sanitize_filename() for path traversal defence, content_hash() for
    SHA-256, per-session subdirectory, and atomic quota enforcement.
    """
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")
    if data_dir is None:
        return _failure_result(state, "Blob tools require data_dir for storage.")

    filename = arguments["filename"]
    mime_type = arguments["mime_type"]
    content = arguments["content"]

    if mime_type not in _ALLOWED_BLOB_MIME_TYPES:
        return _failure_result(
            state,
            f"Unsupported MIME type '{mime_type}'. Allowed: {', '.join(sorted(_ALLOWED_BLOB_MIME_TYPES))}",
        )

    # Sanitize filename — strips path components, rejects dots/empty
    try:
        safe_filename = sanitize_filename(filename)
    except ValueError as exc:
        return _failure_result(state, f"Invalid filename: {exc}")

    content_bytes = content.encode("utf-8")
    file_hash = content_hash(content_bytes)
    blob_id = str(uuid4())

    # Storage path matches BlobServiceImpl: blobs/{session_id}/{blob_id}_{filename}
    storage_path = _blob_storage_path(data_dir, session_id, blob_id, safe_filename)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content_bytes)

    # Atomic quota check + insert (same pattern as BlobServiceImpl)
    now = datetime.now(UTC)
    try:
        with session_engine.begin() as conn:
            quota_error = _check_blob_quota(conn, session_id, len(content_bytes))
            if quota_error is not None:
                storage_path.unlink(missing_ok=True)
                return _failure_result(state, quota_error)

            conn.execute(
                blobs_table.insert().values(
                    id=blob_id,
                    session_id=session_id,
                    filename=safe_filename,
                    mime_type=mime_type,
                    size_bytes=len(content_bytes),
                    content_hash=file_hash,
                    storage_path=str(storage_path),
                    created_at=now,
                    created_by="assistant",
                    source_description=arguments.get("description"),
                    status="ready",
                )
            )
    except Exception:
        # Clean up file on any DB failure.  Exception (not BaseException)
        # because SQLAlchemy errors are Exception subclasses; catching
        # KeyboardInterrupt/SystemExit here is unnecessary and the unlink
        # cleanup is safe but the broader catch is not justified.
        storage_path.unlink(missing_ok=True)
        raise

    return _discovery_result(
        state,
        {
            "blob_id": blob_id,
            "filename": safe_filename,
            "mime_type": mime_type,
            "size_bytes": len(content_bytes),
            "content_hash": file_hash,
        },
    )


def _execute_update_blob(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    """Update the content of an existing blob."""
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")

    blob_id = arguments["blob_id"]
    content = arguments["content"]

    blob = _sync_get_blob(session_engine, blob_id, session_id)
    if blob is None:
        return _failure_result(state, f"Blob '{blob_id}' not found.")

    content_bytes = content.encode("utf-8")
    file_hash = content_hash(content_bytes)

    # Overwrite storage file — snapshot old content for rollback on DB failure
    storage_path = Path(blob["storage_path"])
    old_content = storage_path.read_bytes()
    storage_path.write_bytes(content_bytes)

    new_size = len(content_bytes)

    # Atomic quota check + update.  size_bytes is re-read inside the
    # transaction so the delta reflects the current DB row, not the
    # pre-transaction snapshot (which may be stale under concurrent writes).
    try:
        with session_engine.begin() as conn:
            current_size: int = conn.execute(
                select(blobs_table.c.size_bytes).where(blobs_table.c.id == blob_id, blobs_table.c.session_id == session_id)
            ).scalar_one()
            size_delta = new_size - current_size

            if size_delta > 0:
                quota_error = _check_blob_quota(conn, session_id, size_delta)
                if quota_error is not None:
                    storage_path.write_bytes(old_content)
                    return _failure_result(state, quota_error)
            conn.execute(
                update(blobs_table)
                .where(blobs_table.c.id == blob_id, blobs_table.c.session_id == session_id)
                .values(
                    size_bytes=new_size,
                    content_hash=file_hash,
                )
            )
    except Exception:
        # Restore old content so file matches DB metadata.  Exception
        # (not BaseException) because write_bytes() is not atomic — under
        # KeyboardInterrupt the rollback write could truncate the file,
        # leaving it inconsistent with both old and new DB state.
        storage_path.write_bytes(old_content)
        raise

    return _discovery_result(
        state,
        {
            "blob_id": blob_id,
            "filename": blob["filename"],
            "mime_type": blob["mime_type"],
            "size_bytes": len(content_bytes),
            "content_hash": file_hash,
        },
    )


def _execute_delete_blob(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    """Delete a blob and its storage file."""
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")

    blob_id = arguments["blob_id"]

    blob = _sync_get_blob(session_engine, blob_id, session_id)
    if blob is None:
        return _failure_result(state, f"Blob '{blob_id}' not found.")

    storage_path = Path(blob["storage_path"])

    # Single transaction: guard + unlink + delete (matches BlobServiceImpl.delete_blob)
    with session_engine.begin() as conn:
        # Active-run guard (two checks):
        #
        # 1. Explicit link: blob_run_links already points at an active run.
        active_link = conn.execute(
            select(blob_run_links_table)
            .join(runs_table, blob_run_links_table.c.run_id == runs_table.c.id)
            .where(blob_run_links_table.c.blob_id == blob_id)
            .where(runs_table.c.status.in_(["pending", "running"]))
        ).first()
        if active_link is not None:
            return _failure_result(
                state,
                f"Blob '{blob_id}' is linked to active run '{active_link.run_id}' and cannot be deleted.",
            )

        # 2. Pre-link window: _execute_locked() creates the run record before
        #    link_blob_to_run() inserts the blob_run_links row.  During that
        #    gap the explicit-link check above sees nothing, but the backing
        #    file is about to be needed.
        #
        #    Scoped to THIS blob: join runs → composition_states and check
        #    whether the active run's source references this blob via
        #    blob_ref OR via a path/file matching this blob's storage_path.
        #    Runs whose source doesn't touch this blob must not block
        #    unrelated blob deletions.
        active_run = conn.execute(
            select(runs_table.c.id, composition_states_table.c.source)
            .join(
                composition_states_table,
                runs_table.c.state_id == composition_states_table.c.id,
            )
            .where(runs_table.c.session_id == session_id)
            .where(runs_table.c.status.in_(["pending", "running"]))
        ).first()
        if active_run is not None and _source_references_blob(active_run.source, blob_id, blob["storage_path"]):
            return _failure_result(
                state,
                f"Blob '{blob_id}' cannot be deleted while active run '{active_run.id}' references it.",
            )

        # Delete backing file first — orphaned DB row is recoverable,
        # orphaned file with no metadata is not
        storage_path.unlink(missing_ok=True)

        # Delete record — include session_id filter for defence in depth
        conn.execute(
            delete(blobs_table).where(
                blobs_table.c.id == blob_id,
                blobs_table.c.session_id == session_id,
            )
        )

    return _discovery_result(state, {"blob_id": blob_id, "deleted": True})


def _execute_get_blob_content(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    *,
    session_engine: Engine | None = None,
    session_id: str | None = None,
) -> ToolResult:
    """Retrieve the content of a blob for inspection."""
    if session_engine is None or session_id is None:
        return _failure_result(state, "Blob tools require session context.")

    blob_id = arguments["blob_id"]
    blob = _sync_get_blob(session_engine, blob_id, session_id)
    if blob is None:
        return _failure_result(state, f"Blob '{blob_id}' not found.")

    storage_path = Path(blob["storage_path"])
    if not storage_path.exists():
        return _failure_result(state, f"Blob storage file missing for '{blob_id}'.")

    content = storage_path.read_text(encoding="utf-8")

    # Truncate very large content to avoid overwhelming the LLM context
    max_chars = 50_000
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]

    return _discovery_result(
        state,
        {
            "blob_id": blob_id,
            "filename": blob["filename"],
            "mime_type": blob["mime_type"],
            "content": content,
            "truncated": truncated,
            "size_bytes": blob["size_bytes"],
        },
    )


# Blob tool handler type — extended signature with session context
BlobToolHandler = Callable[..., ToolResult]

# --- Secret tool handlers ---

# Secret tool handler type — extended signature with secret_service + user_id
SecretToolHandler = Callable[..., ToolResult]


def _handle_list_secret_refs(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
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
    catalog: CatalogService,
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
    catalog: CatalogService,
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
            trigger=deep_thaw(node.trigger) if node.trigger is not None else None,
            output_mode=node.output_mode,
            expected_output_count=node.expected_output_count,
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
    catalog: CatalogService,
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

    src_on_vf = src_args.get("on_validation_failure", "quarantine")
    src_prevalidation = _prevalidate_source(src_plugin, src_options, src_on_vf)
    if src_prevalidation is not None:
        return _failure_result(state, src_prevalidation)

    # 2. Validate node plugins and options
    for node_args in args["nodes"]:
        node_id = node_args.get("id", "?")
        node_type = node_args["node_type"]
        node_plugin = node_args.get("plugin")
        if node_type in ("transform", "aggregation") and node_plugin is not None:
            plugin_error = _validate_plugin_name(catalog, "transform", node_plugin)
            if plugin_error is not None:
                return _failure_result(state, f"Node '{node_id}': {plugin_error}")
            node_options = node_args.get("options", {})
            node_prevalidation = _prevalidate_transform(node_plugin, node_options)
            if node_prevalidation is not None:
                return _failure_result(state, f"Node '{node_id}': {node_prevalidation}")

        # Validate gate condition expression at composition time.
        node_condition = node_args.get("condition")
        if node_type == "gate" and node_condition is not None:
            expr_error = _validate_gate_expression(node_condition)
            if expr_error is not None:
                return _failure_result(state, f"Node '{node_id}': {expr_error}")

    # 3. Validate output plugins and options
    for out_args in args["outputs"]:
        out_name = out_args.get("sink_name", "?")
        out_plugin = out_args["plugin"]
        plugin_error = _validate_plugin_name(catalog, "sink", out_plugin)
        if plugin_error is not None:
            return _failure_result(state, f"Output '{out_name}': {plugin_error}")
        # S2: Validate sink path allowlist (mirrors source path check)
        out_options = out_args.get("options", {})
        out_path_error = _validate_sink_path(out_options, data_dir)
        if out_path_error is not None:
            return _failure_result(state, f"Output '{out_name}': {out_path_error}")
        out_prevalidation = _prevalidate_sink(out_plugin, out_options)
        if out_prevalidation is not None:
            return _failure_result(state, f"Output '{out_name}': {out_prevalidation}")

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
                    trigger=n.get("trigger"),
                    output_mode=n.get("output_mode"),
                    expected_output_count=n.get("expected_output_count"),
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
                    name=o["sink_name"],
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
        meta_kwargs: dict[str, str] = {}
        if "name" in meta:
            meta_kwargs["name"] = meta["name"]
        if "description" in meta:
            meta_kwargs["description"] = meta["description"]
        metadata_spec = PipelineMetadata(**meta_kwargs)
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
    catalog: CatalogService,
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

    # Pre-validate patched options against config model
    prevalidation_error = _prevalidate_source(
        state.source.plugin,
        new_options,
        state.source.on_validation_failure,
    )
    if prevalidation_error is not None:
        return _failure_result(state, prevalidation_error)

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
    catalog: CatalogService,
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

    if current.node_type in ("transform", "aggregation") and current.plugin is not None:
        prevalidation_error = _prevalidate_transform(current.plugin, new_options)
        if prevalidation_error is not None:
            return _failure_result(state, prevalidation_error)

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
        trigger=current.trigger,
        output_mode=current.output_mode,
        expected_output_count=current.expected_output_count,
    )
    new_state = state.with_node(new_node)
    return _mutation_result(new_state, (node_id,))


def _handle_patch_node_options(
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_patch_node_options(arguments, state)


def _execute_patch_output_options(
    args: dict[str, Any],
    state: CompositionState,
    data_dir: str | None = None,
) -> ToolResult:
    sink_name = args["sink_name"]
    patch = args["patch"]
    if not isinstance(patch, dict):
        return _failure_result(state, "patch must be an object.")
    current = next((o for o in state.outputs if o.name == sink_name), None)
    if current is None:
        return _failure_result(state, f"Output '{sink_name}' not found.")
    new_options = _apply_merge_patch(current.options, patch)

    # S2: Validate patched sink paths against allowlist
    path_error = _validate_sink_path(new_options, data_dir)
    if path_error is not None:
        return _failure_result(state, path_error)

    prevalidation_error = _prevalidate_sink(current.plugin, new_options)
    if prevalidation_error is not None:
        return _failure_result(state, prevalidation_error)

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
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    return _execute_patch_output_options(arguments, state, data_dir)


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
    catalog: CatalogService,
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
        "A node's input connection point is not produced by the runtime routing fields.",
        "Set source.on_success or an upstream node's on_success/on_error/route/fork_to so it matches this node's input.",
    ),
    (
        r"Unknown .+ plugin '(.+)'",
        "The specified plugin name is not available in the catalog.",
        "Use list_sources, list_transforms, or list_sinks to see available plugins.",
    ),
    (
        r"Path violation \(S2\).*[Ss]ource",
        "The source file path is outside the allowed directories.",
        "Source paths must be under the blobs/ directory. Upload a file first or use set_source_from_blob.",
    ),
    (
        r"Path violation \(S2\).*[Ss]ink",
        "The sink output path is outside the allowed directories.",
        "Sink output paths must be under the outputs/ or blobs/ directory.",
    ),
    (
        r"Path violation \(S2\)",
        "A file path is outside the allowed directories.",
        "Source paths must be under the blobs/ directory. Sink output paths must be under the outputs/ or blobs/ directory.",
    ),
    (
        r"Invalid options for source '(.+)':",
        "The source plugin configuration is invalid. A required option may be missing or have an invalid value.",
        "Use get_pipeline_state with component='source' to see current options, then use patch_source_options to fix.",
    ),
    (
        r"Invalid options for transform '(.+)':",
        "A transform node has invalid configuration. A required option may be missing or have an invalid value.",
        "Use get_pipeline_state to see the node's current options, then use patch_node_options to fix.",
    ),
    (
        r"Invalid options for sink '(.+)':",
        "A sink output has invalid configuration. A required option may be missing (e.g. path for file-based sinks).",
        "Use get_pipeline_state to see the output's current options, then use patch_output_options to fix.",
    ),
    (
        r"Schema contract violation: '.*' -> 'output:[^']+'",
        "A sink schema requires fields that its upstream producer does not guarantee.",
        "Call preview_pipeline to inspect edge_contracts, then either relax the sink schema with patch_output_options or update the upstream schema with patch_source_options or patch_node_options and re-preview until the edge shows satisfied=true.",
    ),
    (
        r"Schema contract violation:",
        "A downstream node requires fields that its upstream producer does not guarantee.",
        "Call preview_pipeline to inspect edge_contracts, then update the upstream schema with patch_source_options or patch_node_options and re-preview until the edge shows satisfied=true.",
    ),
]


def _execute_explain_validation_error(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    """Explain a validation error with human-readable diagnosis and fix."""
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
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    """List available LLM model identifiers.

    Without a provider filter, returns provider names and model counts
    to avoid dumping hundreds of entries. With a provider filter,
    returns matching model IDs capped at ``limit``.
    """
    try:
        import litellm

        all_models: list[str] = sorted(litellm.model_list)
    except (ImportError, AttributeError):
        all_models = []

    provider = args.get("provider")
    limit = args.get("limit", 50)
    if not isinstance(limit, int) or limit < 1:
        limit = 50

    if provider is not None and isinstance(provider, str):
        if provider == "":
            # Empty string means "models without a provider prefix"
            filtered = [m for m in all_models if "/" not in m]
        else:
            filtered = [m for m in all_models if m.startswith(provider)]
        truncated = len(filtered) > limit
        data: dict[str, Any] = {
            "models": filtered[:limit],
            "count": len(filtered),
            "truncated": truncated,
        }
    else:
        # Group by provider prefix to avoid token waste
        providers: dict[str, int] = {}
        for m in all_models:
            prefix = m.split("/", 1)[0] if "/" in m else ""
            providers[prefix] = providers.get(prefix, 0) + 1
        data = {
            "providers": providers,
            "total_models": len(all_models),
            "hint": "Use provider parameter to list models for a specific provider. An empty string key means models without a provider prefix.",
        }

    return _discovery_result(state, data)


def _serialize_source(source: SourceSpec) -> dict[str, Any]:
    """Serialize a SourceSpec to a plain dict for LLM consumption."""
    return {
        "plugin": source.plugin,
        "on_success": source.on_success,
        "options": deep_thaw(source.options),
        "on_validation_failure": source.on_validation_failure,
    }


def _serialize_node(node: NodeSpec) -> dict[str, Any]:
    """Serialize a NodeSpec to a plain dict for LLM consumption.

    Includes all fields (even None) so the LLM sees the full schema.
    """
    return {
        "id": node.id,
        "node_type": node.node_type,
        "plugin": node.plugin,
        "input": node.input,
        "on_success": node.on_success,
        "on_error": node.on_error,
        "options": deep_thaw(node.options),
        "condition": node.condition,
        "routes": deep_thaw(node.routes) if node.routes else None,
        "fork_to": list(node.fork_to) if node.fork_to else None,
        "branches": list(node.branches) if node.branches else None,
        "policy": node.policy,
        "merge": node.merge,
        "trigger": deep_thaw(node.trigger) if node.trigger else None,
        "output_mode": node.output_mode,
        "expected_output_count": node.expected_output_count,
    }


def _serialize_output(output: OutputSpec) -> dict[str, Any]:
    """Serialize an OutputSpec to a plain dict for LLM consumption."""
    return {
        "sink_name": output.name,
        "plugin": output.plugin,
        "options": deep_thaw(output.options),
        "on_write_failure": output.on_write_failure,
    }


def _serialize_edge(edge: EdgeSpec) -> dict[str, Any]:
    """Serialize an EdgeSpec to a plain dict for LLM consumption."""
    return {
        "id": edge.id,
        "from_node": edge.from_node,
        "to_node": edge.to_node,
        "edge_type": edge.edge_type,
        "label": edge.label,
    }


def _execute_get_pipeline_state(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
) -> ToolResult:
    """Return full pipeline state including all options.

    If ``component`` is specified, returns only that component's details.
    Otherwise returns the full state: source, all nodes with options, all
    outputs with options, edges, and metadata.
    """
    component = args.get("component")

    if component == "source":
        data: Any = {"source": _serialize_source(state.source) if state.source is not None else None}
    elif component is not None:
        # Try node, then output
        node = next((n for n in state.nodes if n.id == component), None)
        if node is not None:
            data = {"node": _serialize_node(node)}
        else:
            output = next((o for o in state.outputs if o.name == component), None)
            if output is not None:
                data = {"output": _serialize_output(output)}
            else:
                return _failure_result(state, f"Component '{component}' not found. Specify 'source', a node ID, or an output name.")
    else:
        # Full state
        data = {
            "source": _serialize_source(state.source) if state.source is not None else None,
            "nodes": [_serialize_node(n) for n in state.nodes],
            "outputs": [_serialize_output(o) for o in state.outputs],
            "edges": [_serialize_edge(e) for e in state.edges],
            "metadata": {"name": state.metadata.name, "description": state.metadata.description},
            "version": state.version,
        }

    data = redact_source_storage_path(data)
    return _discovery_result(state, data)


def _execute_preview_pipeline(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
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
        "errors": [e.to_dict() for e in validation.errors],
        "warnings": [e.to_dict() for e in validation.warnings],
        "suggestions": [e.to_dict() for e in validation.suggestions],
        "edge_contracts": [ec.to_dict() for ec in validation.edge_contracts],
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
            "has_schema_config": _source_options_have_schema(state.source.options),
        }

    return ToolResult(
        success=True,
        updated_state=state,
        validation=validation,
        affected_nodes=(),
        data=summary,
    )


def _execute_diff_pipeline(
    args: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    *,
    baseline: CompositionState | None = None,
    current_validation: ValidationSummary | None = None,
) -> ToolResult:
    """Compute a diff/change summary against a baseline state.

    The baseline is passed explicitly by the MCP server or web composer.
    If no baseline is available, returns a notice instead.

    Args:
        current_validation: Pre-computed validation for the current state.
            Threaded from the caller to avoid redundant recomputation.
    """
    if baseline is None:
        return _discovery_result(
            state,
            {
                "error": "No baseline available. Load or create a session first.",
                "current_version": state.version,
            },
        )

    changes = diff_states(baseline, state, current_validation=current_validation)
    return _discovery_result(state, changes)


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
    "get_pipeline_state": _execute_get_pipeline_state,
    "preview_pipeline": _execute_preview_pipeline,
    "diff_pipeline": _execute_diff_pipeline,
}

# All discovery tools are cacheable. If a non-cacheable discovery tool is
# re-added in future (e.g. get_current_state which returns live mutable
# state), add it to _DISCOVERY_TOOLS but NOT to this frozenset.
_CACHEABLE_DISCOVERY_TOOLS: frozenset[str] = frozenset(_DISCOVERY_TOOLS.keys()) - {"diff_pipeline", "get_pipeline_state"}

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
    "get_blob_content": _execute_get_blob_content,
}

_BLOB_MUTATION_TOOLS: dict[str, BlobToolHandler] = {
    "set_source_from_blob": _execute_set_source_from_blob,
    "create_blob": _execute_create_blob,
    "update_blob": _execute_update_blob,
    "delete_blob": _execute_delete_blob,
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


def _inject_prior_validation(
    result: ToolResult,
    prior: ValidationSummary,
) -> ToolResult:
    """Attach prior validation to a successful mutation result for delta computation.

    Returns the result unchanged if the mutation failed or already carries
    prior_validation (set explicitly by the handler).
    """
    if result.success and result.prior_validation is None:
        return replace(result, prior_validation=prior)
    return result


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    state: CompositionState,
    catalog: CatalogService,
    data_dir: str | None = None,
    session_engine: Engine | None = None,
    session_id: str | None = None,
    secret_service: Any | None = None,
    user_id: str | None = None,
    baseline: CompositionState | None = None,
    prior_validation: ValidationSummary | None = None,
) -> ToolResult:
    """Execute a composition tool by name.

    Dispatches via registry dict. Discovery tools return data without
    modifying state. Mutation tools return ToolResult with updated state
    and validation. Unknown tool names return a failure result.

    Args:
        data_dir: Base data directory for S2 path allowlist enforcement.
            When provided, source options containing ``path`` or ``file``
            keys are restricted to ``{data_dir}/blobs/``.
        session_engine: SQLAlchemy engine for the session database.
            Required for blob tools to perform synchronous blob lookups.
        session_id: Current session ID. Required for blob tools.
        secret_service: WebSecretService instance. Required for secret tools.
        user_id: Current user ID. Required for secret tools.
        baseline: Baseline state for diff_pipeline comparisons.
        prior_validation: Pre-computed validation for the current state.
            When provided, mutation tools reuse this instead of calling
            state.validate() for the pre-mutation delta. Callers should
            thread the previous ToolResult.validation forward — the state
            is immutable, so validation is deterministic.
    """
    # diff_pipeline has an extended signature with baseline kwarg
    if tool_name == "diff_pipeline":
        return _execute_diff_pipeline(
            arguments,
            state,
            catalog,
            data_dir,
            baseline=baseline,
            current_validation=prior_validation,
        )

    # Check standard tools first
    discovery_handler = _DISCOVERY_TOOLS.get(tool_name)
    if discovery_handler is not None:
        return discovery_handler(arguments, state, catalog, data_dir)

    mutation_handler = _MUTATION_TOOLS.get(tool_name)
    if mutation_handler is not None:
        prior = prior_validation if prior_validation is not None else state.validate()
        result = mutation_handler(arguments, state, catalog, data_dir)
        return _inject_prior_validation(result, prior)

    # Check blob tools (extended signature with session context)
    blob_discovery = _BLOB_DISCOVERY_TOOLS.get(tool_name)
    if blob_discovery is not None:
        return blob_discovery(arguments, state, catalog, data_dir, session_engine=session_engine, session_id=session_id)

    blob_mutation = _BLOB_MUTATION_TOOLS.get(tool_name)
    if blob_mutation is not None:
        prior = prior_validation if prior_validation is not None else state.validate()
        result = blob_mutation(arguments, state, catalog, data_dir, session_engine=session_engine, session_id=session_id)
        return _inject_prior_validation(result, prior)

    # Check secret tools (extended signature with secret_service + user_id)
    secret_discovery = _SECRET_DISCOVERY_TOOLS.get(tool_name)
    if secret_discovery is not None:
        return secret_discovery(arguments, state, catalog, data_dir, secret_service=secret_service, user_id=user_id)

    secret_mutation = _SECRET_MUTATION_TOOLS.get(tool_name)
    if secret_mutation is not None:
        prior = prior_validation if prior_validation is not None else state.validate()
        result = secret_mutation(arguments, state, catalog, data_dir, secret_service=secret_service, user_id=user_id)
        return _inject_prior_validation(result, prior)

    return _failure_result(state, f"Unknown tool: {tool_name}")
