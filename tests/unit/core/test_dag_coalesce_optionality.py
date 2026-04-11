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
        *,
        policy: str = "best_effort",
    ) -> SchemaConfig:
        """Simulate the builder's union merge logic with SchemaConfig objects.

        Mirrors the policy-aware logic in src/elspeth/core/dag/builder.py:
        - require_all: OR semantics (a field is required if ANY branch
          requires it; branch-exclusive fields keep their source flag)
        - all others (best_effort/quorum/first): AND semantics (a field is
          required only if every contributing branch requires it; branch-
          exclusive fields are forced optional)

        The default `policy="best_effort"` exercises the AND path because
        the historical tests in this class were written assuming AND.
        Tests for the OR path explicitly pass `policy="require_all"`.
        """
        require_all = policy == "require_all"
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
                    prior_type, prior_req, prior_branch = seen_types[fd.name]
                    if prior_type != fd.field_type:
                        raise GraphValidationError(f"Type mismatch for {fd.name}")
                    if require_all:
                        # OR: required if required in ANY branch.
                        if fd.required and not prior_req:
                            seen_types[fd.name] = (prior_type, True, prior_branch)
                    else:
                        # AND: optional if optional in ANY branch.
                        if not fd.required:
                            seen_types[fd.name] = (prior_type, False, prior_branch)
                else:
                    seen_types[fd.name] = (fd.field_type, fd.required, branch_name)

        # Branch-exclusive fields: under require_all the source-branch flag
        # is preserved (the source branch always arrives and produces it).
        # Under other policies, force optional (the source may not arrive).
        if not require_all:
            for field_name in list(seen_types):
                if branches_with_field[field_name] != contributing_branches:
                    ftype, _, first_branch = seen_types[field_name]
                    seen_types[field_name] = (ftype, False, first_branch)

        if all_observed or not seen_types:
            return SchemaConfig(mode="observed", fields=None)
        merged_fields = tuple(
            FieldDefinition(name=name, field_type=ftype, required=req)  # type: ignore[arg-type]  # ftype is Literal at runtime (from FieldDefinition.field_type), narrowed to str by tuple storage
            for name, (ftype, req, _) in seen_types.items()
        )
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

    # ── require_all OR-semantics tests ───────────────────────────────────────

    def test_require_all_keeps_branch_exclusive_required_field_required(self) -> None:
        """Under require_all, a branch-exclusive REQUIRED field stays required.

        Branch A always arrives and always produces 'label'. After merge,
        'label' is in every merged row. The merged spec must reflect this.

        Regression for the unconditional AND-downgrade bug that produced
        false positives in build-time validation for valid require_all DAGs.
        """
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"), FieldDefinition("label", "str", required=True)),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"),),
                ),
            },
            policy="require_all",
        )
        # 'label' is exclusive to branch A but always present (require_all).
        assert self._get_field(result, "label").required is True
        assert self._get_field(result, "id").required is True

    def test_require_all_keeps_branch_exclusive_optional_field_optional(self) -> None:
        """Under require_all, a branch-exclusive OPTIONAL field stays optional.

        Branch A always arrives, but its 'score' field is optional —
        branch A's row may not have it. The merged row may not have it
        either. The merged spec correctly reflects this as optional.
        """
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"), FieldDefinition("score", "float", required=False)),
                ),
                "branch_b": SchemaConfig(
                    mode="flexible",
                    fields=(FieldDefinition("id", "int"),),
                ),
            },
            policy="require_all",
        )
        # 'score' is optional in branch A → optional in merged.
        assert self._get_field(result, "score").required is False
        assert self._get_field(result, "id").required is True

    def test_require_all_shared_field_required_in_one_branch_becomes_required(self) -> None:
        """Under require_all, a shared field required in one branch is required in merged.

        Branch A requires 'score', branch B has it optional. Branch A always
        produces 'score'. After dict.update, 'score' is in every merged row
        (either A's value or B's overwrite if B has it). The merged spec
        is required=True under require_all.

        This is the OR semantic for shared fields. Under AND (the wrong
        semantic for require_all), this would incorrectly become optional.
        """
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
            },
            policy="require_all",
        )
        assert self._get_field(result, "score").required is True

    def test_abstaining_branch_does_not_downgrade_others(self) -> None:
        """A non-observed branch with fields=None must not downgrade other branches' fields.

        Regression test for a latent bomb in the builder's union merge. Before
        the fix, a branch with ``fields=None`` would silently mark every OTHER
        branch's required fields as optional: the post-loop pass applied AND
        semantics by comparing each field's branch-presence set against the
        FULL set of branches in the coalesce, not just the branches that
        actually contributed a typed contract.

        With a ``fields=None`` branch in the mix, no field could ever be
        present in ALL branches, so every required field got silently
        downgraded to optional — a catastrophic false negative.

        The fix introduced ``contributing_branches`` to exclude abstaining
        branches from the denominator. This test locks that behaviour in:
        two branches both require ``id`` and ``score``, a third branch
        abstains with ``fields=None``. Both fields must remain required.

        If the ``contributing_branches`` guard is removed, this test fails
        because ``branch_b`` is missing from ``branches_with_field[id]``
        and ``branches_with_field[score]``, so both get downgraded to
        ``required=False``.
        """
        result = self._merge_schemas(
            {
                "branch_a": SchemaConfig(
                    mode="flexible",
                    fields=(
                        FieldDefinition("id", "str", required=True),
                        FieldDefinition("score", "float", required=True),
                    ),
                ),
                "branch_b": SchemaConfig(mode="flexible", fields=None),
                "branch_c": SchemaConfig(
                    mode="flexible",
                    fields=(
                        FieldDefinition("id", "str", required=True),
                        FieldDefinition("score", "float", required=True),
                    ),
                ),
            }
        )
        assert self._get_field(result, "id").required is True
        assert self._get_field(result, "score").required is True


class TestCoalesceSinkRequiredFieldValidation:
    """Build-time validation of coalesce output vs downstream sink required fields.

    When a sink's declared_required_fields references a field that the upstream
    coalesce marks as optional (branch-exclusive or AND-downgraded), the
    configuration is broken and should fail at build time — not crash at runtime
    with a generic 'upstream schema bug' error.
    """

    def test_coalesce_to_sink_required_field_mismatch_raises(self) -> None:
        """Build-time validation catches coalesce output missing a sink's required field.

        Branch A guarantees field 'x'; branch B does not. Under best_effort
        policy, branch A might not arrive (lost), so the merged row may be
        missing 'x'. A downstream sink declares 'x' required in its
        declared_required_fields. Validation must fail at build time.

        Note: this test uses best_effort policy because under require_all,
        branch A always arrives and the field IS guaranteed in the merged
        row — see test_builder_end_to_end_require_all_accepts_branch_exclusive_sink_requirement
        for the require_all variant.

        Branch transforms set guaranteed_fields explicitly to mirror what real
        plugin code (BaseTransform._build_output_schema_config) produces — the
        coalesce union path skips branches that don't declare guarantees.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph

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
        # Coalesce output under best_effort: 'x' is optional because branch A
        # may not arrive. The coalesce node's own output_schema_config is unused
        # by the union path of get_effective_guaranteed_fields — the
        # intersection is computed from the branches' guaranteed_fields directly.
        # Set here for parity with real builder behavior.
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
            config={"branches": {"a": "a", "b": "b"}, "policy": "best_effort", "merge": "union"},
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
        """Build-time validation catches the branch-exclusive case under best_effort.

        Branch A has a required field that branch B lacks. Under best_effort,
        branch A may be lost — the merged schema marks 'exclusive_to_a' as
        optional. A sink requiring that field fails validation at build time.

        Note: this test uses best_effort policy because under require_all,
        branch A always arrives and the field IS guaranteed in the merged
        row — see test_builder_end_to_end_require_all_accepts_branch_exclusive_sink_requirement
        for the require_all variant where validation correctly accepts.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph

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

        # Coalesce output under best_effort: 'exclusive_to_a' is optional
        # (branch-exclusive AND the source branch may not arrive).
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
            config={"branches": {"a": "a", "b": "b"}, "policy": "best_effort", "merge": "union"},
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
        from elspeth.core.dag.models import GraphValidationError

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

    def test_shape_changing_transform_between_coalesce_and_sink_uses_guaranteed_fields(
        self,
    ) -> None:
        """Sink validator must consult get_effective_guaranteed_fields, not fields tuple.

        Regression test for the original critical bug. ``_validate_sink_required_fields``
        was originally written to read ``output_schema_config.fields`` directly.
        The base ``BaseTransform._build_output_schema_config()`` (see
        ``src/elspeth/plugins/infrastructure/base.py``) copies INPUT ``fields``
        into the output config, recomputing only ``guaranteed_fields``. For a
        shape-changing transform (e.g., FieldMapper renaming ``id`` →
        ``customer_id``), the output schema's ``fields`` tuple still contains
        the pre-rename input names.

        This test mirrors FieldMapper's ``_build_field_mapper_output_schema_config``
        pattern: ``fields`` holds the input ``id`` (required=True) and
        ``guaranteed_fields`` holds the post-rename ``customer_id``. The sink
        requires only ``customer_id``.

        If the validator is reverted to reading ``output_schema_config.fields``
        directly, it would see ``id`` but not ``customer_id`` and falsely
        reject this valid topology. Under the current implementation it calls
        ``get_effective_guaranteed_fields()``, which OR's in explicit
        ``guaranteed_fields`` and sees ``customer_id`` → passes.

        Topology: source → fork → [t_a, t_b] → coalesce(union) → field_mapper → sink.
        Both branches guarantee ``id``; the field_mapper renames ``id`` to
        ``customer_id``; the sink requires ``customer_id``.
        """
        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph

        branch_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
            guaranteed_fields=("id",),
        )
        coalesce_output_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
            guaranteed_fields=("id",),
        )
        # Shape-changing transform schema mirroring FieldMapper's pattern:
        # fields holds INPUT names (pre-rename), guaranteed_fields holds
        # OUTPUT names (post-rename). A validator that reads fields directly
        # would see "id" and falsely reject; one that uses
        # get_effective_guaranteed_fields() sees "customer_id" via
        # guaranteed_fields and correctly accepts.
        field_mapper_output_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
            guaranteed_fields=("customer_id",),
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
            "field_mapper",
            node_type=NodeType.TRANSFORM,
            plugin_name="field_mapper",
            output_schema_config=field_mapper_output_schema,
        )
        graph.add_node(
            "sink",
            node_type=NodeType.SINK,
            plugin_name="csv_sink",
            declared_required_fields=frozenset({"customer_id"}),
        )

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "t_a", label="a", mode=RoutingMode.COPY)
        graph.add_edge("gate", "t_b", label="b", mode=RoutingMode.COPY)
        graph.add_edge("t_a", "coalesce", label="a", mode=RoutingMode.MOVE)
        graph.add_edge("t_b", "coalesce", label="b", mode=RoutingMode.MOVE)
        graph.add_edge("coalesce", "field_mapper", label="continue", mode=RoutingMode.MOVE)
        graph.add_edge("field_mapper", "sink", label="continue", mode=RoutingMode.MOVE)

        # Call the sink-required-fields validator directly. We skip the full
        # validate_edge_compatibility() walk because the mocked schemas are
        # not meant to exercise the cross-plugin compatibility path — this
        # test is narrowly scoped to the sink predecessor walk.
        graph._validate_sink_required_fields()  # Should not raise

    def test_multi_edge_sink_predecessor_deduped(self) -> None:
        """Sink validator must visit each unique predecessor once, even with parallel edges.

        Regression test for the multi-edge case. The original implementation
        used ``self._graph.in_edges(node_id)`` which yields one tuple per
        parallel edge in a ``MultiDiGraph``. A gate routing two labels (e.g.,
        ``true`` and ``false``) to the same sink would therefore cause the
        validator to run twice for that predecessor.

        The fix switched to ``self._graph.predecessors(node_id)`` which
        yields each unique predecessor node exactly once regardless of the
        number of parallel edges between them.

        This test builds a graph with a single gate routing to one sink via
        two different labels ("true" and "false"). It then patches
        ``get_effective_guaranteed_fields`` with a call counter and asserts
        it is invoked exactly once for the gate predecessor. If the
        implementation regresses to ``.in_edges()``, the counter reads 2
        and the assertion fails.
        """
        from unittest.mock import patch

        from elspeth.contracts import RoutingMode
        from elspeth.core.dag.graph import ExecutionGraph

        gate_output_schema = SchemaConfig(
            mode="flexible",
            fields=(FieldDefinition("id", "str", required=True),),
            guaranteed_fields=("id",),
        )

        graph = ExecutionGraph()
        graph.add_node("source", node_type=NodeType.SOURCE, plugin_name="csv")
        graph.add_node(
            "gate",
            node_type=NodeType.GATE,
            plugin_name="fork",
            output_schema_config=gate_output_schema,
        )
        graph.add_node(
            "sink",
            node_type=NodeType.SINK,
            plugin_name="csv_sink",
            declared_required_fields=frozenset({"id"}),
        )

        graph.add_edge("source", "gate", label="continue", mode=RoutingMode.MOVE)
        # Two parallel edges from gate to sink — different labels, same source/target.
        graph.add_edge("gate", "sink", label="true", mode=RoutingMode.MOVE)
        graph.add_edge("gate", "sink", label="false", mode=RoutingMode.MOVE)

        # Patch the effective-guarantees API with a counter. The validator
        # must call it exactly ONCE for the gate predecessor, regardless of
        # how many parallel edges exist between gate and sink.
        call_counts: dict[str, int] = {}
        original = graph.get_effective_guaranteed_fields

        def counting_wrapper(node_id: str) -> frozenset[str]:
            call_counts[node_id] = call_counts.get(node_id, 0) + 1
            return original(node_id)

        with patch.object(graph, "get_effective_guaranteed_fields", side_effect=counting_wrapper):
            graph._validate_sink_required_fields()  # Should not raise

        assert call_counts.get("gate", 0) == 1, (
            f"Expected gate predecessor to be visited exactly once, "
            f"but was visited {call_counts.get('gate', 0)} times. "
            f"This indicates the validator is iterating in_edges (which yields "
            f"one tuple per parallel edge) instead of predecessors (which "
            f"yields each unique source node once)."
        )


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

    def test_builder_preserves_branch_exclusive_required_field_under_require_all(self) -> None:
        """End-to-end: builder's union merge KEEPS branch-exclusive fields required under require_all.

        Under require_all coalesce policy, every branch always arrives before
        the merge fires (CoalesceExecutor._should_merge enforces this). Then
        _merge_data unions every arrived branch's keys via dict.update, so a
        field produced by branch A is always in the merged row regardless of
        whether branch B has it.

        Therefore: a field required in branch A is GUARANTEED in the merged
        output under require_all, even if branch B doesn't declare it. The
        builder must reflect this by KEEPING the field required.

        Regresses a previous over-conservative AND-semantics fix that
        unconditionally downgraded branch-exclusive fields to optional,
        producing false positives in build-time validation for valid
        require_all DAGs that fed sinks requiring such fields.
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

        # Branch-exclusive REQUIRED field stays required under require_all:
        # branch A always arrives and always produces it.
        assert self._get_field(coal_schema, "exclusive_to_a").required is True
        # Field present in ALL branches stays required (trivially).
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

    def _build_end_to_end_branch_exclusive_setup(self, *, policy: str) -> tuple[Any, Any, Any, Any, Any, Any]:
        """Build the source/transforms/gate/coalesce for an asymmetric-branch sink test.

        Returns (source, wired_a, wired_b, fork_gate, coalesce, sink_class).
        Branch A guarantees 'id' and 'exclusive_to_a'; branch B only guarantees 'id'.
        Sink declares both as required. The coalesce policy is parameterized.
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

        # best_effort requires a timeout; require_all does not. Pass timeout
        # unconditionally — it's harmless for require_all (the policy ignores it).
        coalesce = CoalesceSettings(
            name="merger",
            branches={"branch_a": "t_a_out", "branch_b": "t_b_out"},
            policy=policy,  # type: ignore[arg-type]
            merge="union",
            on_success="output",
            timeout_seconds=60.0,
        )

        return source, wired_a, wired_b, fork_gate, coalesce, _SinkRequiringExclusive

    def test_builder_end_to_end_require_all_accepts_branch_exclusive_sink_requirement(self) -> None:
        """End-to-end: under require_all, the sink can require a branch-exclusive field.

        Branch A produces 'exclusive_to_a' as required, branch B does not.
        Sink declares 'exclusive_to_a' in declared_required_fields. Under
        require_all, every branch always arrives, so branch A's field IS in
        every merged row — the sink requirement is correctly satisfied.

        Build-time validation must NOT reject this configuration. This test
        regresses a previous over-conservative AND-semantics fix that
        unconditionally downgraded branch-exclusive fields to optional, causing
        validate_edge_compatibility() to raise on valid require_all DAGs.
        """
        source, wired_a, wired_b, fork_gate, coalesce, sink_class = self._build_end_to_end_branch_exclusive_setup(policy="require_all")

        # Build must succeed — under require_all, the sink requirement is
        # actually satisfied because branch A always arrives with the field.
        graph = ExecutionGraph.from_plugin_instances(
            source=source,  # type: ignore[arg-type]
            source_settings=SourceSettings(plugin=source.name, on_success="source_out", options={}),
            transforms=[wired_a, wired_b],
            sinks={"output": sink_class()},  # type: ignore[dict-item]
            aggregations={},
            gates=[fork_gate],
            coalesce_settings=[coalesce],
        )

        # Sanity check: the coalesce node's effective guarantees include
        # exclusive_to_a (via OR over branches under require_all).
        coalesce_nodes = [n for n in graph.get_nodes() if n.node_type == NodeType.COALESCE]
        assert len(coalesce_nodes) == 1
        guaranteed = graph.get_effective_guaranteed_fields(coalesce_nodes[0].node_id)
        assert "exclusive_to_a" in guaranteed
        assert "id" in guaranteed

    def test_builder_end_to_end_best_effort_rejects_branch_exclusive_sink_requirement(self) -> None:
        """End-to-end: under best_effort, a sink requiring a branch-exclusive field is rejected.

        Same setup as the require_all test, but with best_effort policy: the
        branch that produces 'exclusive_to_a' may NOT arrive, so the merged
        row may be missing the field. The sink's requirement cannot be
        statically satisfied — build-time validation must reject this.

        This is the AND-semantics case the previous over-conservative fix
        was trying to catch (correctly, for non-require_all policies).
        """
        source, wired_a, wired_b, fork_gate, coalesce, sink_class = self._build_end_to_end_branch_exclusive_setup(policy="best_effort")

        with pytest.raises(GraphValidationError, match=r"exclusive_to_a"):
            ExecutionGraph.from_plugin_instances(
                source=source,  # type: ignore[arg-type]
                source_settings=SourceSettings(plugin=source.name, on_success="source_out", options={}),
                transforms=[wired_a, wired_b],
                sinks={"output": sink_class()},  # type: ignore[dict-item]
                aggregations={},
                gates=[fork_gate],
                coalesce_settings=[coalesce],
            )
