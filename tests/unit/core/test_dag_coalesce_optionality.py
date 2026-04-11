# tests/unit/core/test_dag_coalesce_optionality.py
"""Tests for field optionality preservation in coalesce union merge schema.

Fix: builder.py union merge was stripping optionality markers from branch
field specs, making all merged fields appear required. Now uses SchemaConfig
and FieldDefinition directly — optionality is a first-class boolean field.
"""

from __future__ import annotations

import pytest

from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.core.dag.models import GraphValidationError


class TestUnionMergeOptionalityPreservation:
    """Tests for optionality in union merge using SchemaConfig objects.

    These simulate the builder's coalesce merge logic to verify that
    FieldDefinition.required flags survive the merge correctly.
    """

    def _merge_schemas(
        self,
        branch_schemas: dict[str, SchemaConfig],
    ) -> SchemaConfig:
        """Simulate the builder's union merge logic with SchemaConfig objects."""
        seen_types: dict[str, tuple[str, bool, str]] = {}
        all_observed = False
        for branch_name, schema_cfg in branch_schemas.items():
            if schema_cfg.is_observed:
                all_observed = True
                break
            if schema_cfg.fields is None:
                continue
            for fd in schema_cfg.fields:
                if fd.name in seen_types:
                    prior_type, _prior_req, prior_branch = seen_types[fd.name]
                    if prior_type != fd.field_type:
                        raise GraphValidationError(f"Type mismatch for {fd.name}")
                    if not fd.required:
                        seen_types[fd.name] = (prior_type, False, prior_branch)
                else:
                    seen_types[fd.name] = (fd.field_type, fd.required, branch_name)

        if all_observed or not seen_types:
            return SchemaConfig(mode="observed", fields=None)
        merged_fields = tuple(FieldDefinition(name=name, field_type=ftype, required=req) for name, (ftype, req, _) in seen_types.items())
        return SchemaConfig(mode="flexible", fields=merged_fields)

    def _get_field(self, schema: SchemaConfig, name: str) -> FieldDefinition:
        """Get a FieldDefinition by name from a SchemaConfig."""
        assert schema.fields is not None
        for fd in schema.fields:
            if fd.name == name:
                return fd
        raise AssertionError(f"Field {name!r} not found in schema")

    def test_optional_field_preserved(self) -> None:
        """Optional field in one branch should remain optional in merged output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"), FieldDefinition("score", "float", required=False)),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"), FieldDefinition("label", "str")),
                ),
            }
        )
        assert self._get_field(result, "score").required is False
        assert self._get_field(result, "id").required is True
        assert self._get_field(result, "label").required is True

    def test_mixed_required_and_optional_yields_optional(self) -> None:
        """Field required in branch A, optional in branch B → optional in output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=True),),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=False),),
                ),
            }
        )
        assert self._get_field(result, "score").required is False

    def test_all_required_stays_required(self) -> None:
        """Field required in ALL branches → required in output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"),),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"),),
                ),
            }
        )
        assert self._get_field(result, "id").required is True

    def test_all_optional_stays_optional(self) -> None:
        """Field optional in ALL branches → optional in output."""
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=False),),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("score", "float", required=False),),
                ),
            }
        )
        assert self._get_field(result, "score").required is False


class TestCoalesceSinkRequiredFieldValidation:
    """Build-time validation of coalesce output vs downstream sink required fields.

    When a sink's declared_required_fields references a field that the upstream
    coalesce marks as optional (branch-exclusive or AND-downgraded), the
    configuration is broken and should fail at build time — not crash at runtime
    with a generic 'upstream schema bug' error.
    """

    def test_coalesce_to_sink_required_field_mismatch_raises(self) -> None:
        """Build-time validation catches coalesce output missing a sink's required field.

        Branch A guarantees field 'x'; branch B does not. Union merge marks 'x'
        as optional (branch-exclusive). A downstream sink declares 'x' required
        in its declared_required_fields. Validation must fail at build time.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph
        from elspeth.core.dag.models import NodeType

        branch_a_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=True),
            ),
        )
        branch_b_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
        )
        # Coalesce output: 'x' is optional because branch B doesn't guarantee it
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=False),
            ),
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node("gate", node_type=NodeType.GATE, plugin_name="fork")
        graph.add_node(
            "t_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="a",
            output_schema_config=branch_a_schema,
        )
        graph.add_node(
            "t_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="b",
            output_schema_config=branch_b_schema,
        )
        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce:merge",
            config={"branches": {"a": "a", "b": "b"}, "policy": "require_all", "merge": "union"},
            output_schema_config=coalesce_output_schema,
        )
        graph.add_node(
            "sink",
            node_type=NodeType.SINK,
            plugin_name="csv_sink",
            declared_required_fields=frozenset({"id", "x"}),
        )

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "t_a", label="a", mode=RoutingMode.COPY)
        graph.add_edge("gate", "t_b", label="b", mode=RoutingMode.COPY)
        graph.add_edge("t_a", "coalesce", label="a", mode=RoutingMode.MOVE)
        graph.add_edge("t_b", "coalesce", label="b", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "sink", label="continue", mode=RoutingMode.MOVE)

        with pytest.raises(
            GraphValidationError,
            match=r"required by sink.*but optional in coalesce output|Sink '.*' requires fields.*but optional in coalesce output",
        ):
            graph.validate_edge_compatibility()

    def test_coalesce_to_sink_validates_when_all_fields_guaranteed(self) -> None:
        """Build-time validation passes when coalesce guarantees all sink-required fields."""
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph
        from elspeth.core.dag.models import NodeType

        # Both branches guarantee 'x' → merged output guarantees 'x'
        branch_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=True),
            ),
        )
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=True),
            ),
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node("gate", node_type=NodeType.GATE, plugin_name="fork")
        graph.add_node(
            "t_a",
            node_type=NodeType.TRANSFORM,
            plugin_name="a",
            output_schema_config=branch_schema,
        )
        graph.add_node(
            "t_b",
            node_type=NodeType.TRANSFORM,
            plugin_name="b",
            output_schema_config=branch_schema,
        )
        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce:merge",
            config={"branches": {"a": "a", "b": "b"}, "policy": "require_all", "merge": "union"},
            output_schema_config=coalesce_output_schema,
        )
        graph.add_node(
            "sink",
            node_type=NodeType.SINK,
            plugin_name="csv_sink",
            declared_required_fields=frozenset({"id", "x"}),
        )

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "t_a", label="a", mode=RoutingMode.COPY)
        graph.add_edge("gate", "t_b", label="b", mode=RoutingMode.COPY)
        graph.add_edge("t_a", "coalesce", label="a", mode=RoutingMode.MOVE)
        graph.add_edge("t_b", "coalesce", label="b", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "sink", label="continue", mode=RoutingMode.MOVE)

        # Should not raise — all sink-required fields are guaranteed by coalesce output
        graph.validate_edge_compatibility()
