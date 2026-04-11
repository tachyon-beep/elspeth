# tests/unit/core/test_dag_coalesce_optionality.py
"""Tests for field optionality preservation in coalesce union merge schema.

Fix: builder.py union merge was stripping optionality markers from branch
field specs, making all merged fields appear required. Now uses SchemaConfig
and FieldDefinition directly — optionality is a first-class boolean field.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from elspeth.contracts import NodeType
from elspeth.contracts.schema import FieldDefinition, SchemaConfig
from elspeth.core.config import (
    CoalesceSettings,
    GateSettings,
    SourceSettings,
    TransformSettings,
)
from elspeth.core.dag import ExecutionGraph, WiredTransform
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
        branches_with_field: dict[str, set[str]] = {}
        contributing_branches: set[str] = set()
        all_observed = False
        for branch_name, schema_cfg in branch_schemas.items():
            if schema_cfg.is_observed:
                all_observed = True
                break
            if schema_cfg.fields is None:
                continue
            contributing_branches.add(branch_name)
            for fd in schema_cfg.fields:
                if fd.name not in branches_with_field:
                    branches_with_field[fd.name] = set()
                branches_with_field[fd.name].add(branch_name)
                if fd.name in seen_types:
                    prior_type, _prior_req, prior_branch = seen_types[fd.name]
                    if prior_type != fd.field_type:
                        raise GraphValidationError(f"Type mismatch for {fd.name}")
                    if not fd.required:
                        seen_types[fd.name] = (prior_type, False, prior_branch)
                else:
                    seen_types[fd.name] = (fd.field_type, fd.required, branch_name)

        # Apply AND semantics: fields not present in ALL contributing branches
        # become optional. Branches with fields=None abstain from the typed
        # contract and are excluded from the denominator.
        for field_name in list(seen_types):
            if branches_with_field[field_name] != contributing_branches:
                ftype, _, first_branch = seen_types[field_name]
                seen_types[field_name] = (ftype, False, first_branch)

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
        """Optional field in one branch or exclusive to one branch both remain optional in merged output."""
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
        assert self._get_field(result, "score").required is False  # explicit optional preserved
        assert self._get_field(result, "id").required is True  # present in all branches
        assert self._get_field(result, "label").required is False  # branch-exclusive → optional

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

        Branch transforms set guaranteed_fields explicitly to mirror what real
        plugin code (BaseTransform._build_output_schema_config) produces — the
        coalesce union path skips branches that don't declare guarantees.
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
            guaranteed_fields=("id", "x"),
        )
        branch_b_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
            guaranteed_fields=("id",),
        )
        # Coalesce output: 'x' is optional because branch B doesn't guarantee it.
        # The coalesce node's own output_schema_config is unused by the union
        # path of get_effective_guaranteed_fields — the intersection is computed
        # from the branches' guaranteed_fields directly. Set here for parity
        # with real builder behavior.
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=False),
            ),
            guaranteed_fields=("id",),
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
            match=r"upstream.*does not guarantee",
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
            guaranteed_fields=("id", "x"),
        )
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=True),
            ),
            guaranteed_fields=("id", "x"),
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

    def test_coalesce_to_sink_branch_exclusive_field_caught(self) -> None:
        """Build-time validation now catches the branch-exclusive case.

        After C2 fix: if branch A has a required field that branch B lacks,
        the merged schema marks it optional. A sink requiring that field will
        fail validation at build time.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph
        from elspeth.core.dag.models import NodeType

        branch_a_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("exclusive_to_a", "int", required=True),
            ),
            guaranteed_fields=("id", "exclusive_to_a"),
        )
        branch_b_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
            guaranteed_fields=("id",),
        )

        # Coalesce output: 'exclusive_to_a' is optional (branch-exclusive)
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("exclusive_to_a", "int", required=False),
            ),
            guaranteed_fields=("id",),
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
            declared_required_fields=frozenset({"id", "exclusive_to_a"}),
        )

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "t_a", label="a", mode=RoutingMode.COPY)
        graph.add_edge("gate", "t_b", label="b", mode=RoutingMode.COPY)
        graph.add_edge("t_a", "coalesce", label="a", mode=RoutingMode.MOVE)
        graph.add_edge("t_b", "coalesce", label="b", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "sink", label="continue", mode=RoutingMode.MOVE)

        with pytest.raises(GraphValidationError, match=r"exclusive_to_a"):
            graph.validate_edge_compatibility()

    def test_transform_between_coalesce_and_sink_still_validated(self) -> None:
        """COALESCE → TRANSFORM → SINK topology is still validated.

        If a transform sits between the coalesce and sink, the sink is
        validated against the TRANSFORM's output_schema_config (not the
        coalesce's). If the transform's output schema doesn't guarantee a
        field the sink requires, validation fails at build time.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.contracts.schema import FieldDefinition, SchemaConfig
        from elspeth.core.dag.graph import ExecutionGraph
        from elspeth.core.dag.models import GraphValidationError, NodeType

        # Coalesce produces 'id' (required) and 'x' (optional) via union merge
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=False),
            ),
        )

        # Transform passes through the coalesce output (keeps 'x' optional).
        # Set guaranteed_fields explicitly to mirror what BaseTransform's
        # _build_output_schema_config produces in production.
        transform_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=False),
            ),
            guaranteed_fields=("id",),
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node("gate", node_type=NodeType.GATE, plugin_name="fork")
        branch_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
        )
        graph.add_node("t_a", node_type=NodeType.TRANSFORM, plugin_name="a", output_schema_config=branch_schema)
        graph.add_node("t_b", node_type=NodeType.TRANSFORM, plugin_name="b", output_schema_config=branch_schema)
        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce:merge",
            config={"branches": {"a": "a", "b": "b"}, "policy": "require_all", "merge": "union"},
            output_schema_config=coalesce_output_schema,
        )
        graph.add_node(
            "post_transform",
            node_type=NodeType.TRANSFORM,
            plugin_name="enrich",
            output_schema_config=transform_output_schema,
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
        graph.add_edge("coalesce", "post_transform", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("post_transform", "sink", label="continue", mode=RoutingMode.MOVE)

        with pytest.raises(GraphValidationError, match=r"upstream 'post_transform'.*does not guarantee"):
            graph.validate_edge_compatibility()

    def test_transform_between_coalesce_and_sink_passes_when_transform_guarantees(self) -> None:
        """COALESCE → TRANSFORM → SINK passes when the transform guarantees required fields.

        Even if the coalesce marks 'x' optional, a transform that declares 'x'
        required in its output commits to producing it. The sink's requirement
        is satisfied by the transform's contract, not the coalesce's output.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.contracts.schema import FieldDefinition, SchemaConfig
        from elspeth.core.dag.graph import ExecutionGraph
        from elspeth.core.dag.models import NodeType

        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=False),  # optional from coalesce
            ),
        )
        # Transform commits to always producing x — declared via guaranteed_fields
        # mirroring real BaseTransform._build_output_schema_config output.
        transform_output_schema = SchemaConfig(
            mode="flexible",
            fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("x", "int", required=True),
            ),
            guaranteed_fields=("id", "x"),
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node("gate", node_type=NodeType.GATE, plugin_name="fork")
        branch_schema = SchemaConfig(mode="flexible", fields=(FieldDefinition("id", "str", required=True),))
        graph.add_node("t_a", node_type=NodeType.TRANSFORM, plugin_name="a", output_schema_config=branch_schema)
        graph.add_node("t_b", node_type=NodeType.TRANSFORM, plugin_name="b", output_schema_config=branch_schema)
        graph.add_node(
            "coalesce",
            node_type=NodeType.COALESCE,
            plugin_name="coalesce:merge",
            config={"branches": {"a": "a", "b": "b"}, "policy": "require_all", "merge": "union"},
            output_schema_config=coalesce_output_schema,
        )
        graph.add_node(
            "post_transform",
            node_type=NodeType.TRANSFORM,
            plugin_name="enrich",
            output_schema_config=transform_output_schema,
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
        graph.add_edge("coalesce", "post_transform", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("post_transform", "sink", label="continue", mode=RoutingMode.MOVE)

        graph.validate_edge_compatibility()  # Should not raise

    def test_aggregation_predecessor_skipped(self) -> None:
        """AGGREGATION → SINK skips required-field validation.

        Aggregations have dynamic output by design (e.g., BatchStats produces
        count/sum/mean rather than the input fields). The builder stores their
        `options.schema` as input-validation, not output, so validating sink
        requirements against it produces false positives. Validation must skip.

        Regression test for the case where the new sink-required-fields walk
        was firing on aggregation→sink topologies and rejecting valid configs.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.contracts.schema import FieldDefinition, SchemaConfig
        from elspeth.core.dag.graph import ExecutionGraph
        from elspeth.core.dag.models import NodeType

        # Aggregation's output_schema_config carries its INPUT schema (legacy
        # builder behavior). Without the AGGREGATION skip, the sink's required
        # field 'total_records' would appear missing from this schema.
        aggregation_input_schema = SchemaConfig(
            mode="fixed",
            fields=(FieldDefinition("value", "float", required=True),),
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node(
            "stats",
            node_type=NodeType.AGGREGATION,
            plugin_name="batch_stats",
            config={"options": {"value_field": "value"}},
            output_schema_config=aggregation_input_schema,
        )
        graph.add_node(
            "sink",
            node_type=NodeType.SINK,
            plugin_name="csv_sink",
            declared_required_fields=frozenset({"total_records"}),
        )

        graph.add_edge("source", "stats", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("stats", "sink", label="continue", mode=RoutingMode.MOVE)

        graph.validate_edge_compatibility()  # Should not raise


class _BuilderMockSource:
    """Mock source plugin for builder end-to-end tests."""

    name = "mock_source"
    output_schema = None
    config: ClassVar[dict[str, Any]] = {"schema": {"mode": "observed"}}
    _on_validation_failure = "discard"
    on_success = "output"


class _BuilderMockSink:
    """Mock sink plugin with no declared required fields."""

    name = "mock_sink"
    input_schema = None
    config: ClassVar[dict[str, Any]] = {}
    _on_write_failure: str = "discard"
    declared_required_fields: ClassVar[frozenset[str]] = frozenset()

    def _reset_diversion_log(self) -> None:
        pass


class _TransformWithTypedSchema:
    """Mock transform that exposes a typed _output_schema_config with fields."""

    input_schema = None
    output_schema = None
    config: ClassVar[dict[str, Any]] = {"schema": {"mode": "flexible"}}
    on_error: str | None = None
    on_success: str | None = "output"
    declared_output_fields: frozenset[str] = frozenset()

    def __init__(self, name: str, schema: SchemaConfig) -> None:
        self.name = name
        self._output_schema_config = schema


class TestBuilderBranchExclusiveFieldDowngrade:
    """End-to-end coverage for the builder's union-merge downgrade pass.

    The tests above this class (_merge_schemas and the manually-built graph
    with a pre-computed coalesce schema) all bypass the real builder. If the
    downgrade pass in ``src/elspeth/core/dag/builder.py`` were deleted, those
    tests would still pass.

    These tests drive ``ExecutionGraph.from_plugin_instances`` with asymmetric
    branch schemas and inspect the resulting coalesce node's
    ``output_schema_config`` directly, so a regression in the builder's
    downgrade pass will fail here loudly.
    """

    def _build_graph(
        self,
        *,
        branch_a_fields: tuple[FieldDefinition, ...],
        branch_b_fields: tuple[FieldDefinition, ...],
    ) -> ExecutionGraph:
        """Build: source → fork gate → [transform_a, transform_b] → coalesce → sink."""
        source = _BuilderMockSource()

        t_a = _TransformWithTypedSchema(
            "branch_transform_a",
            SchemaConfig(mode="flexible", fields=branch_a_fields),
        )
        t_b = _TransformWithTypedSchema(
            "branch_transform_b",
            SchemaConfig(mode="flexible", fields=branch_b_fields),
        )

        wired_a = WiredTransform(
            plugin=t_a,  # type: ignore[arg-type]
            settings=TransformSettings(
                name="t_a",
                plugin=t_a.name,
                input="branch_a",
                on_success="t_a_out",
                on_error="discard",
                options={},
            ),
        )
        wired_b = WiredTransform(
            plugin=t_b,  # type: ignore[arg-type]
            settings=TransformSettings(
                name="t_b",
                plugin=t_b.name,
                input="branch_b",
                on_success="t_b_out",
                on_error="discard",
                options={},
            ),
        )

        fork_gate = GateSettings(
            name="splitter",
            input="source_out",
            condition="True",
            routes={"true": "fork", "false": "output"},
            fork_to=["branch_a", "branch_b"],
        )

        coalesce = CoalesceSettings(
            name="merger",
            branches={"branch_a": "t_a_out", "branch_b": "t_b_out"},
            policy="require_all",
            merge="union",
            on_success="output",
        )

        return ExecutionGraph.from_plugin_instances(
            source=source,  # type: ignore[arg-type]
            source_settings=SourceSettings(plugin=source.name, on_success="source_out", options={}),
            transforms=[wired_a, wired_b],
            sinks={"output": _BuilderMockSink()},  # type: ignore[dict-item]
            aggregations={},
            gates=[fork_gate],
            coalesce_settings=[coalesce],
        )

    def _get_field(self, schema: SchemaConfig, name: str) -> FieldDefinition:
        assert schema.fields is not None
        for fd in schema.fields:
            if fd.name == name:
                return fd
        raise AssertionError(f"Field {name!r} not found in schema")

    def test_builder_downgrades_branch_exclusive_field_to_optional(self) -> None:
        """End-to-end: builder's union merge marks branch-exclusive fields as optional.

        Drives the real build_execution_graph with asymmetric branch schemas
        to prove the downgrade pass actually runs and produces the right result.
        Without this test, the bug-fix code could be deleted and all other
        tests would still pass (they use a simulation copy of the algorithm).
        """
        graph = self._build_graph(
            branch_a_fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("exclusive_to_a", "int", required=True),
            ),
            branch_b_fields=(FieldDefinition("id", "str", required=True),),
        )

        coalesce_nodes = [n for n in graph.get_nodes() if n.node_type == NodeType.COALESCE]
        assert len(coalesce_nodes) == 1
        coal_schema = coalesce_nodes[0].output_schema_config
        assert coal_schema is not None
        assert coal_schema.fields is not None, "Expected typed schema, not observed"

        # Branch-exclusive field must be downgraded to optional.
        assert self._get_field(coal_schema, "exclusive_to_a").required is False
        # Field present in ALL branches must stay required — downgrade is selective.
        assert self._get_field(coal_schema, "id").required is True

    def test_builder_keeps_shared_required_fields_required(self) -> None:
        """Control case: field required in BOTH branches stays required.

        Complements the branch-exclusive test — proves the downgrade is
        keyed on branch-presence, not applied blanket to every field.
        """
        graph = self._build_graph(
            branch_a_fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("shared", "int", required=True),
            ),
            branch_b_fields=(
                FieldDefinition("id", "str", required=True),
                FieldDefinition("shared", "int", required=True),
            ),
        )

        coalesce_nodes = [n for n in graph.get_nodes() if n.node_type == NodeType.COALESCE]
        assert len(coalesce_nodes) == 1
        coal_schema = coalesce_nodes[0].output_schema_config
        assert coal_schema is not None
        assert coal_schema.fields is not None

        assert self._get_field(coal_schema, "id").required is True
        assert self._get_field(coal_schema, "shared").required is True

    def test_builder_end_to_end_sink_required_fields_branch_exclusive_rejected(self) -> None:
        """End-to-end: builder + sink validation catch branch-exclusive sink requirement.

        This is the integration test that exercises BOTH C1 (sink validation
        walks predecessors) AND C2 (builder marks branch-exclusive fields
        optional) together. Without this test, either fix could be regressed
        independently and the other tests would still pass.

        Setup: branch A produces 'exclusive_to_a' as required, branch B does
        not. Sink declares 'exclusive_to_a' in declared_required_fields. The
        builder runs the union merge and marks 'exclusive_to_a' as optional
        in the coalesce output. The sink validator then walks predecessors,
        sees the field is not guaranteed by the coalesce, and raises.
        """

        class _SinkRequiringExclusive:
            name = "strict_sink"
            input_schema = None
            config: ClassVar[dict[str, Any]] = {}
            _on_write_failure: str = "discard"
            declared_required_fields: ClassVar[frozenset[str]] = frozenset({"id", "exclusive_to_a"})

            def _reset_diversion_log(self) -> None:
                pass

        source = _BuilderMockSource()
        t_a = _TransformWithTypedSchema(
            "branch_transform_a",
            SchemaConfig(
                mode="flexible",
                fields=(
                    FieldDefinition("id", "str", required=True),
                    FieldDefinition("exclusive_to_a", "int", required=True),
                ),
                guaranteed_fields=("id", "exclusive_to_a"),
            ),
        )
        t_b = _TransformWithTypedSchema(
            "branch_transform_b",
            SchemaConfig(
                mode="flexible",
                fields=(FieldDefinition("id", "str", required=True),),
                guaranteed_fields=("id",),
            ),
        )

        wired_a = WiredTransform(
            plugin=t_a,  # type: ignore[arg-type]
            settings=TransformSettings(
                name="t_a",
                plugin=t_a.name,
                input="branch_a",
                on_success="t_a_out",
                on_error="discard",
                options={},
            ),
        )
        wired_b = WiredTransform(
            plugin=t_b,  # type: ignore[arg-type]
            settings=TransformSettings(
                name="t_b",
                plugin=t_b.name,
                input="branch_b",
                on_success="t_b_out",
                on_error="discard",
                options={},
            ),
        )

        fork_gate = GateSettings(
            name="splitter",
            input="source_out",
            condition="True",
            routes={"true": "fork", "false": "output"},
            fork_to=["branch_a", "branch_b"],
        )

        coalesce = CoalesceSettings(
            name="merger",
            branches={"branch_a": "t_a_out", "branch_b": "t_b_out"},
            policy="require_all",
            merge="union",
            on_success="output",
        )

        with pytest.raises(GraphValidationError, match=r"exclusive_to_a"):
            ExecutionGraph.from_plugin_instances(
                source=source,  # type: ignore[arg-type]
                source_settings=SourceSettings(plugin=source.name, on_success="source_out", options={}),
                transforms=[wired_a, wired_b],
                sinks={"output": _SinkRequiringExclusive()},  # type: ignore[dict-item]
                aggregations={},
                gates=[fork_gate],
                coalesce_settings=[coalesce],
            )
