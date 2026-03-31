"""Tests for CompositionState and supporting data models."""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.web.composer.state import (
    CompositionState,
    EdgeSpec,
    EdgeType,
    NodeSpec,
    OutputSpec,
    PipelineMetadata,
    SourceSpec,
    ValidationSummary,
)


class TestSourceSpec:
    def test_create(self) -> None:
        s = SourceSpec(
            plugin="csv",
            on_success="transform_1",
            options={"path": "/data/input.csv"},
            on_validation_failure="quarantine",
        )
        assert s.plugin == "csv"
        assert s.on_success == "transform_1"
        assert s.options["path"] == "/data/input.csv"

    def test_frozen(self) -> None:
        s = SourceSpec(plugin="csv", on_success="t1", options={}, on_validation_failure="discard")
        with pytest.raises(AttributeError):
            s.plugin = "json"  # type: ignore[misc]

    def test_options_deep_frozen(self) -> None:
        s = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"key": "val"}},
            on_validation_failure="discard",
        )
        with pytest.raises(TypeError):
            s.options["new"] = "x"  # type: ignore[index]

    def test_options_nested_frozen(self) -> None:
        s = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"key": "val"}},
            on_validation_failure="discard",
        )
        with pytest.raises(TypeError):
            s.options["nested"]["mutate"] = "x"

    def test_from_dict_round_trip(self) -> None:
        s = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"key": "val"}},
            on_validation_failure="quarantine",
        )
        restored = SourceSpec.from_dict(
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"nested": {"key": "val"}},
                "on_validation_failure": "quarantine",
            }
        )
        assert restored == s


class TestNodeSpec:
    def _make_transform(self, **overrides: Any) -> NodeSpec:
        defaults: dict[str, Any] = {
            "id": "transform_1",
            "node_type": "transform",
            "plugin": "uppercase",
            "input": "source_out",
            "on_success": "sink_main",
            "on_error": None,
            "options": {"field": "name"},
            "condition": None,
            "routes": None,
            "fork_to": None,
            "branches": None,
            "policy": None,
            "merge": None,
        }
        defaults.update(overrides)
        return NodeSpec(**defaults)

    def _make_gate(self, **overrides: Any) -> NodeSpec:
        defaults: dict[str, Any] = {
            "id": "gate_1",
            "node_type": "gate",
            "plugin": None,
            "input": "source_out",
            "on_success": None,
            "on_error": None,
            "options": {},
            "condition": "row['score'] >= 0.5",
            "routes": {"high": "sink_good", "low": "sink_bad"},
            "fork_to": None,
            "branches": None,
            "policy": None,
            "merge": None,
        }
        defaults.update(overrides)
        return NodeSpec(**defaults)

    def test_create_transform(self) -> None:
        n = self._make_transform()
        assert n.id == "transform_1"
        assert n.node_type == "transform"
        assert n.plugin == "uppercase"

    def test_create_gate(self) -> None:
        n = self._make_gate()
        assert n.condition == "row['score'] >= 0.5"
        assert n.routes is not None
        assert n.routes["high"] == "sink_good"

    def test_frozen(self) -> None:
        n = self._make_transform()
        with pytest.raises(AttributeError):
            n.id = "new_id"  # type: ignore[misc]

    def test_options_deep_frozen(self) -> None:
        n = self._make_transform(options={"nested": {"k": "v"}})
        with pytest.raises(TypeError):
            n.options["new"] = 1  # type: ignore[index]

    def test_routes_deep_frozen(self) -> None:
        n = self._make_gate()
        with pytest.raises(TypeError):
            n.routes["extra"] = "val"  # type: ignore[index]

    def test_fork_to_is_tuple(self) -> None:
        n = self._make_gate(fork_to=("path_a", "path_b"))
        assert isinstance(n.fork_to, tuple)
        assert n.fork_to == ("path_a", "path_b")

    def test_branches_is_tuple(self) -> None:
        n = NodeSpec(
            id="coal_1",
            node_type="coalesce",
            plugin=None,
            input="join_point",
            on_success="sink_main",
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=("path_a", "path_b"),
            policy="require_all",
            merge="nested",
        )
        assert isinstance(n.branches, tuple)

    def test_from_dict_with_optional_fields(self) -> None:
        """from_dict reconstructs optional fields; missing ones default to None."""
        d = {
            "id": "g1",
            "node_type": "gate",
            "plugin": None,
            "input": "in",
            "on_success": None,
            "on_error": None,
            "options": {},
            "condition": "row['x'] > 1",
            "routes": {"high": "s1"},
            "fork_to": ["path_a", "path_b"],
        }
        n = NodeSpec.from_dict(d)
        assert n.condition == "row['x'] > 1"
        assert n.fork_to == ("path_a", "path_b")
        assert n.branches is None
        assert n.policy is None
        assert n.merge is None

    def test_from_dict_converts_list_to_tuple(self) -> None:
        """to_dict() serialises tuples as lists; from_dict() must convert back."""
        d: dict[str, object] = {
            "id": "c1",
            "node_type": "coalesce",
            "plugin": None,
            "input": "join",
            "on_success": "out",
            "on_error": None,
            "options": {},
            "branches": ["a", "b"],
            "policy": "require_all",
            "merge": "nested",
        }
        n = NodeSpec.from_dict(d)
        assert isinstance(n.branches, tuple)
        assert n.branches == ("a", "b")


class TestEdgeSpec:
    def test_create(self) -> None:
        e = EdgeSpec(
            id="e1",
            from_node="source",
            to_node="transform_1",
            edge_type="on_success",
            label=None,
        )
        assert e.from_node == "source"
        assert e.to_node == "transform_1"

    def test_frozen(self) -> None:
        e = EdgeSpec(
            id="e1",
            from_node="source",
            to_node="t1",
            edge_type="on_success",
            label=None,
        )
        with pytest.raises(AttributeError):
            e.id = "e2"  # type: ignore[misc]

    def test_from_dict_round_trip(self) -> None:
        e = EdgeSpec(
            id="e1",
            from_node="source",
            to_node="t1",
            edge_type="on_success",
            label="main",
        )
        restored = EdgeSpec.from_dict(
            {
                "id": "e1",
                "from_node": "source",
                "to_node": "t1",
                "edge_type": "on_success",
                "label": "main",
            }
        )
        assert restored == e


class TestOutputSpec:
    def test_create(self) -> None:
        o = OutputSpec(
            name="main_output",
            plugin="csv",
            options={"path": "/out.csv"},
            on_write_failure="quarantine",
        )
        assert o.name == "main_output"
        assert o.plugin == "csv"

    def test_frozen(self) -> None:
        o = OutputSpec(name="out", plugin="csv", options={}, on_write_failure="discard")
        with pytest.raises(AttributeError):
            o.name = "new"  # type: ignore[misc]

    def test_options_deep_frozen(self) -> None:
        o = OutputSpec(
            name="out",
            plugin="csv",
            options={"nested": {"k": 1}},
            on_write_failure="discard",
        )
        with pytest.raises(TypeError):
            o.options["new"] = 2  # type: ignore[index]

    def test_from_dict_round_trip(self) -> None:
        o = OutputSpec(
            name="out",
            plugin="csv",
            options={"path": "/out.csv"},
            on_write_failure="quarantine",
        )
        restored = OutputSpec.from_dict(
            {
                "name": "out",
                "plugin": "csv",
                "options": {"path": "/out.csv"},
                "on_write_failure": "quarantine",
            }
        )
        assert restored == o


class TestPipelineMetadata:
    def test_defaults(self) -> None:
        m = PipelineMetadata()
        assert m.name == "Untitled Pipeline"
        assert m.description == ""

    def test_custom(self) -> None:
        m = PipelineMetadata(
            name="My Pipeline",
            description="Does things",
        )
        assert m.name == "My Pipeline"

    def test_frozen(self) -> None:
        m = PipelineMetadata()
        with pytest.raises(AttributeError):
            m.name = "new"  # type: ignore[misc]

    def test_from_dict_round_trip(self) -> None:
        m = PipelineMetadata(name="My Pipeline", description="Desc")
        restored = PipelineMetadata.from_dict(
            {
                "name": "My Pipeline",
                "description": "Desc",
            }
        )
        assert restored == m

    def test_from_dict_crashes_on_missing_fields(self) -> None:
        """Missing fields crash — this is Tier 1 data from to_dict()."""
        with pytest.raises(KeyError):
            PipelineMetadata.from_dict({})


class TestValidationSummary:
    def test_valid(self) -> None:
        v = ValidationSummary(is_valid=True, errors=())
        assert v.is_valid is True
        assert v.errors == ()

    def test_with_errors(self) -> None:
        v = ValidationSummary(is_valid=False, errors=("No source configured.",))
        assert v.is_valid is False
        assert len(v.errors) == 1


class TestCompositionState:
    def _empty_state(self) -> CompositionState:
        return CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=1,
        )

    def _make_source(self) -> SourceSpec:
        return SourceSpec(
            plugin="csv",
            on_success="transform_1",
            options={"path": "/data/in.csv"},
            on_validation_failure="quarantine",
        )

    def _make_node(self, id: str = "transform_1") -> NodeSpec:
        return NodeSpec(
            id=id,
            node_type="transform",
            plugin="uppercase",
            input="source_out",
            on_success="sink_main",
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )

    def _make_edge(self, id: str = "e1") -> EdgeSpec:
        return EdgeSpec(
            id=id,
            from_node="source",
            to_node="transform_1",
            edge_type="on_success",
            label=None,
        )

    def _make_output(self, name: str = "main_output") -> OutputSpec:
        return OutputSpec(
            name=name,
            plugin="csv",
            options={"path": "/out.csv"},
            on_write_failure="quarantine",
        )

    # --- Immutability ---

    def test_frozen(self) -> None:
        state = self._empty_state()
        with pytest.raises(AttributeError):
            state.version = 2  # type: ignore[misc]

    def test_nodes_tuple_frozen(self) -> None:
        """nodes is a tuple — cannot append."""
        state = self._empty_state()
        assert isinstance(state.nodes, tuple)

    def test_metadata_frozen(self) -> None:
        """metadata is a frozen dataclass — deep freeze via freeze_fields."""
        state = self._empty_state()
        with pytest.raises(AttributeError):
            state.metadata.name = "mutated"  # type: ignore[misc]

    # --- with_source ---

    def test_with_source_returns_new_instance(self) -> None:
        state = self._empty_state()
        src = self._make_source()
        new_state = state.with_source(src)
        assert new_state is not state
        assert new_state.source is src
        assert state.source is None  # original unchanged

    def test_with_source_increments_version(self) -> None:
        state = self._empty_state()
        new_state = state.with_source(self._make_source())
        assert new_state.version == 2

    # --- with_node ---

    def test_with_node_adds(self) -> None:
        state = self._empty_state()
        node = self._make_node()
        new_state = state.with_node(node)
        assert len(new_state.nodes) == 1
        assert new_state.nodes[0].id == "transform_1"
        assert new_state.version == 2

    def test_with_node_replaces_existing(self) -> None:
        state = self._empty_state()
        node1 = self._make_node("t1")
        node2 = self._make_node("t1")  # same ID
        state2 = state.with_node(node1)
        state3 = state2.with_node(node2)
        assert len(state3.nodes) == 1
        assert state3.version == 3

    def test_with_node_preserves_order(self) -> None:
        state = self._empty_state()
        state = state.with_node(self._make_node("a"))
        state = state.with_node(self._make_node("b"))
        state = state.with_node(self._make_node("c"))
        assert [n.id for n in state.nodes] == ["a", "b", "c"]

    # --- without_node ---

    def test_without_node_removes(self) -> None:
        state = self._empty_state().with_node(self._make_node("t1"))
        new_state = state.without_node("t1")
        assert new_state is not None
        assert len(new_state.nodes) == 0
        assert new_state.version == 3

    def test_without_node_nonexistent_returns_none(self) -> None:
        state = self._empty_state()
        result = state.without_node("nonexistent")
        assert result is None

    # --- with_edge ---

    def test_with_edge_adds(self) -> None:
        state = self._empty_state()
        edge = self._make_edge()
        new_state = state.with_edge(edge)
        assert len(new_state.edges) == 1
        assert new_state.version == 2

    def test_with_edge_replaces_by_id(self) -> None:
        state = self._empty_state()
        e1 = EdgeSpec(id="e1", from_node="source", to_node="t1", edge_type="on_success", label=None)
        e1_updated = EdgeSpec(id="e1", from_node="source", to_node="t2", edge_type="on_success", label=None)
        state2 = state.with_edge(e1).with_edge(e1_updated)
        assert len(state2.edges) == 1
        assert state2.edges[0].to_node == "t2"

    def test_with_edge_preserves_order(self) -> None:
        """Updating an existing edge must preserve its position, not append."""
        state = self._empty_state()
        e1 = EdgeSpec(id="e1", from_node="source", to_node="t1", edge_type="on_success", label=None)
        e2 = EdgeSpec(id="e2", from_node="t1", to_node="t2", edge_type="on_success", label=None)
        e3 = EdgeSpec(id="e3", from_node="t2", to_node="sink", edge_type="on_success", label=None)
        state = state.with_edge(e1).with_edge(e2).with_edge(e3)
        assert [e.id for e in state.edges] == ["e1", "e2", "e3"]

        # Update e2 — should stay at index 1, not move to end
        e2_updated = EdgeSpec(id="e2", from_node="t1", to_node="t2_new", edge_type="on_success", label="updated")
        updated = state.with_edge(e2_updated)
        assert [e.id for e in updated.edges] == ["e1", "e2", "e3"]
        assert updated.edges[1].to_node == "t2_new"
        assert updated.edges[1].label == "updated"

    # --- without_edge ---

    def test_without_edge_removes(self) -> None:
        state = self._empty_state().with_edge(self._make_edge("e1"))
        new_state = state.without_edge("e1")
        assert new_state is not None
        assert len(new_state.edges) == 0

    def test_without_edge_nonexistent_returns_none(self) -> None:
        state = self._empty_state()
        result = state.without_edge("nonexistent")
        assert result is None

    # --- with_output ---

    def test_with_output_adds(self) -> None:
        state = self._empty_state()
        output = self._make_output()
        new_state = state.with_output(output)
        assert len(new_state.outputs) == 1
        assert new_state.version == 2

    def test_with_output_replaces_by_name(self) -> None:
        state = self._empty_state()
        o1 = self._make_output("out")
        o2 = OutputSpec(name="out", plugin="json", options={}, on_write_failure="discard")
        state2 = state.with_output(o1).with_output(o2)
        assert len(state2.outputs) == 1
        assert state2.outputs[0].plugin == "json"

    def test_with_output_preserves_order(self) -> None:
        """Updating an existing output must preserve its position, not append."""
        state = self._empty_state()
        o1 = self._make_output("alpha")
        o2 = self._make_output("beta")
        o3 = self._make_output("gamma")
        state = state.with_output(o1).with_output(o2).with_output(o3)
        assert [o.name for o in state.outputs] == ["alpha", "beta", "gamma"]

        # Update beta — should stay at index 1, not move to end
        o2_updated = OutputSpec(name="beta", plugin="json", options={"format": "lines"}, on_write_failure="discard")
        updated = state.with_output(o2_updated)
        assert [o.name for o in updated.outputs] == ["alpha", "beta", "gamma"]
        assert updated.outputs[1].plugin == "json"

    # --- without_output ---

    def test_without_output_removes(self) -> None:
        state = self._empty_state().with_output(self._make_output("out"))
        new_state = state.without_output("out")
        assert new_state is not None
        assert len(new_state.outputs) == 0

    def test_without_output_nonexistent_returns_none(self) -> None:
        result = self._empty_state().without_output("nope")
        assert result is None

    # --- with_metadata ---

    def test_with_metadata_partial_update(self) -> None:
        state = self._empty_state()
        new_state = state.with_metadata({"name": "My Pipeline"})
        assert new_state.metadata.name == "My Pipeline"
        assert new_state.metadata.description == ""  # unchanged
        assert new_state.version == 2

    def test_with_metadata_full_update(self) -> None:
        state = self._empty_state()
        new_state = state.with_metadata({"name": "P1", "description": "Desc"})
        assert new_state.metadata.name == "P1"
        assert new_state.metadata.description == "Desc"

    # --- to_dict ---

    def test_to_dict_unwraps_frozen_containers(self) -> None:
        """to_dict() converts MappingProxyType -> dict and tuple -> list."""
        state = self._empty_state()
        src = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"k": "v"}},
            on_validation_failure="discard",
        )
        state = state.with_source(src)
        state = state.with_node(self._make_node("t1"))
        state = state.with_output(self._make_output("out"))

        d = state.to_dict()
        assert isinstance(d, dict)
        assert isinstance(d["nodes"], list)
        assert isinstance(d["source"]["options"], dict)
        assert isinstance(d["source"]["options"]["nested"], dict)
        assert isinstance(d["outputs"], list)

    def test_to_dict_roundtrip_yaml(self) -> None:
        """to_dict() output is yaml.dump()-safe (no MappingProxyType errors)."""
        import yaml

        state = self._empty_state()
        src = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"deep": {"k": "v"}}},
            on_validation_failure="quarantine",
        )
        state = state.with_source(src)
        d = state.to_dict()
        yaml_str = yaml.dump(d, default_flow_style=False)
        assert "csv" in yaml_str

    def test_mutation_refreezes_containers(self) -> None:
        """Mutation methods must re-freeze since dataclasses.replace() skips __post_init__."""
        state = self._empty_state()
        src = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"k": "v"}},
            on_validation_failure="discard",
        )
        new_state = state.with_source(src)
        assert isinstance(new_state.nodes, tuple)
        with pytest.raises(TypeError):
            new_state.source.options["new"] = "x"  # type: ignore[union-attr, index]

    # --- from_dict round-trip ---

    def test_from_dict_round_trip_empty(self) -> None:
        """Empty state round-trips through to_dict/from_dict."""
        state = self._empty_state()
        restored = CompositionState.from_dict(state.to_dict())
        assert restored == state

    def test_from_dict_round_trip_fully_populated(self) -> None:
        """Fully populated state round-trips through to_dict/from_dict."""
        gate = NodeSpec(
            id="gate_1",
            node_type="gate",
            plugin=None,
            input="source_out",
            on_success=None,
            on_error=None,
            options={},
            condition="row['score'] >= 0.5",
            routes={"high": "sink_good", "low": "sink_bad"},
            fork_to=("path_a", "path_b"),
            branches=None,
            policy=None,
            merge=None,
        )
        coalesce = NodeSpec(
            id="coal_1",
            node_type="coalesce",
            plugin=None,
            input="join_point",
            on_success="main_output",
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=("path_a", "path_b"),
            policy="require_all",
            merge="nested",
        )
        state = CompositionState(
            source=SourceSpec(
                plugin="csv",
                on_success="transform_1",
                options={"path": "/data/in.csv", "nested": {"key": "val"}},
                on_validation_failure="quarantine",
            ),
            nodes=(self._make_node("transform_1"), gate, coalesce),
            edges=(
                self._make_edge("e1"),
                EdgeSpec(id="e2", from_node="gate_1", to_node="sink_good", edge_type="route_true", label="high"),
            ),
            outputs=(
                self._make_output("main_output"),
                OutputSpec(name="sink_good", plugin="json", options={"indent": 2}, on_write_failure="discard"),
            ),
            metadata=PipelineMetadata(name="Test Pipeline", description="A fully populated test state"),
            version=42,
        )
        restored = CompositionState.from_dict(state.to_dict())
        assert restored == state

    def test_from_dict_round_trip_none_optional_fields(self) -> None:
        """NodeSpec optional fields omitted by to_dict() reconstruct as None."""
        node = self._make_node("t1")
        state = self._empty_state().with_node(node)
        restored = CompositionState.from_dict(state.to_dict())
        restored_node = restored.nodes[0]
        assert restored_node.condition is None
        assert restored_node.routes is None
        assert restored_node.fork_to is None
        assert restored_node.branches is None
        assert restored_node.policy is None
        assert restored_node.merge is None

    def test_from_dict_containers_are_frozen(self) -> None:
        """from_dict() output has deep-frozen containers (not plain dicts)."""
        state = self._empty_state()
        src = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"nested": {"k": "v"}},
            on_validation_failure="discard",
        )
        state = state.with_source(src)
        restored = CompositionState.from_dict(state.to_dict())
        assert restored.source is not None
        assert restored.source.options is not None
        with pytest.raises(TypeError):
            restored.source.options["new"] = "x"  # type: ignore[index]
        with pytest.raises(TypeError):
            restored.source.options["nested"]["mutate"] = "y"


class TestStage1Validation:
    def _empty_state(self) -> CompositionState:
        return CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(),
            version=1,
        )

    def _make_source(self, on_success: str = "t1") -> SourceSpec:
        return SourceSpec(
            plugin="csv",
            on_success=on_success,
            options={},
            on_validation_failure="quarantine",
        )

    def _make_transform(self, id: str, input: str, on_success: str) -> NodeSpec:
        return NodeSpec(
            id=id,
            node_type="transform",
            plugin="uppercase",
            input=input,
            on_success=on_success,
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )

    def _make_output(self, name: str = "main") -> OutputSpec:
        return OutputSpec(name=name, plugin="csv", options={}, on_write_failure="discard")

    def _make_edge(
        self,
        id: str,
        from_node: str,
        to_node: str,
        edge_type: EdgeType = "on_success",
    ) -> EdgeSpec:
        return EdgeSpec(id=id, from_node=from_node, to_node=to_node, edge_type=edge_type, label=None)

    def test_empty_state_has_errors(self) -> None:
        result = self._empty_state().validate()
        assert not result.is_valid
        assert "No source configured." in result.errors
        assert "No sinks configured." in result.errors

    def test_minimal_valid_pipeline(self) -> None:
        """source -> transform -> sink, fully connected."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "source_out", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert result.is_valid, result.errors

    def test_dangling_edge_from_node(self) -> None:
        state = self._empty_state()
        state = state.with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "nonexistent", "main"))
        result = state.validate()
        assert not result.is_valid
        assert any("nonexistent" in e and "from_node" in e for e in result.errors)

    def test_dangling_edge_to_node(self) -> None:
        state = self._empty_state()
        state = state.with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_edge(self._make_edge("e1", "source", "nonexistent"))
        result = state.validate()
        assert not result.is_valid
        assert any("nonexistent" in e and "to_node" in e for e in result.errors)

    def test_duplicate_node_ids(self) -> None:
        """Two nodes with same id — caught by validation, not by with_node (which replaces)."""
        node = self._make_transform("dup", "in", "out")
        state = CompositionState(
            source=self._make_source(),
            nodes=(node, node),
            edges=(),
            outputs=(self._make_output(),),
            metadata=PipelineMetadata(),
            version=1,
        )
        result = state.validate()
        assert not result.is_valid
        assert any("Duplicate node ID" in e for e in result.errors)

    def test_duplicate_output_names(self) -> None:
        out = self._make_output("dup")
        state = CompositionState(
            source=self._make_source(),
            nodes=(),
            edges=(),
            outputs=(out, out),
            metadata=PipelineMetadata(),
            version=1,
        )
        result = state.validate()
        assert not result.is_valid
        assert any("Duplicate output name" in e for e in result.errors)

    def test_duplicate_edge_ids(self) -> None:
        edge = self._make_edge("dup", "source", "main")
        state = CompositionState(
            source=self._make_source(),
            nodes=(),
            edges=(edge, edge),
            outputs=(self._make_output(),),
            metadata=PipelineMetadata(),
            version=1,
        )
        result = state.validate()
        assert not result.is_valid
        assert any("Duplicate edge ID" in e for e in result.errors)

    def test_gate_missing_condition(self) -> None:
        gate = NodeSpec(
            id="g1",
            node_type="gate",
            plugin=None,
            input="in",
            on_success=None,
            on_error=None,
            options={},
            condition=None,
            routes={"high": "s1"},
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )
        state = self._empty_state().with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_node(gate)
        state = state.with_edge(self._make_edge("e1", "source", "g1"))
        result = state.validate()
        assert not result.is_valid
        assert any("condition" in e for e in result.errors)

    def test_gate_missing_routes(self) -> None:
        gate = NodeSpec(
            id="g1",
            node_type="gate",
            plugin=None,
            input="in",
            on_success=None,
            on_error=None,
            options={},
            condition="row['x'] > 1",
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )
        state = self._empty_state().with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_node(gate)
        state = state.with_edge(self._make_edge("e1", "source", "g1"))
        result = state.validate()
        assert not result.is_valid
        assert any("routes" in e for e in result.errors)

    def test_transform_with_condition_is_error(self) -> None:
        node = NodeSpec(
            id="t1",
            node_type="transform",
            plugin="uppercase",
            input="in",
            on_success="out",
            on_error=None,
            options={},
            condition="row['x'] > 1",
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )
        state = self._empty_state().with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_node(node)
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        result = state.validate()
        assert not result.is_valid
        assert any("condition" in e for e in result.errors)

    def test_coalesce_missing_branches(self) -> None:
        node = NodeSpec(
            id="c1",
            node_type="coalesce",
            plugin=None,
            input="join",
            on_success="out",
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=None,
            policy="require_all",
            merge="nested",
        )
        state = self._empty_state().with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_node(node)
        state = state.with_edge(self._make_edge("e1", "source", "c1"))
        result = state.validate()
        assert not result.is_valid
        assert any("branches" in e for e in result.errors)

    def test_aggregation_missing_plugin(self) -> None:
        node = NodeSpec(
            id="a1",
            node_type="aggregation",
            plugin=None,
            input="in",
            on_success="out",
            on_error=None,
            options={},
            condition=None,
            routes=None,
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )
        state = self._empty_state().with_source(self._make_source())
        state = state.with_output(self._make_output())
        state = state.with_node(node)
        state = state.with_edge(self._make_edge("e1", "source", "a1"))
        result = state.validate()
        assert not result.is_valid
        assert any("plugin" in e for e in result.errors)

    def test_unreachable_node(self) -> None:
        """Node exists but no edge points to it and source.on_success doesn't match."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="other"))
        state = state.with_node(self._make_transform("t1", "somewhere", "main"))
        state = state.with_output(self._make_output())
        result = state.validate()
        assert not result.is_valid
        assert any("not reachable" in e for e in result.errors)

    def test_validate_after_from_dict_round_trip(self) -> None:
        """W-4A-2: validate() on reconstructed state matches original."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "source_out", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))

        restored = CompositionState.from_dict(state.to_dict())
        result = restored.validate()
        assert result.is_valid, result.errors

    # --- Warning rules (W1-W4) ---

    def test_validate_output_no_incoming_edge_warns(self) -> None:
        """W1: Output with no edge targeting it produces a warning."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "t1", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_output(self._make_output("orphan"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert result.is_valid
        assert any("orphan" in w and "never receive data" in w for w in result.warnings)

    def test_validate_source_on_success_mismatch_warns(self) -> None:
        """W2: Source on_success doesn't match any node input."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="nonexistent"))
        state = state.with_node(self._make_transform("t1", "other_input", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert any("nonexistent" in w and "does not match" in w for w in result.warnings)

    def test_validate_format_extension_mismatch_warns(self) -> None:
        """W4: Sink plugin/filename extension mismatch."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "t1", "results"))
        output = OutputSpec(
            name="results",
            plugin="csv",
            options={"path": "/output/data.json"},
            on_write_failure="discard",
        )
        state = state.with_output(output)
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "results"))
        result = state.validate()
        assert result.is_valid
        assert any("extension suggests a different format" in w for w in result.warnings)

    # --- Suggestion rules (S1-S3) ---

    def test_validate_no_error_routing_suggests(self) -> None:
        """S1: Pipeline with no gates and no on_error edges gets a suggestion."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "t1", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert result.is_valid
        assert any("error routing" in s for s in result.suggestions)

    def test_validate_single_output_suggests(self) -> None:
        """S2: Pipeline with only one output gets a suggestion."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "t1", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert any("second output" in s for s in result.suggestions)

    def test_validate_no_schema_config_suggests(self) -> None:
        """S3: Source without schema_config in options gets a suggestion."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "t1", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert any("no explicit schema" in s for s in result.suggestions)

    # --- Interaction tests ---

    def test_validate_warnings_dont_block(self) -> None:
        """Warnings don't affect is_valid."""
        state = self._empty_state()
        state = state.with_source(self._make_source(on_success="t1"))
        state = state.with_node(self._make_transform("t1", "t1", "main"))
        state = state.with_output(self._make_output("main"))
        state = state.with_output(self._make_output("orphan"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "main"))
        result = state.validate()
        assert result.is_valid is True
        assert len(result.warnings) > 0

    def test_validate_errors_and_warnings_coexist(self) -> None:
        """A state with both errors and warnings populates both."""
        state = self._empty_state()
        # No source = error, orphan output = warning
        state = state.with_output(self._make_output("orphan"))
        result = state.validate()
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("never receive data" in w for w in result.warnings)

    def test_validate_clean_pipeline_no_warnings(self) -> None:
        """Well-formed pipeline with gates, error routing, schema, and
        multiple outputs has empty warnings and suggestions."""
        state = self._empty_state()
        source = SourceSpec(
            plugin="csv",
            on_success="t1",
            options={"path": "/in.csv", "schema_config": {"fields": []}},
            on_validation_failure="quarantine",
        )
        state = state.with_source(source)
        state = state.with_node(self._make_transform("t1", "t1", "gate_1"))
        gate = NodeSpec(
            id="gate_1",
            node_type="gate",
            plugin=None,
            input="gate_in",
            on_success=None,
            on_error=None,
            options={},
            condition="row['score'] >= 0.5",
            routes={"high": "main", "low": "errors"},
            fork_to=None,
            branches=None,
            policy=None,
            merge=None,
        )
        state = state.with_node(gate)
        state = state.with_output(self._make_output("main"))
        state = state.with_output(self._make_output("errors"))
        state = state.with_edge(self._make_edge("e1", "source", "t1"))
        state = state.with_edge(self._make_edge("e2", "t1", "gate_1"))
        state = state.with_edge(self._make_edge("e3", "gate_1", "main"))
        state = state.with_edge(self._make_edge("e4", "gate_1", "errors"))
        result = state.validate()
        assert result.is_valid, result.errors
        assert result.warnings == ()
        assert result.suggestions == ()
