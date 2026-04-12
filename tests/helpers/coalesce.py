# tests/helpers/coalesce.py
"""Coalesce schema computation helpers for DAG tests.

These functions mirror builder.py logic for tests that construct graphs directly,
computing merged schemas for coalesce nodes from their predecessor branch schemas.
"""

from __future__ import annotations

from typing import Any

from elspeth.contracts import NodeType
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.dag import ExecutionGraph


def _compute_coalesce_schema(
    branch_schemas: dict[str, SchemaConfig | None],
    *,
    policy: str = "best_effort",
) -> SchemaConfig:
    """Compute merged schema for a coalesce node from branch schemas.

    Mirrors builder.py logic for tests that construct graphs directly.
    Must be called BEFORE adding the coalesce node to the graph (because
    NodeInfo is frozen and can't be modified after creation).

    Args:
        branch_schemas: Map of branch_name -> SchemaConfig for each branch
        policy: Coalesce policy ("require_all" uses union, others use intersection)

    Returns:
        SchemaConfig with computed guaranteed_fields for the coalesce node
    """
    guaranteed_sets: list[set[str]] = []
    for schema in branch_schemas.values():
        if schema is not None and schema.has_effective_guarantees:
            guaranteed_sets.append(set(schema.get_effective_guaranteed_fields()))

    if not guaranteed_sets:
        return SchemaConfig(mode="observed", fields=None, guaranteed_fields=None)

    # Policy determines union vs intersection
    if policy == "require_all":
        merged = set.union(*guaranteed_sets)
    else:
        merged = set.intersection(*guaranteed_sets)

    merged_tuple = tuple(sorted(merged)) if merged else ()
    return SchemaConfig(mode="observed", fields=None, guaranteed_fields=merged_tuple)


def _add_coalesce_with_computed_schema(
    graph: ExecutionGraph,
    coalesce_node_id: str,
    branch_node_ids: list[str],
    *,
    policy: str = "best_effort",
    extra_config: dict[str, Any] | None = None,
) -> None:
    """Add a coalesce node with computed schema from its predecessor branches.

    This is a convenience helper for tests that construct graphs directly.
    It collects branch schemas, computes the merged schema, and adds the
    coalesce node with the correct output_schema_config.

    Args:
        graph: The ExecutionGraph to add the node to
        coalesce_node_id: ID for the coalesce node
        branch_node_ids: List of branch node IDs to compute guarantees from
        policy: Coalesce policy ("require_all" uses union, others use intersection)
        extra_config: Additional config dict entries for the coalesce node
    """
    # Collect branch schemas
    branch_schemas = {node_id: graph.get_schema_config_from_node(node_id) for node_id in branch_node_ids}

    # Compute merged schema
    coalesce_schema = _compute_coalesce_schema(branch_schemas, policy=policy)

    # Build config
    config: dict[str, Any] = {"merge": "union", "branches": {}, "policy": policy}
    if extra_config:
        config.update(extra_config)

    # Add coalesce node with computed schema
    graph.add_node(
        coalesce_node_id,
        node_type=NodeType.COALESCE,
        plugin_name="coalesce",
        config=config,
        output_schema_config=coalesce_schema,
    )
