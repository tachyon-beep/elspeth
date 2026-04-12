# tests/core/test_dag_contract_validation.py
"""Tests for DAG schema contract validation (guaranteed/required fields)."""

from typing import Any

import pytest

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
        branch_schemas: Map of branch_name → SchemaConfig for each branch
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
    config = {"merge": "union", "branches": {}, "policy": policy}
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


class TestContractHelpers:
    """Tests for contract extraction helper methods."""

    def test_get_guaranteed_fields_from_dynamic_with_explicit(self) -> None:
        """Extract explicit guaranteed_fields from dynamic schema."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id", "name"]}},
        )

        result = graph.get_guaranteed_fields("source_1")
        assert result == frozenset({"id", "name"})

    def test_get_guaranteed_fields_from_explicit_schema(self) -> None:
        """Extract guaranteed fields from free mode schema (implicit from declared fields)."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "flexible", "fields": ["a: int", "b: str"]}},
        )

        result = graph.get_guaranteed_fields("source_1")
        assert result == frozenset({"a", "b"})

    def test_get_guaranteed_fields_empty_for_pure_dynamic(self) -> None:
        """Pure dynamic schema without explicit guarantees returns empty set."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )

        result = graph.get_guaranteed_fields("source_1")
        assert result == frozenset()

    def test_get_required_fields_from_required_input_fields(self) -> None:
        """Required fields from explicit required_input_fields config."""
        graph = ExecutionGraph()
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed"},
                "required_input_fields": ["customer_id", "amount"],
            },
        )

        result = graph.get_required_fields("transform_1")
        assert result == frozenset({"customer_id", "amount"})

    def test_get_required_fields_from_schema_required_fields(self) -> None:
        """Required fields from schema's required_fields (fallback)."""
        graph = ExecutionGraph()
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed", "required_fields": ["x", "y"]},
            },
        )

        result = graph.get_required_fields("transform_1")
        assert result == frozenset({"x", "y"})

    def test_get_required_fields_from_explicit_schema(self) -> None:
        """Implicit requirements from strict schema are NOT returned.

        Contract validation only considers explicit declarations
        (required_input_fields or required_fields). Type validation
        handles implicit requirements from typed schemas.
        """
        graph = ExecutionGraph()
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "fixed", "fields": ["id: int", "value: str"]}},
        )

        # Implicit requirements are NOT returned - type validation handles these
        result = graph.get_required_fields("sink_1")
        assert result == frozenset()

    def test_get_required_fields_from_explicit_required_fields(self) -> None:
        """Explicit required_fields in schema config ARE returned."""
        graph = ExecutionGraph()
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {
                    "mode": "observed",
                    "required_fields": ["customer_id", "amount"],
                },
            },
        )

        result = graph.get_required_fields("sink_1")
        assert result == frozenset({"customer_id", "amount"})

    def test_required_input_fields_takes_priority(self) -> None:
        """Explicit required_input_fields overrides schema's required_fields."""
        graph = ExecutionGraph()
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed", "required_fields": ["schema_req"]},
                "required_input_fields": ["config_req"],  # This wins
            },
        )

        result = graph.get_required_fields("transform_1")
        assert result == frozenset({"config_req"})


class TestEffectiveGuaranteedFields:
    """Tests for _get_effective_guaranteed_fields with pass-through nodes."""

    def test_source_guarantees_directly(self) -> None:
        """Source node's guarantees are returned directly."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a", "b"]}},
        )

        result = graph.get_effective_guaranteed_fields("source_1")
        assert result == frozenset({"a", "b"})

    def test_gate_uses_propagated_schema(self) -> None:
        """Gate node uses its own schema (propagated by builder from upstream).

        In production, the builder copies the upstream schema to gates.
        This test simulates that propagation — the gate's config already
        contains the upstream's guaranteed_fields.
        """
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["x", "y"]}},
        )
        graph.add_node(
            "gate_1",
            node_type=NodeType.GATE,
            plugin_name="config_gate",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["x", "y"]}},
        )
        graph.add_edge("source_1", "gate_1", label="continue")

        result = graph.get_effective_guaranteed_fields("gate_1")
        assert result == frozenset({"x", "y"})

    def test_coalesce_returns_intersection(self) -> None:
        """Coalesce node returns intersection of branch guarantees under best_effort.

        Under best_effort policy, branches may not arrive, so the merged
        guarantees are the intersection of branches' guaranteed_fields.
        Under require_all this would be the union — see
        test_dag_coalesce_optionality.py::test_require_all_* for that path.
        """
        graph = ExecutionGraph()

        # Fork gate with two branches
        graph.add_node(
            "gate_1",
            node_type=NodeType.GATE,
            plugin_name="fork_gate",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "branch_a"]}},
        )

        # Branch A source
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform_a",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only"]}},
        )

        # Branch B source
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform_b",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "b_only"]}},
        )

        # Compute merged schema BEFORE adding coalesce node (NodeInfo is frozen)
        branch_schemas = {
            "branch_a": graph.get_schema_config_from_node("branch_a"),
            "branch_b": graph.get_schema_config_from_node("branch_b"),
        }
        coalesce_schema = _compute_coalesce_schema(branch_schemas, policy="best_effort")
        graph.add_node(
            "coalesce_1",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce",
            config={"merge": "union", "branches": {}, "policy": "best_effort"},
            output_schema_config=coalesce_schema,
        )

        graph.add_edge("branch_a", "coalesce_1", label="path_a")
        graph.add_edge("branch_b", "coalesce_1", label="path_b")

        # Coalesce guarantees only the intersection (best_effort semantics)
        result = graph.get_effective_guaranteed_fields("coalesce_1")
        assert result == frozenset({"common"})


class TestContractValidation:
    """Tests for contract validation in _validate_single_edge."""

    def test_producer_satisfies_consumer(self) -> None:
        """Producer with guaranteed fields satisfies consumer requirements."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a", "b"]}},
        )
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed"},
                "required_input_fields": ["a"],  # Requires only 'a'
            },
        )
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "sink_1", label="continue")

        # Should not raise - producer guarantees what consumer needs
        graph.validate_edge_compatibility()

    def test_producer_missing_required_fails(self) -> None:
        """Producer without required field raises clear error."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a"]}},
        )
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed"},
                "required_input_fields": ["a", "b"],  # Requires 'b' which source doesn't have
            },
        )
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "sink_1", label="continue")

        with pytest.raises(ValueError, match="Schema contract violation"):
            graph.validate_edge_compatibility()

    def test_error_message_contains_missing_fields(self) -> None:
        """Error message shows exactly which fields are missing."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed"},
                "required_input_fields": ["customer_id", "order_amount"],
            },
        )
        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_edge("transform_1", "sink_1", label="continue")

        with pytest.raises(ValueError) as exc_info:
            graph.validate_edge_compatibility()

        error_message = str(exc_info.value)
        assert "customer_id" in error_message
        assert "order_amount" in error_message
        assert "Missing fields" in error_message

    def test_dynamic_producer_fails_requirements(self) -> None:
        """Dynamic producer cannot satisfy consumer requirements."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},  # No guarantees
        )
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed"},
                "required_input_fields": ["required_field"],
            },
        )
        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_edge("transform_1", "sink_1", label="continue")

        with pytest.raises(ValueError, match="none - dynamic schema"):
            graph.validate_edge_compatibility()

    def test_consumer_without_requirements_passes(self) -> None:
        """Consumer without required fields always passes contract check."""
        graph = ExecutionGraph()
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="passthrough",
            config={"schema": {"mode": "observed"}},  # No requirements
        )
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )
        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "sink_1", label="continue")

        # Should not raise - no requirements to satisfy
        graph.validate_edge_compatibility()


class TestChainValidation:
    """Tests for contract validation across multi-node chains."""

    def test_three_node_chain_catches_middle_gap(self) -> None:
        """Chain validation catches missing field in middle of chain."""
        graph = ExecutionGraph()

        # Source guarantees [a, b]
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a", "b"]}},
        )

        # Transform consumes [a], produces [a, c] (drops b, adds c)
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="mapper",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "c"]},
                "required_input_fields": ["a"],
            },
        )

        # Sink requires [a, b] - should fail because transform dropped b
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["a", "b"]},
            },
        )

        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "sink_1", label="continue")

        with pytest.raises(ValueError, match=r"Missing fields.*'b'"):
            graph.validate_edge_compatibility()

    def test_explicit_schema_combined_with_contract(self) -> None:
        """Explicit schema fields combine with contract fields for validation."""
        graph = ExecutionGraph()

        # Source with explicit free mode schema
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "flexible", "fields": ["id: int", "name: str"]}},
        )

        # Transform requires id (which source guarantees)
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="llm",
            config={
                "schema": {"mode": "observed"},
                "required_input_fields": ["id"],
            },
        )

        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},
        )

        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "sink_1", label="continue")

        # Should pass - source's explicit schema guarantees 'id'
        graph.validate_edge_compatibility()

    def test_five_node_chain_detects_late_gap(self) -> None:
        """Long chain where field dropped early is only required late."""
        graph = ExecutionGraph()

        # Source guarantees [a, b, c]
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c"]}},
        )

        # Transform 1: consumes [a], produces [a, b, c] (pass-through)
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="t1",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c"]},
                "required_input_fields": ["a"],
            },
        )

        # Transform 2: consumes [b], produces [a, b, c] (pass-through)
        graph.add_node(
            "transform_2",
            node_type=NodeType.TRANSFORM,
            plugin_name="t2",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c"]},
                "required_input_fields": ["b"],
            },
        )

        # Transform 3: consumes [c], produces [a, b, d] (DROPS c, adds d)
        graph.add_node(
            "transform_3",
            node_type=NodeType.TRANSFORM,
            plugin_name="t3",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "d"]},
                "required_input_fields": ["c"],
            },
        )

        # Sink requires [a, b, c] - should FAIL because c was dropped by transform_3
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["a", "b", "c"]},
            },
        )

        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "transform_2", label="continue")
        graph.add_edge("transform_2", "transform_3", label="continue")
        graph.add_edge("transform_3", "sink_1", label="continue")

        with pytest.raises(ValueError, match="'c'"):
            graph.validate_edge_compatibility()

    def test_five_node_chain_passes_when_contracts_satisfied(self) -> None:
        """Long chain where all contracts are satisfied passes validation."""
        graph = ExecutionGraph()

        # Source guarantees [a, b, c]
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c"]}},
        )

        # Transform 1: consumes [a], adds [d], keeps all
        graph.add_node(
            "transform_1",
            node_type=NodeType.TRANSFORM,
            plugin_name="t1",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c", "d"]},
                "required_input_fields": ["a"],
            },
        )

        # Transform 2: consumes [b], adds [e], keeps all
        graph.add_node(
            "transform_2",
            node_type=NodeType.TRANSFORM,
            plugin_name="t2",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c", "d", "e"]},
                "required_input_fields": ["b"],
            },
        )

        # Transform 3: consumes [c, d], adds [f], keeps all
        graph.add_node(
            "transform_3",
            node_type=NodeType.TRANSFORM,
            plugin_name="t3",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["a", "b", "c", "d", "e", "f"]},
                "required_input_fields": ["c", "d"],
            },
        )

        # Sink requires [a, b, c, f] - all should be guaranteed
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["a", "b", "c", "f"]},
            },
        )

        graph.add_edge("source_1", "transform_1", label="continue")
        graph.add_edge("transform_1", "transform_2", label="continue")
        graph.add_edge("transform_2", "transform_3", label="continue")
        graph.add_edge("transform_3", "sink_1", label="continue")

        # Should pass - all contracts satisfied
        graph.validate_edge_compatibility()


class TestGatePassthrough:
    """Tests for gates preserving upstream guarantees."""

    def test_gate_passes_through_guarantees(self) -> None:
        """Gate node passes upstream guarantees to downstream consumer.

        In production, the builder propagates the upstream schema to the gate.
        This test simulates that propagation.
        """
        graph = ExecutionGraph()

        # Source with guarantees
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["field_a"]}},
        )

        # Gate (passthrough — builder would copy source schema here)
        graph.add_node(
            "gate_1",
            node_type=NodeType.GATE,
            plugin_name="config_gate",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["field_a"]}},
        )

        # Sink requires field_a
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["field_a"]},
            },
        )

        graph.add_edge("source_1", "gate_1", label="continue")
        graph.add_edge("gate_1", "sink_1", label="continue")

        # Should pass - gate passes through source's guarantees
        graph.validate_edge_compatibility()


class TestForkCoalesceContracts:
    """Tests for fork → multiple branches → coalesce contract flows."""

    def test_fork_with_different_branch_transforms(self) -> None:
        """Fork gate to two branches with different transforms, coalesce guarantees union under require_all."""
        graph = ExecutionGraph()

        # Source guarantees base fields
        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id", "raw_data"]}},
        )

        # Fork gate (builder would propagate source schema here)
        graph.add_node(
            "fork_gate",
            node_type=NodeType.GATE,
            plugin_name="fork_gate",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id", "raw_data"]}},
        )

        # Branch A: adds 'classification' field
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="classifier",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["id", "raw_data", "classification"]},
                "required_input_fields": ["raw_data"],
            },
        )

        # Branch B: adds 'sentiment' field
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="sentiment_analyzer",
            config={
                "schema": {"mode": "observed", "guaranteed_fields": ["id", "raw_data", "sentiment"]},
                "required_input_fields": ["raw_data"],
            },
        )

        # Coalesce merges branches - guarantees UNION under require_all
        graph.add_node(
            "coalesce_1",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce",
            config={"schema": {"mode": "observed"}, "merge": "union", "branches": {}, "policy": "require_all"},
        )

        # Sink requires only 'id' (which is in union)
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["id"]},
            },
        )

        graph.add_edge("source_1", "fork_gate", label="continue")
        graph.add_edge("fork_gate", "branch_a", label="path_a")
        graph.add_edge("fork_gate", "branch_b", label="path_b")

        # Add coalesce with computed schema (must be done before adding edges TO it)
        _add_coalesce_with_computed_schema(graph, "coalesce_1", ["branch_a", "branch_b"], policy="require_all")

        graph.add_edge("branch_a", "coalesce_1", label="merge")
        graph.add_edge("branch_b", "coalesce_1", label="merge")
        graph.add_edge("coalesce_1", "sink_1", label="continue")

        # Should pass - sink requires 'id' which is in union
        graph.validate_edge_compatibility()

    def test_coalesce_intersection_rejects_branch_specific_requirement(self) -> None:
        """Under best_effort, a consumer after coalesce cannot require branch-specific fields.

        Under best_effort, the branch producing 'a_only' may be lost — the
        merged row may be missing it, so a sink requiring 'a_only' must be
        rejected at build time. Under require_all the same configuration
        would be valid — see test_dag_coalesce_optionality.py for that path.
        """
        graph = ExecutionGraph()

        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common"]}},
        )

        # Branch A: guarantees common + a_only
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform_a",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only"]}},
        )

        # Branch B: guarantees common + b_only
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform_b",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "b_only"]}},
        )

        graph.add_edge("source_1", "branch_a", label="path_a")
        graph.add_edge("source_1", "branch_b", label="path_b")

        # Add coalesce with computed schema (must be done before adding edges TO it)
        _add_coalesce_with_computed_schema(graph, "coalesce_1", ["branch_a", "branch_b"], policy="best_effort")

        # Sink requires 'a_only' - NOT guaranteed by coalesce (only 'common' is)
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["a_only"]},
            },
        )

        graph.add_edge("branch_a", "coalesce_1", label="merge")
        graph.add_edge("branch_b", "coalesce_1", label="merge")
        graph.add_edge("coalesce_1", "sink_1", label="continue")

        with pytest.raises(ValueError, match="a_only"):
            graph.validate_edge_compatibility()

    def test_coalesce_three_branches_intersection(self) -> None:
        """Coalesce with three branches takes intersection of all three."""
        graph = ExecutionGraph()

        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id"]}},
        )

        # Three branches with overlapping guarantees
        # Branch A: id, x, y
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="a",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id", "x", "y"]}},
        )

        # Branch B: id, x, z
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="b",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id", "x", "z"]}},
        )

        # Branch C: id, y, z
        graph.add_node(
            "branch_c",
            node_type=NodeType.TRANSFORM,
            plugin_name="c",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["id", "y", "z"]}},
        )

        # Add coalesce with computed schema (simulates builder)
        # Under require_all: union = {id, x, y, z}
        _add_coalesce_with_computed_schema(graph, "coalesce_1", ["branch_a", "branch_b", "branch_c"], policy="require_all")

        # Sink requires only 'id' (the only field guaranteed by ALL branches)
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["id"]},
            },
        )

        graph.add_edge("source_1", "branch_a", label="a")
        graph.add_edge("source_1", "branch_b", label="b")
        graph.add_edge("source_1", "branch_c", label="c")
        graph.add_edge("branch_a", "coalesce_1", label="merge")
        graph.add_edge("branch_b", "coalesce_1", label="merge")
        graph.add_edge("branch_c", "coalesce_1", label="merge")
        graph.add_edge("coalesce_1", "sink_1", label="continue")

        # Should pass - 'id' is in the union of all three branches
        graph.validate_edge_compatibility()

    def test_coalesce_empty_intersection_fails_requirements(self) -> None:
        """Coalesce with no common fields fails any downstream requirements."""
        graph = ExecutionGraph()

        graph.add_node(
            "source_1",
            node_type=NodeType.SOURCE,
            plugin_name="csv",
            config={"schema": {"mode": "observed"}},  # No guarantees
        )

        # Branch A: only guarantees 'a'
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="a",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["a"]}},
        )

        # Branch B: only guarantees 'b'
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="b",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["b"]}},
        )

        graph.add_node(
            "coalesce_1",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce",
            config={"schema": {"mode": "observed"}, "merge": "union", "branches": {}, "policy": "require_all"},
        )

        # Sink requires any field - will fail since intersection is empty
        graph.add_node(
            "sink_1",
            node_type=NodeType.SINK,
            plugin_name="csv",
            config={
                "schema": {"mode": "observed", "required_fields": ["any_field"]},
            },
        )

        graph.add_edge("source_1", "branch_a", label="a")
        graph.add_edge("source_1", "branch_b", label="b")
        graph.add_edge("branch_a", "coalesce_1", label="merge")
        graph.add_edge("branch_b", "coalesce_1", label="merge")
        graph.add_edge("coalesce_1", "sink_1", label="continue")

        with pytest.raises(ValueError, match="any_field"):
            graph.validate_edge_compatibility()


class TestCoalesceGuaranteedFieldsSemantics:
    """Tests for None vs empty-tuple distinction in coalesce guaranteed_fields.

    The intersection of guaranteed_fields across coalesce branches must
    distinguish between:
      None  = "observed schema, unknown fields" → abstain from intersection
      ()    = "explicitly guarantee zero fields" → participates, kills intersection

    Uses best_effort policy because intersection semantics is the correct
    merge for policies where branches can be lost (best_effort/quorum/first).
    Under require_all every branch always arrives, so the merged guarantees
    are the UNION (any branch's guarantee is in the merged row) — see
    test_dag_coalesce_optionality.py::test_require_all_* for that path.
    """

    def _build_coalesce_graph(
        self,
        branch_configs: dict[str, dict[str, Any]],
        *,
        policy: str = "best_effort",
    ) -> ExecutionGraph:
        """Build a coalesce graph with given schema configs.

        Simulates what the builder does: computes merged guarantees from
        branch schemas and sets output_schema_config on the coalesce node.
        """
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        # First pass: add branch nodes and collect their schemas
        branch_schemas: dict[str, SchemaConfig | None] = {}
        for branch_name, config in branch_configs.items():
            graph.add_node(
                branch_name,
                node_type=NodeType.TRANSFORM,
                plugin_name="transform",
                config=config,
            )
            graph.add_edge("source", branch_name, label=branch_name)
            # Get the parsed schema from the node we just added
            branch_schemas[branch_name] = graph.get_schema_config_from_node(branch_name)

        # Compute merged schema BEFORE adding coalesce node (NodeInfo is frozen)
        coalesce_schema = _compute_coalesce_schema(branch_schemas, policy=policy)

        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce",
            config={"merge": "union", "branches": {}, "policy": policy},
            output_schema_config=coalesce_schema,
        )
        for branch_name in branch_configs:
            graph.add_edge(branch_name, "coalesce", label="continue")

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")
        graph.add_edge("coalesce", "sink", label="continue")
        return graph

    def test_both_branches_with_guarantees_intersects(self) -> None:
        """Two branches with explicit guaranteed_fields → intersection."""
        graph = self._build_coalesce_graph(
            {
                "branch_a": {"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only"]}},
                "branch_b": {"schema": {"mode": "observed", "guaranteed_fields": ["common", "b_only"]}},
            }
        )
        result = graph.get_effective_guaranteed_fields("coalesce")
        assert result == frozenset({"common"})

    def test_one_branch_none_guarantees_abstains(self) -> None:
        """Branch with None guaranteed_fields abstains — doesn't kill intersection."""
        graph = self._build_coalesce_graph(
            {
                "branch_a": {"schema": {"mode": "observed", "guaranteed_fields": ["x", "y"]}},
                "branch_b": {"schema": {"mode": "observed"}},  # guaranteed_fields=None
            }
        )
        result = graph.get_effective_guaranteed_fields("coalesce")
        # branch_b abstains, so branch_a's guarantees survive
        assert result == frozenset({"x", "y"})

    def test_all_branches_none_guarantees_returns_empty(self) -> None:
        """All branches with None guaranteed_fields → no guarantees (empty set)."""
        graph = self._build_coalesce_graph(
            {
                "branch_a": {"schema": {"mode": "observed"}},
                "branch_b": {"schema": {"mode": "observed"}},
            }
        )
        result = graph.get_effective_guaranteed_fields("coalesce")
        assert result == frozenset()

    def test_empty_list_guarantees_treated_as_none(self) -> None:
        """Empty list in config is normalized to None by _parse_field_names_list → abstains."""
        graph = self._build_coalesce_graph(
            {
                "branch_a": {"schema": {"mode": "observed", "guaranteed_fields": ["x", "y"]}},
                "branch_b": {"schema": {"mode": "observed", "guaranteed_fields": []}},  # [] → None
            }
        )
        result = graph.get_effective_guaranteed_fields("coalesce")
        # Empty list is parsed as None (unspecified), so branch_b abstains
        assert result == frozenset({"x", "y"})

    def test_explicit_empty_tuple_kills_intersection(self) -> None:
        """SchemaConfig with guaranteed_fields=() (Python API) participates and kills intersection.

        This distinction only exists at the Python API level — config parsing
        normalizes [] to None. A transform that explicitly constructs
        SchemaConfig(guaranteed_fields=()) is saying "I guarantee zero fields."
        """
        from elspeth.contracts.schema import SchemaConfig

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["x", "y"]}},
        )
        # Manually set output_schema_config with explicit empty tuple
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={},
            output_schema_config=SchemaConfig(mode="observed", fields=None, guaranteed_fields=()),
        )

        # Add coalesce with computed schema (simulates builder)
        # branch_b explicitly guarantees nothing → intersection is ∅ (best_effort)
        _add_coalesce_with_computed_schema(graph, "coalesce", ["branch_a", "branch_b"], policy="best_effort")

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        graph.add_edge("source", "branch_a", label="a")
        graph.add_edge("source", "branch_b", label="b")
        graph.add_edge("branch_a", "coalesce", label="continue")
        graph.add_edge("branch_b", "coalesce", label="continue")
        graph.add_edge("coalesce", "sink", label="continue")

        result = graph.get_effective_guaranteed_fields("coalesce")
        assert result == frozenset()

    def test_three_branches_mixed_none_and_explicit(self) -> None:
        """Three branches: two explicit, one None → intersection of explicit only."""
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["x", "y", "z"]}},
        )
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["x", "z"]}},
        )
        graph.add_node(
            "branch_c",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed"}},  # None → abstains
        )
        # Add coalesce with computed schema (simulates builder)
        # branch_c abstains, intersection of a ∩ b = {"x", "z"}
        _add_coalesce_with_computed_schema(graph, "coalesce", ["branch_a", "branch_b", "branch_c"], policy="best_effort")

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        for b in ("branch_a", "branch_b", "branch_c"):
            graph.add_edge("source", b, label=b)
            graph.add_edge(b, "coalesce", label="continue")
        graph.add_edge("coalesce", "sink", label="continue")

        result = graph.get_effective_guaranteed_fields("coalesce")
        assert result == frozenset({"x", "z"})

    def test_typed_required_fields_participate_without_explicit_guaranteed_fields(
        self,
    ) -> None:
        """Typed required fields contribute guarantees even when guaranteed_fields=None.

        Bug reproduction: A branch with mode="fixed", fields=(id, x) required=True,
        but guaranteed_fields=None should still contribute {id, x} to the coalesce
        merge. The declares_guaranteed_fields property only checks explicit
        guaranteed_fields, but get_effective_guaranteed_fields() includes typed
        required fields — the coalesce merge loop must consider both sources.

        Under require_all, both branches always arrive, so:
        - branch_a contributes {id, x} from typed required fields
        - branch_b contributes {id} from typed required fields
        - Merged guarantees = {id, x} (union under require_all)
        """
        from elspeth.contracts.schema import FieldDefinition, SchemaConfig

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        # Branch A: typed fields (id, x) required, NO explicit guaranteed_fields
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={},
            output_schema_config=SchemaConfig(
                mode="fixed",
                fields=(
                    FieldDefinition("id", "int", required=True),
                    FieldDefinition("x", "str", required=True),
                ),
                guaranteed_fields=None,  # Abstains from explicit declaration
            ),
        )

        # Branch B: typed field (id) required, NO explicit guaranteed_fields
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={},
            output_schema_config=SchemaConfig(
                mode="fixed",
                fields=(FieldDefinition("id", "int", required=True),),
                guaranteed_fields=None,  # Abstains from explicit declaration
            ),
        )

        # Add coalesce with computed schema (simulates builder)
        # Both branches have typed required fields that ARE effective guarantees
        # Under require_all, merged guarantees = union = {id, x}
        _add_coalesce_with_computed_schema(graph, "coalesce", ["branch_a", "branch_b"], policy="require_all")

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        for b in ("branch_a", "branch_b"):
            graph.add_edge("source", b, label=b)
            graph.add_edge(b, "coalesce", label="continue")
        graph.add_edge("coalesce", "sink", label="continue")

        result = graph.get_effective_guaranteed_fields("coalesce")
        assert result == frozenset({"id", "x"})

    def test_quorum_equal_to_branch_count_uses_union_semantics(self) -> None:
        """quorum_count == len(branches) is semantically identical to require_all.

        Bug reproduction: policy='quorum' with quorum_count == 2 and 2 branches
        is runtime-equivalent to require_all — _should_merge() waits for all,
        _evaluate_after_loss() fails on any loss. But the builder was using
        intersection semantics, rejecting valid branch-exclusive field requirements.

        Under quorum=N (where N == branch_count), every branch always arrives,
        so the union of branch guarantees should be the merged guarantees.
        """
        # Build with quorum policy directly (quorum_count == len(branches) uses union semantics)
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only"]}},
        )
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "b_only"]}},
        )

        for b in ("branch_a", "branch_b"):
            graph.add_edge("source", b, label=b)

        # Add coalesce with computed schema (simulates builder)
        # quorum=2 with 2 branches == require_all semantics → UNION
        # Note: we pass policy="require_all" to get union semantics,
        # but the node config still says "quorum" with quorum_count=2
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce",
            ["branch_a", "branch_b"],
            policy="require_all",  # quorum=N uses union like require_all
            extra_config={
                "branches": {"branch_a": {}, "branch_b": {}},
                "policy": "quorum",
                "quorum_count": 2,
            },
        )

        for b in ("branch_a", "branch_b"):
            graph.add_edge(b, "coalesce", label="continue")

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")
        graph.add_edge("coalesce", "sink", label="continue")

        result = graph.get_effective_guaranteed_fields("coalesce")
        assert result == frozenset({"common", "a_only", "b_only"})


class TestNestedCoalesceSchemaProgation:
    """Tests for schema propagation through nested coalesce nodes.

    When coalesce nodes chain (coalesce1 feeds into coalesce2), the downstream
    coalesce must see the computed guarantees of its upstream coalesce, not
    the raw branch schemas. This verifies transitive propagation works correctly.

    Example topology:
        source → branch_a ─┐
                           ├─→ coalesce_inner ─┐
        source → branch_b ─┘                   │
                                               ├─→ coalesce_outer → sink
        source → branch_c ───────────────────→─┘
    """

    def test_nested_coalesce_require_all_union_propagates(self) -> None:
        """Nested require_all coalesces propagate union guarantees transitively.

        Inner coalesce (require_all): union of branch_a | branch_b
        Outer coalesce (require_all): union of inner | branch_c

        The outer coalesce must see the inner's computed union, not recompute
        from the inner's raw predecessors.
        """
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        # Branch A: guarantees {common, a_only}
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only"]}},
        )

        # Branch B: guarantees {common, b_only}
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "b_only"]}},
        )

        # Branch C: guarantees {common, c_only}
        graph.add_node(
            "branch_c",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "c_only"]}},
        )

        # Inner coalesce (require_all): union of A | B = {common, a_only, b_only}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_inner",
            ["branch_a", "branch_b"],
            policy="require_all",
            extra_config={"branches": {"branch_a": {}, "branch_b": {}}},
        )

        # Outer coalesce (require_all): union of inner | C
        # Inner contributes {common, a_only, b_only}, C contributes {common, c_only}
        # Expected: {common, a_only, b_only, c_only}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_outer",
            ["coalesce_inner", "branch_c"],
            policy="require_all",
            extra_config={"branches": {"coalesce_inner": {}, "branch_c": {}}},
        )

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        # Wire up edges
        graph.add_edge("source", "branch_a", label="a")
        graph.add_edge("source", "branch_b", label="b")
        graph.add_edge("source", "branch_c", label="c")
        graph.add_edge("branch_a", "coalesce_inner", label="continue")
        graph.add_edge("branch_b", "coalesce_inner", label="continue")
        graph.add_edge("coalesce_inner", "coalesce_outer", label="continue")
        graph.add_edge("branch_c", "coalesce_outer", label="continue")
        graph.add_edge("coalesce_outer", "sink", label="continue")

        # Verify inner coalesce has correct guarantees
        inner_result = graph.get_effective_guaranteed_fields("coalesce_inner")
        assert inner_result == frozenset({"common", "a_only", "b_only"}), f"Inner coalesce should have union of A | B, got {inner_result}"

        # Verify outer coalesce sees inner's computed guarantees
        outer_result = graph.get_effective_guaranteed_fields("coalesce_outer")
        assert outer_result == frozenset({"common", "a_only", "b_only", "c_only"}), (
            f"Outer coalesce should have union of inner | C, got {outer_result}"
        )

    def test_nested_coalesce_best_effort_intersection_propagates(self) -> None:
        """Nested best_effort coalesces propagate intersection guarantees transitively.

        Inner coalesce (best_effort): intersection of branch_a ∩ branch_b
        Outer coalesce (best_effort): intersection of inner ∩ branch_c

        The outer coalesce must see the inner's computed intersection.
        """
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        # Branch A: guarantees {common, shared_ab, a_only}
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "shared_ab", "a_only"]}},
        )

        # Branch B: guarantees {common, shared_ab, b_only}
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "shared_ab", "b_only"]}},
        )

        # Branch C: guarantees {common, c_only}
        graph.add_node(
            "branch_c",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "c_only"]}},
        )

        # Inner coalesce (best_effort): intersection of A ∩ B = {common, shared_ab}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_inner",
            ["branch_a", "branch_b"],
            policy="best_effort",
            extra_config={"branches": {"branch_a": {}, "branch_b": {}}},
        )

        # Outer coalesce (best_effort): intersection of inner ∩ C
        # Inner contributes {common, shared_ab}, C contributes {common, c_only}
        # Expected: {common} (only field in both)
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_outer",
            ["coalesce_inner", "branch_c"],
            policy="best_effort",
            extra_config={"branches": {"coalesce_inner": {}, "branch_c": {}}},
        )

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        # Wire up edges
        graph.add_edge("source", "branch_a", label="a")
        graph.add_edge("source", "branch_b", label="b")
        graph.add_edge("source", "branch_c", label="c")
        graph.add_edge("branch_a", "coalesce_inner", label="continue")
        graph.add_edge("branch_b", "coalesce_inner", label="continue")
        graph.add_edge("coalesce_inner", "coalesce_outer", label="continue")
        graph.add_edge("branch_c", "coalesce_outer", label="continue")
        graph.add_edge("coalesce_outer", "sink", label="continue")

        # Verify inner coalesce has correct guarantees
        inner_result = graph.get_effective_guaranteed_fields("coalesce_inner")
        assert inner_result == frozenset({"common", "shared_ab"}), f"Inner coalesce should have intersection of A ∩ B, got {inner_result}"

        # Verify outer coalesce sees inner's computed guarantees
        outer_result = graph.get_effective_guaranteed_fields("coalesce_outer")
        assert outer_result == frozenset({"common"}), f"Outer coalesce should have intersection of inner ∩ C, got {outer_result}"

    def test_nested_coalesce_mixed_policies(self) -> None:
        """Mixed policies: inner require_all (union) feeds outer best_effort (intersection).

        This tests the edge case where policy changes between nesting levels.
        The outer must see the inner's union result, then intersect with branch_c.
        """
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        # Branch A: guarantees {common, a_only}
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only"]}},
        )

        # Branch B: guarantees {common, b_only}
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "b_only"]}},
        )

        # Branch C: guarantees {common, a_only, c_only}
        # Note: a_only is in both A and C, but not B
        graph.add_node(
            "branch_c",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["common", "a_only", "c_only"]}},
        )

        # Inner coalesce (require_all): union of A | B = {common, a_only, b_only}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_inner",
            ["branch_a", "branch_b"],
            policy="require_all",
            extra_config={"branches": {"branch_a": {}, "branch_b": {}}},
        )

        # Outer coalesce (best_effort): intersection of inner ∩ C
        # Inner contributes {common, a_only, b_only}, C contributes {common, a_only, c_only}
        # Expected: {common, a_only} (fields in both)
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_outer",
            ["coalesce_inner", "branch_c"],
            policy="best_effort",
            extra_config={"branches": {"coalesce_inner": {}, "branch_c": {}}},
        )

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        # Wire up edges
        graph.add_edge("source", "branch_a", label="a")
        graph.add_edge("source", "branch_b", label="b")
        graph.add_edge("source", "branch_c", label="c")
        graph.add_edge("branch_a", "coalesce_inner", label="continue")
        graph.add_edge("branch_b", "coalesce_inner", label="continue")
        graph.add_edge("coalesce_inner", "coalesce_outer", label="continue")
        graph.add_edge("branch_c", "coalesce_outer", label="continue")
        graph.add_edge("coalesce_outer", "sink", label="continue")

        # Verify inner coalesce has correct guarantees (union)
        inner_result = graph.get_effective_guaranteed_fields("coalesce_inner")
        assert inner_result == frozenset({"common", "a_only", "b_only"}), f"Inner coalesce should have union of A | B, got {inner_result}"

        # Verify outer coalesce: intersection of inner's union with C
        outer_result = graph.get_effective_guaranteed_fields("coalesce_outer")
        assert outer_result == frozenset({"common", "a_only"}), f"Outer coalesce should have intersection of inner | C, got {outer_result}"

    def test_three_level_nested_coalesce(self) -> None:
        """Three-level nesting: coalesce1 → coalesce2 → coalesce3.

        Verifies that schema propagation works through arbitrary depth.
        """
        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")

        # Level 1 branches
        graph.add_node(
            "branch_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["all", "level1_shared", "a"]}},
        )
        graph.add_node(
            "branch_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["all", "level1_shared", "b"]}},
        )

        # Level 2 branch
        graph.add_node(
            "branch_c",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["all", "level2_shared", "c"]}},
        )

        # Level 3 branch
        graph.add_node(
            "branch_d",
            node_type=NodeType.TRANSFORM,
            plugin_name="transform",
            config={"schema": {"mode": "observed", "guaranteed_fields": ["all", "d"]}},
        )

        # Level 1 coalesce (best_effort): A ∩ B = {all, level1_shared}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_1",
            ["branch_a", "branch_b"],
            policy="best_effort",
            extra_config={"branches": {"branch_a": {}, "branch_b": {}}},
        )

        # Level 2 coalesce (best_effort): coalesce_1 ∩ C = {all}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_2",
            ["coalesce_1", "branch_c"],
            policy="best_effort",
            extra_config={"branches": {"coalesce_1": {}, "branch_c": {}}},
        )

        # Level 3 coalesce (best_effort): coalesce_2 ∩ D = {all}
        _add_coalesce_with_computed_schema(
            graph,
            "coalesce_3",
            ["coalesce_2", "branch_d"],
            policy="best_effort",
            extra_config={"branches": {"coalesce_2": {}, "branch_d": {}}},
        )

        graph.add_node("sink", node_type=NodeType.SINK, plugin_name="csv")

        # Wire up edges
        for branch in ("branch_a", "branch_b", "branch_c", "branch_d"):
            graph.add_edge("source", branch, label=branch)
        graph.add_edge("branch_a", "coalesce_1", label="continue")
        graph.add_edge("branch_b", "coalesce_1", label="continue")
        graph.add_edge("coalesce_1", "coalesce_2", label="continue")
        graph.add_edge("branch_c", "coalesce_2", label="continue")
        graph.add_edge("coalesce_2", "coalesce_3", label="continue")
        graph.add_edge("branch_d", "coalesce_3", label="continue")
        graph.add_edge("coalesce_3", "sink", label="continue")

        # Verify each level
        assert graph.get_effective_guaranteed_fields("coalesce_1") == frozenset({"all", "level1_shared"})
        assert graph.get_effective_guaranteed_fields("coalesce_2") == frozenset({"all"})
        assert graph.get_effective_guaranteed_fields("coalesce_3") == frozenset({"all"})
