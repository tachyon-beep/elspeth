"""Tests for composition tools — discovery delegation and mutation + validation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from elspeth.web.catalog.schemas import (
    ConfigFieldSummary,
    PluginSchemaInfo,
    PluginSummary,
)
from elspeth.web.composer.state import (
    CompositionState,
    PipelineMetadata,
)
from elspeth.web.composer.tools import (
    ToolResult,
    execute_tool,
    get_expression_grammar,
    get_tool_definitions,
)


def _empty_state() -> CompositionState:
    return CompositionState(
        source=None,
        nodes=(),
        edges=(),
        outputs=(),
        metadata=PipelineMetadata(),
        version=1,
    )


def _mock_catalog() -> MagicMock:
    """Mock CatalogService with real PluginSummary/PluginSchemaInfo instances.

    AC #16: Tests must use real PluginSummary and PluginSchemaInfo instances,
    not plain dicts. Mock return types must match the CatalogService protocol.
    """
    catalog = MagicMock()
    catalog.list_sources.return_value = [
        PluginSummary(
            name="csv",
            description="CSV file source",
            plugin_type="source",
            config_fields=[
                ConfigFieldSummary(name="path", type="string", required=True, description="File path", default=None),
            ],
        ),
        PluginSummary(
            name="json",
            description="JSON file source",
            plugin_type="source",
            config_fields=[],
        ),
    ]
    catalog.list_transforms.return_value = [
        PluginSummary(
            name="uppercase",
            description="Uppercase transform",
            plugin_type="transform",
            config_fields=[],
        ),
    ]
    catalog.list_sinks.return_value = [
        PluginSummary(
            name="csv",
            description="CSV file sink",
            plugin_type="sink",
            config_fields=[],
        ),
    ]
    catalog.get_schema.return_value = PluginSchemaInfo(
        name="csv",
        plugin_type="source",
        description="CSV file source",
        json_schema={"title": "CsvSourceConfig", "properties": {"path": {"type": "string"}}},
    )
    return catalog


class TestToolResult:
    def test_frozen(self) -> None:
        state = _empty_state()
        from elspeth.web.composer.state import ValidationSummary

        result = ToolResult(
            success=True,
            updated_state=state,
            validation=ValidationSummary(is_valid=False, errors=("err",)),
            affected_nodes=("n1", "n2"),
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]

    def test_affected_nodes_frozen(self) -> None:
        state = _empty_state()
        from elspeth.web.composer.state import ValidationSummary

        result = ToolResult(
            success=True,
            updated_state=state,
            validation=ValidationSummary(is_valid=True, errors=()),
            affected_nodes=("n1",),
        )
        assert isinstance(result.affected_nodes, tuple)


class TestSetSource:
    def test_sets_source(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"path": "/data/in.csv"},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
        )
        assert result.success is True
        assert result.updated_state.source is not None
        assert result.updated_state.source.plugin == "csv"
        assert result.updated_state.version == 2
        assert "source" in result.affected_nodes

    def test_unknown_plugin_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        catalog.get_schema.side_effect = ValueError("Unknown plugin: foobar")
        result = execute_tool(
            "set_source",
            {
                "plugin": "foobar",
                "on_success": "t1",
                "options": {},
                "on_validation_failure": "discard",
            },
            state,
            catalog,
        )
        assert result.success is False
        assert result.updated_state.source is None  # unchanged
        assert result.updated_state.version == 1
        assert result.data is not None
        assert "foobar" in result.data["error"].lower()


class TestUpsertNode:
    def test_adds_new_node(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "upsert_node",
            {
                "id": "t1",
                "node_type": "transform",
                "plugin": "uppercase",
                "input": "source_out",
                "on_success": "main",
                "options": {},
            },
            state,
            catalog,
        )
        assert result.success is True
        assert len(result.updated_state.nodes) == 1
        assert "t1" in result.affected_nodes

    def test_replaces_existing_node(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result1 = execute_tool(
            "upsert_node",
            {
                "id": "t1",
                "node_type": "transform",
                "plugin": "uppercase",
                "input": "in",
                "on_success": "out",
                "options": {},
            },
            state,
            catalog,
        )
        result2 = execute_tool(
            "upsert_node",
            {
                "id": "t1",
                "node_type": "transform",
                "plugin": "uppercase",
                "input": "new_in",
                "on_success": "out",
                "options": {"field": "x"},
            },
            result1.updated_state,
            catalog,
        )
        assert result2.success is True
        assert len(result2.updated_state.nodes) == 1
        assert result2.updated_state.nodes[0].input == "new_in"

    def test_gate_node_no_plugin_validation(self) -> None:
        """Gates don't have plugins — should not validate against catalog."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "upsert_node",
            {
                "id": "g1",
                "node_type": "gate",
                "plugin": None,
                "input": "in",
                "on_success": None,
                "options": {},
                "condition": "row['x'] > 0",
                "routes": {"high": "s1", "low": "s2"},
            },
            state,
            catalog,
        )
        assert result.success is True
        catalog.get_schema.assert_not_called()

    def test_upsert_node_unknown_transform_plugin_fails(self) -> None:
        """W-4B-1: LLM hallucinates a transform plugin name."""
        state = _empty_state()
        catalog = _mock_catalog()
        catalog.get_schema.side_effect = ValueError("Unknown plugin: nonexistent_xyz")
        result = execute_tool(
            "upsert_node",
            {
                "id": "t1",
                "node_type": "transform",
                "plugin": "nonexistent_xyz",
                "input": "in",
                "on_success": "out",
                "options": {},
            },
            state,
            catalog,
        )
        assert result.success is False
        assert result.updated_state.version == 1  # unchanged


class TestUpsertEdge:
    def test_adds_edge(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "upsert_edge",
            {
                "id": "e1",
                "from_node": "source",
                "to_node": "t1",
                "edge_type": "on_success",
                "label": None,
            },
            state,
            catalog,
        )
        assert result.success is True
        assert len(result.updated_state.edges) == 1
        assert "source" in result.affected_nodes
        assert "t1" in result.affected_nodes


class TestRemoveNode:
    def test_removes_node_and_edges(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        # Add a node and an edge to it
        r1 = execute_tool(
            "upsert_node",
            {
                "id": "t1",
                "node_type": "transform",
                "plugin": "uppercase",
                "input": "in",
                "on_success": "out",
                "options": {},
            },
            state,
            catalog,
        )
        r2 = execute_tool(
            "upsert_edge",
            {
                "id": "e1",
                "from_node": "source",
                "to_node": "t1",
                "edge_type": "on_success",
                "label": None,
            },
            r1.updated_state,
            catalog,
        )
        # Remove the node — edge should also be removed
        r3 = execute_tool("remove_node", {"id": "t1"}, r2.updated_state, catalog)
        assert r3.success is True
        assert len(r3.updated_state.nodes) == 0
        assert len(r3.updated_state.edges) == 0

    def test_remove_nonexistent_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool("remove_node", {"id": "nope"}, state, catalog)
        assert result.success is False
        assert result.updated_state.version == 1  # unchanged


class TestRemoveEdge:
    def test_removes_edge(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        r1 = execute_tool(
            "upsert_edge",
            {
                "id": "e1",
                "from_node": "source",
                "to_node": "t1",
                "edge_type": "on_success",
                "label": None,
            },
            state,
            catalog,
        )
        r2 = execute_tool("remove_edge", {"id": "e1"}, r1.updated_state, catalog)
        assert r2.success is True
        assert len(r2.updated_state.edges) == 0

    def test_remove_nonexistent_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool("remove_edge", {"id": "nope"}, state, catalog)
        assert result.success is False


class TestSetMetadata:
    def test_partial_update(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_metadata",
            {"patch": {"name": "My Pipeline"}},
            state,
            catalog,
        )
        assert result.success is True
        assert result.updated_state.metadata.name == "My Pipeline"
        assert result.updated_state.metadata.description == ""  # preserved
        assert result.affected_nodes == ()  # metadata doesn't affect nodes

    def test_missing_patch_key_raises(self) -> None:
        """LLM omits required 'patch' key — KeyError propagates to service handler."""
        state = _empty_state()
        catalog = _mock_catalog()
        with pytest.raises(KeyError):
            execute_tool("set_metadata", {"name": "Oops"}, state, catalog)


class TestSetOutput:
    def test_adds_output(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_output",
            {
                "sink_name": "main",
                "plugin": "csv",
                "options": {"path": "/data/out.csv"},
                "on_write_failure": "discard",
            },
            state,
            catalog,
        )
        assert result.success is True
        assert len(result.updated_state.outputs) == 1
        assert result.updated_state.outputs[0].name == "main"
        assert result.updated_state.outputs[0].plugin == "csv"
        assert result.updated_state.version == 2
        assert "main" in result.affected_nodes

    def test_replaces_existing_output(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        r1 = execute_tool(
            "set_output",
            {
                "sink_name": "main",
                "plugin": "csv",
                "options": {},
                "on_write_failure": "discard",
            },
            state,
            catalog,
        )
        r2 = execute_tool(
            "set_output",
            {
                "sink_name": "main",
                "plugin": "csv",
                "options": {"path": "/new.csv"},
                "on_write_failure": "quarantine",
            },
            r1.updated_state,
            catalog,
        )
        assert r2.success is True
        assert len(r2.updated_state.outputs) == 1
        assert r2.updated_state.outputs[0].on_write_failure == "quarantine"

    def test_unknown_sink_plugin_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        catalog.get_schema.side_effect = ValueError("Unknown plugin: foobar")
        result = execute_tool(
            "set_output",
            {
                "sink_name": "main",
                "plugin": "foobar",
                "options": {},
                "on_write_failure": "discard",
            },
            state,
            catalog,
        )
        assert result.success is False
        assert result.updated_state.version == 1  # unchanged


class TestRemoveOutput:
    def test_removes_output(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        r1 = execute_tool(
            "set_output",
            {
                "sink_name": "main",
                "plugin": "csv",
                "options": {},
                "on_write_failure": "discard",
            },
            state,
            catalog,
        )
        r2 = execute_tool("remove_output", {"sink_name": "main"}, r1.updated_state, catalog)
        assert r2.success is True
        assert len(r2.updated_state.outputs) == 0

    def test_remove_nonexistent_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool("remove_output", {"sink_name": "nope"}, state, catalog)
        assert result.success is False
        assert result.updated_state.version == 1  # unchanged


class TestSetSourcePathSecurity:
    """S2: Source path allowlist — paths must be under {data_dir}/uploads/."""

    def test_path_under_uploads_succeeds(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"path": "/data/uploads/input.csv"},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
            data_dir="/data",
        )
        assert result.success is True

    def test_path_outside_uploads_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"path": "/etc/passwd"},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
            data_dir="/data",
        )
        assert result.success is False
        assert "path" in result.data["error"].lower()

    def test_traversal_attack_fails(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"path": "/data/uploads/../../etc/passwd"},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
            data_dir="/data",
        )
        assert result.success is False

    def test_file_key_also_validated(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"file": "/tmp/evil.csv"},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
            data_dir="/data",
        )
        assert result.success is False

    def test_file_key_traversal_via_uploads_prefix_fails(self) -> None:
        """W-4B-2: file key traversal starting from uploads prefix."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"file": "/data/uploads/../../etc/passwd"},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
            data_dir="/data",
        )
        assert result.success is False

    def test_no_path_key_skips_validation(self) -> None:
        """Source options without path/file keys are not subject to S2."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {"connection_string": "postgres://..."},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
            data_dir="/data",
        )
        assert result.success is True


class TestDiscoveryTools:
    def test_list_sources_delegates(self) -> None:
        catalog = _mock_catalog()
        result = execute_tool("list_sources", {}, _empty_state(), catalog)
        assert result.success is True
        catalog.list_sources.assert_called_once()

    def test_list_transforms_delegates(self) -> None:
        catalog = _mock_catalog()
        result = execute_tool("list_transforms", {}, _empty_state(), catalog)
        assert result.success is True
        catalog.list_transforms.assert_called_once()

    def test_list_sinks_delegates(self) -> None:
        catalog = _mock_catalog()
        result = execute_tool("list_sinks", {}, _empty_state(), catalog)
        assert result.success is True
        catalog.list_sinks.assert_called_once()

    def test_get_plugin_schema_delegates(self) -> None:
        catalog = _mock_catalog()
        result = execute_tool(
            "get_plugin_schema",
            {"plugin_type": "source", "name": "csv"},
            _empty_state(),
            catalog,
        )
        assert result.success is True
        catalog.get_schema.assert_called_once_with("source", "csv")

    def test_get_expression_grammar_is_static(self) -> None:
        grammar = get_expression_grammar()
        assert "row" in grammar
        assert isinstance(grammar, str)


class TestToolDefinitions:
    def test_has_thirteen_tools(self) -> None:
        """5 discovery + 8 mutation = 13 tools."""
        defs = get_tool_definitions()
        assert len(defs) == 13

    def test_all_have_json_schema(self) -> None:
        for defn in get_tool_definitions():
            assert "name" in defn
            assert "description" in defn
            assert "parameters" in defn


class TestToolResultValidation:
    def test_mutation_includes_validation(self) -> None:
        """Every mutation tool result includes validation summary."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source",
            {
                "plugin": "csv",
                "on_success": "t1",
                "options": {},
                "on_validation_failure": "quarantine",
            },
            state,
            catalog,
        )
        assert result.validation is not None
        # Source is set but no sinks — should have validation error
        assert not result.validation.is_valid
        assert any("No sinks" in e for e in result.validation.errors)
