# src/elspeth/core/landscape/_graph_recording.py
"""Node and edge registration methods for LandscapeRecorder."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from elspeth.contracts import (
    ContractAuditRecord,
    Determinism,
    Edge,
    Node,
    NodeType,
    RoutingMode,
)
from elspeth.core.canonical import canonical_json, stable_hash
from elspeth.core.landscape._helpers import generate_id, now
from elspeth.core.landscape.schema import (
    edges_table,
    nodes_table,
)

if TYPE_CHECKING:
    from elspeth.contracts.schema import SchemaConfig
    from elspeth.contracts.schema_contract import SchemaContract
    from elspeth.core.landscape._database_ops import DatabaseOps
    from elspeth.core.landscape.database import LandscapeDB
    from elspeth.core.landscape.repositories import EdgeRepository, NodeRepository


class GraphRecordingMixin:
    """Node and edge registration methods. Mixed into LandscapeRecorder."""

    # Shared state annotations (set by LandscapeRecorder.__init__)
    _db: LandscapeDB
    _ops: DatabaseOps
    _node_repo: NodeRepository
    _edge_repo: EdgeRepository

    def register_node(
        self,
        run_id: str,
        plugin_name: str,
        node_type: NodeType,
        plugin_version: str,
        config: dict[str, Any],
        *,
        node_id: str | None = None,
        sequence: int | None = None,
        schema_hash: str | None = None,
        determinism: Determinism = Determinism.DETERMINISTIC,
        schema_config: SchemaConfig,
        input_contract: SchemaContract | None = None,
        output_contract: SchemaContract | None = None,
    ) -> Node:
        """Register a plugin instance (node) in the execution graph.

        Args:
            run_id: Run this node belongs to
            plugin_name: Name of the plugin
            node_type: NodeType enum (SOURCE, TRANSFORM, GATE, AGGREGATION, COALESCE, SINK)
            plugin_version: Version of the plugin
            config: Plugin configuration
            node_id: Optional node ID (generated if not provided)
            sequence: Position in pipeline
            schema_hash: Optional input/output schema hash
            determinism: Determinism enum (defaults to DETERMINISTIC)
            schema_config: Schema configuration for audit trail (WP-11.99)
            input_contract: Optional input schema contract (what node requires)
            output_contract: Optional output schema contract (what node guarantees)

        Returns:
            Node model
        """
        node_id = node_id or generate_id()
        config_json = canonical_json(config)
        config_hash = stable_hash(config)
        timestamp = now()

        # Extract schema info for audit (WP-11.99)
        schema_fields_json: str | None = None
        schema_fields_list: list[dict[str, object]] | None = None

        # Extract schema mode directly - no translation needed
        schema_mode = schema_config.mode
        if not schema_config.is_observed and schema_config.fields:
            # FieldDefinition.to_dict() returns dict[str, str | bool]
            # Cast each dict to wider type for storage
            field_dicts = [f.to_dict() for f in schema_config.fields]
            schema_fields_list = [dict(d) for d in field_dicts]
            schema_fields_json = canonical_json(field_dicts)

        # Convert schema contracts to audit records if provided
        input_contract_json: str | None = None
        output_contract_json: str | None = None
        if input_contract is not None:
            input_contract_json = ContractAuditRecord.from_contract(input_contract).to_json()
        if output_contract is not None:
            output_contract_json = ContractAuditRecord.from_contract(output_contract).to_json()

        node = Node(
            node_id=node_id,
            run_id=run_id,
            plugin_name=plugin_name,
            node_type=node_type,
            plugin_version=plugin_version,
            determinism=determinism,
            config_hash=config_hash,
            config_json=config_json,
            schema_hash=schema_hash,
            sequence_in_pipeline=sequence,
            registered_at=timestamp,
            schema_mode=schema_mode,
            schema_fields=schema_fields_list,
        )

        self._ops.execute_insert(
            nodes_table.insert().values(
                node_id=node.node_id,
                run_id=node.run_id,
                plugin_name=node.plugin_name,
                node_type=node.node_type.value,  # Store string in DB
                plugin_version=node.plugin_version,
                determinism=node.determinism.value,  # Store string in DB
                config_hash=node.config_hash,
                config_json=node.config_json,
                schema_hash=node.schema_hash,
                sequence_in_pipeline=node.sequence_in_pipeline,
                registered_at=node.registered_at,
                schema_mode=node.schema_mode,
                schema_fields_json=schema_fields_json,
                input_contract_json=input_contract_json,
                output_contract_json=output_contract_json,
            )
        )

        return node

    def register_edge(
        self,
        run_id: str,
        from_node_id: str,
        to_node_id: str,
        label: str,
        mode: RoutingMode,
        *,
        edge_id: str | None = None,
    ) -> Edge:
        """Register an edge in the execution graph.

        Args:
            run_id: Run this edge belongs to
            from_node_id: Source node
            to_node_id: Destination node
            label: Edge label ("continue", route name, etc.)
            mode: RoutingMode enum (MOVE or COPY)
            edge_id: Optional edge ID (generated if not provided)

        Returns:
            Edge model
        """
        edge_id = edge_id or generate_id()
        timestamp = now()

        edge = Edge(
            edge_id=edge_id,
            run_id=run_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            label=label,
            default_mode=mode,
            created_at=timestamp,
        )

        self._ops.execute_insert(
            edges_table.insert().values(
                edge_id=edge.edge_id,
                run_id=edge.run_id,
                from_node_id=edge.from_node_id,
                to_node_id=edge.to_node_id,
                label=edge.label,
                default_mode=edge.default_mode.value,  # Store string in DB
                created_at=edge.created_at,
            )
        )

        return edge

    def get_node(self, node_id: str, run_id: str) -> Node | None:
        """Get a node by its composite primary key (node_id, run_id).

        NOTE: The nodes table has a composite PK (node_id, run_id). The same
        node_id can exist in multiple runs, so run_id is required to identify
        the specific node.

        Args:
            node_id: Node ID to retrieve
            run_id: Run ID the node belongs to

        Returns:
            Node model or None if not found
        """
        query = select(nodes_table).where((nodes_table.c.node_id == node_id) & (nodes_table.c.run_id == run_id))
        row = self._ops.execute_fetchone(query)
        if row is None:
            return None
        return self._node_repo.load(row)

    def get_nodes(self, run_id: str) -> list[Node]:
        """Get all nodes for a run.

        Args:
            run_id: Run ID

        Returns:
            List of Node models, ordered by sequence (NULL sequences last)
        """
        query = (
            select(nodes_table)
            .where(nodes_table.c.run_id == run_id)
            # Use nullslast() for consistent NULL handling across databases
            # Nodes without sequence (e.g., dynamically added) sort last
            # Tiebreakers (registered_at, node_id) ensure deterministic ordering
            # for export signing when sequence_in_pipeline is NULL
            .order_by(
                nodes_table.c.sequence_in_pipeline.nullslast(),
                nodes_table.c.registered_at,
                nodes_table.c.node_id,
            )
        )
        rows = self._ops.execute_fetchall(query)
        return [self._node_repo.load(row) for row in rows]

    def get_node_contracts(self, run_id: str, node_id: str) -> tuple[SchemaContract | None, SchemaContract | None]:
        """Get input and output contracts for a node.

        Retrieves stored schema contracts and verifies integrity via hash.

        Args:
            run_id: Run ID the node belongs to
            node_id: Node ID to query

        Returns:
            Tuple of (input_contract, output_contract), either may be None

        Raises:
            ValueError: If stored contract fails integrity verification
        """
        query = select(
            nodes_table.c.input_contract_json,
            nodes_table.c.output_contract_json,
        ).where((nodes_table.c.node_id == node_id) & (nodes_table.c.run_id == run_id))
        row = self._ops.execute_fetchone(query)

        if row is None:
            return None, None

        input_contract: SchemaContract | None = None
        output_contract: SchemaContract | None = None

        if row.input_contract_json is not None:
            audit_record = ContractAuditRecord.from_json(row.input_contract_json)
            input_contract = audit_record.to_schema_contract()

        if row.output_contract_json is not None:
            audit_record = ContractAuditRecord.from_json(row.output_contract_json)
            output_contract = audit_record.to_schema_contract()

        return input_contract, output_contract

    def get_edges(self, run_id: str) -> list[Edge]:
        """Get all edges for a run.

        Args:
            run_id: Run ID

        Returns:
            List of Edge models for this run, ordered by created_at then edge_id
            for deterministic export signatures.
        """
        query = select(edges_table).where(edges_table.c.run_id == run_id).order_by(edges_table.c.created_at, edges_table.c.edge_id)
        rows = self._ops.execute_fetchall(query)
        return [self._edge_repo.load(row) for row in rows]

    def get_edge(self, edge_id: str) -> Edge:
        """Get a single edge by ID.

        Tier 1: crash on missing — an edge_id from our own routing_events
        table MUST resolve. Missing means audit DB corruption.

        Args:
            edge_id: Edge ID to look up

        Returns:
            Edge model

        Raises:
            ValueError: If edge not found (audit integrity violation)
        """
        query = select(edges_table).where(edges_table.c.edge_id == edge_id)
        row = self._ops.execute_fetchone(query)
        if row is None:
            raise ValueError(
                f"Audit integrity violation: edge '{edge_id}' not found. "
                f"A routing_event references a non-existent edge. "
                f"This indicates database corruption."
            )
        return self._edge_repo.load(row)

    def get_edge_map(self, run_id: str) -> dict[tuple[str, str], str]:
        """Get edge mapping for a run (from_node_id, label) -> edge_id.

        Args:
            run_id: Run to query

        Returns:
            Dictionary mapping (from_node_id, label) to edge_id

        Raises:
            ValueError: If run has no edges registered (data corruption)

        Note:
            This encapsulates Landscape schema access for Orchestrator resume.
            Edge IDs are required for FK integrity when recording routing events.
        """
        query = select(edges_table).where(edges_table.c.run_id == run_id)
        edges = self._ops.execute_fetchall(query)

        edge_map: dict[tuple[str, str], str] = {}
        for edge in edges:
            edge_map[(edge.from_node_id, edge.label)] = edge.edge_id

        return edge_map

    def update_node_output_contract(
        self,
        run_id: str,
        node_id: str,
        contract: SchemaContract,
    ) -> None:
        """Update a node's output_contract after first-row inference or schema evolution.

        Called in two scenarios:
        1. Source infers schema from first valid row during OBSERVED mode
        2. Transform adds fields during execution (schema evolution)

        Args:
            run_id: Run containing the node
            node_id: Node to update (source or transform node)
            contract: SchemaContract with inferred/evolved fields

        Note:
            This is the complement to update_run_contract() for node-level contracts.
            Used for dynamic schema discovery and transform schema evolution.
        """
        audit_record = ContractAuditRecord.from_contract(contract)
        output_contract_json = audit_record.to_json()

        self._ops.execute_update(
            nodes_table.update()
            .where((nodes_table.c.run_id == run_id) & (nodes_table.c.node_id == node_id))
            .values(output_contract_json=output_contract_json)
        )
