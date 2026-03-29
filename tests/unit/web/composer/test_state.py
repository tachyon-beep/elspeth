"""Tests for CompositionState and supporting data models."""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.web.composer.state import (
    EdgeSpec,
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
            s.options["nested"]["mutate"] = "x"  # type: ignore[index]

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
        d = {
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

    def test_from_dict_uses_defaults_for_missing_fields(self) -> None:
        """Missing fields fall back to dataclass defaults."""
        restored = PipelineMetadata.from_dict({})
        assert restored.name == "Untitled Pipeline"
        assert restored.description == ""


class TestValidationSummary:
    def test_valid(self) -> None:
        v = ValidationSummary(is_valid=True, errors=())
        assert v.is_valid is True
        assert v.errors == ()

    def test_with_errors(self) -> None:
        v = ValidationSummary(is_valid=False, errors=("No source configured.",))
        assert v.is_valid is False
        assert len(v.errors) == 1
