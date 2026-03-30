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
            name="text",
            description="Text line source",
            plugin_type="source",
            config_fields=[],
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
    def test_has_nineteen_tools(self) -> None:
        """5 discovery + 8 mutation + 3 blob tools + 3 secret tools = 19 tools."""
        defs = get_tool_definitions()
        assert len(defs) == 19

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


class TestToolRegistry:
    """Tests for the tool registry pattern — two dicts + cacheable frozenset."""

    def test_discovery_tools_has_five_entries(self) -> None:
        from elspeth.web.composer.tools import _DISCOVERY_TOOLS

        assert len(_DISCOVERY_TOOLS) == 5
        expected = {
            "list_sources",
            "list_transforms",
            "list_sinks",
            "get_plugin_schema",
            "get_expression_grammar",
        }
        assert set(_DISCOVERY_TOOLS.keys()) == expected

    def test_mutation_tools_has_eight_entries(self) -> None:
        from elspeth.web.composer.tools import _MUTATION_TOOLS

        assert len(_MUTATION_TOOLS) == 8
        expected = {
            "set_source",
            "upsert_node",
            "upsert_edge",
            "remove_node",
            "remove_edge",
            "set_metadata",
            "set_output",
            "remove_output",
        }
        assert set(_MUTATION_TOOLS.keys()) == expected

    def test_no_overlap_between_registries(self) -> None:
        from elspeth.web.composer.tools import _DISCOVERY_TOOLS, _MUTATION_TOOLS

        overlap = set(_DISCOVERY_TOOLS.keys()) & set(_MUTATION_TOOLS.keys())
        assert overlap == set(), f"Registry overlap: {overlap}"

    def test_cacheable_discovery_equals_discovery(self) -> None:
        """All discovery tools are cacheable (get_current_state was removed)."""
        from elspeth.web.composer.tools import (
            _CACHEABLE_DISCOVERY_TOOLS,
            _DISCOVERY_TOOLS,
        )

        assert frozenset(_DISCOVERY_TOOLS.keys()) == _CACHEABLE_DISCOVERY_TOOLS

    def test_cacheable_is_subset_of_discovery(self) -> None:
        from elspeth.web.composer.tools import (
            _CACHEABLE_DISCOVERY_TOOLS,
            _DISCOVERY_TOOLS,
        )

        assert set(_DISCOVERY_TOOLS.keys()) >= _CACHEABLE_DISCOVERY_TOOLS

    def test_is_discovery_tool(self) -> None:
        from elspeth.web.composer.tools import is_discovery_tool

        assert is_discovery_tool("list_sources") is True
        assert is_discovery_tool("get_expression_grammar") is True
        assert is_discovery_tool("set_source") is False
        assert is_discovery_tool("nonexistent") is False

    def test_is_cacheable_discovery_tool(self) -> None:
        from elspeth.web.composer.tools import is_cacheable_discovery_tool

        assert is_cacheable_discovery_tool("list_sources") is True
        assert is_cacheable_discovery_tool("get_plugin_schema") is True
        assert is_cacheable_discovery_tool("set_source") is False

    def test_registry_dispatch_matches_original_behaviour(self) -> None:
        """Every tool in the registries dispatches correctly via execute_tool."""
        state = _empty_state()
        catalog = _mock_catalog()

        # All discovery tools should succeed
        for tool_name in [
            "list_sources",
            "list_transforms",
            "list_sinks",
            "get_expression_grammar",
        ]:
            result = execute_tool(tool_name, {}, state, catalog)
            assert result.success is True, f"{tool_name} failed"

        # get_plugin_schema needs arguments
        result = execute_tool(
            "get_plugin_schema",
            {"plugin_type": "source", "name": "csv"},
            state,
            catalog,
        )
        assert result.success is True

        # Mutation tools that work on empty state
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
        assert result.success is True

        result = execute_tool(
            "set_metadata",
            {"patch": {"name": "Test"}},
            state,
            catalog,
        )
        assert result.success is True

        # Unknown tool returns failure
        result = execute_tool("nonexistent", {}, state, catalog)
        assert result.success is False

    def test_module_level_assertion_no_overlap(self) -> None:
        """Importing the module should not raise — the overlap assertion passes."""
        import importlib

        import elspeth.web.composer.tools as mod

        importlib.reload(mod)  # Force re-evaluation of module-level assertion


# ---------------------------------------------------------------------------
# Blob tool tests — composer-level security boundaries
# ---------------------------------------------------------------------------


class TestBlobTools:
    """Blob composition tools: session context enforcement, storage_path exclusion,
    status guards, and source plugin wiring.

    Security contracts tested:
    - Blob tools fail without session context (no ambient access)
    - get_blob_metadata never exposes storage_path to the LLM
    - Wrong session_id returns failure (IDOR at the tool layer)
    - set_source_from_blob rejects non-ready blobs
    - set_source_from_blob wires the correct source plugin from MIME type
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Create an in-memory SQLite engine with tables and seed data."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        from elspeth.web.sessions.models import blobs_table, metadata, sessions_table

        self.engine = create_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        metadata.create_all(self.engine)

        self.session_id = str(uuid4())
        self.other_session_id = str(uuid4())
        self.blob_id = str(uuid4())
        self.pending_blob_id = str(uuid4())

        now = datetime.now(UTC)

        with self.engine.begin() as conn:
            # Two sessions
            conn.execute(
                sessions_table.insert().values(
                    id=self.session_id,
                    user_id="test-user",
                    auth_provider_type="local",
                    title="Test Session",
                    created_at=now,
                    updated_at=now,
                )
            )
            conn.execute(
                sessions_table.insert().values(
                    id=self.other_session_id,
                    user_id="other-user",
                    auth_provider_type="local",
                    title="Other Session",
                    created_at=now,
                    updated_at=now,
                )
            )
            # Ready blob in session
            conn.execute(
                blobs_table.insert().values(
                    id=self.blob_id,
                    session_id=self.session_id,
                    filename="data.csv",
                    mime_type="text/csv",
                    size_bytes=100,
                    content_hash="abc123",
                    storage_path="/tmp/fake/data.csv",
                    created_at=now,
                    created_by="user",
                    source_description=None,
                    status="ready",
                )
            )
            # Pending blob in session
            conn.execute(
                blobs_table.insert().values(
                    id=self.pending_blob_id,
                    session_id=self.session_id,
                    filename="output.csv",
                    mime_type="text/csv",
                    size_bytes=0,
                    content_hash=None,
                    storage_path="/tmp/fake/output.csv",
                    created_at=now,
                    created_by="pipeline",
                    source_description=None,
                    status="pending",
                )
            )

    def test_list_blobs_without_session_context_returns_failure(self) -> None:
        """Blob tools with no session context must fail — no ambient data access."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool("list_blobs", {}, state, catalog)
        assert result.success is False

    def test_get_blob_metadata_excludes_storage_path(self) -> None:
        """storage_path must never be exposed to the LLM — it leaks filesystem layout."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "get_blob_metadata",
            {"blob_id": self.blob_id},
            state,
            catalog,
            session_engine=self.engine,
            session_id=self.session_id,
        )
        assert result.success is True
        assert "storage_path" not in result.data

    def test_get_blob_metadata_wrong_session_returns_failure(self) -> None:
        """IDOR at tool layer: blob belongs to session A, caller is session B."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "get_blob_metadata",
            {"blob_id": self.blob_id},
            state,
            catalog,
            session_engine=self.engine,
            session_id=self.other_session_id,
        )
        assert result.success is False

    def test_set_source_from_blob_rejects_non_ready(self) -> None:
        """Cannot wire a pending blob as source — content doesn't exist yet."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source_from_blob",
            {"blob_id": self.pending_blob_id, "on_success": "out"},
            state,
            catalog,
            session_engine=self.engine,
            session_id=self.session_id,
        )
        assert result.success is False

    def test_set_source_from_blob_wires_correct_plugin(self) -> None:
        """text/csv blob should auto-resolve to the 'csv' source plugin."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "set_source_from_blob",
            {"blob_id": self.blob_id, "on_success": "out"},
            state,
            catalog,
            session_engine=self.engine,
            session_id=self.session_id,
        )
        assert result.success is True
        assert result.updated_state.source is not None
        assert result.updated_state.source.plugin == "csv"

    def test_set_source_from_plain_text_blob_uses_text_source(self) -> None:
        """text/plain blob should auto-resolve to the 'text' source plugin."""
        from elspeth.web.sessions.models import blobs_table

        state = _empty_state()
        catalog = _mock_catalog()

        with self.engine.begin() as conn:
            conn.execute(blobs_table.update().where(blobs_table.c.id == self.blob_id).values(mime_type="text/plain"))

        result = execute_tool(
            "set_source_from_blob",
            {"blob_id": self.blob_id, "on_success": "out"},
            state,
            catalog,
            session_engine=self.engine,
            session_id=self.session_id,
        )

        assert result.success is True
        assert result.updated_state.source is not None
        assert result.updated_state.source.plugin == "text"


# ---------------------------------------------------------------------------
# Secret tool tests — composer-level secret reference wiring
# ---------------------------------------------------------------------------


class TestSecretTools:
    """Secret reference composition tools: discovery, validation, and wiring.

    Security contracts tested:
    - Secret tools fail without secret_service (no ambient access)
    - list_secret_refs never returns plaintext values
    - validate_secret_ref returns availability status
    - wire_secret_ref sets a secret_ref marker in source options
    """

    def _mock_secret_service(self) -> MagicMock:
        from elspeth.contracts.secrets import SecretInventoryItem

        svc = MagicMock()
        svc.list_refs.return_value = [
            SecretInventoryItem(name="OPENROUTER_API_KEY", scope="user", available=True),
            SecretInventoryItem(name="DB_PASSWORD", scope="server", available=True),
        ]
        svc.has_ref.return_value = True
        return svc

    def test_list_secret_refs_without_service_returns_failure(self) -> None:
        """Secret tools with no secret_service must fail — no ambient access."""
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool("list_secret_refs", {}, state, catalog)
        assert result.success is False

    def test_list_secret_refs_returns_inventory(self) -> None:
        """list_secret_refs returns inventory items without values."""
        state = _empty_state()
        catalog = _mock_catalog()
        svc = self._mock_secret_service()
        result = execute_tool(
            "list_secret_refs",
            {},
            state,
            catalog,
            secret_service=svc,
            user_id="test-user",
        )
        assert result.success is True
        assert len(result.data) == 2
        # Ensure no value field leaked
        for item in result.data:
            assert "value" not in item

    def test_validate_secret_ref_returns_availability(self) -> None:
        """validate_secret_ref returns name and availability status."""
        state = _empty_state()
        catalog = _mock_catalog()
        svc = self._mock_secret_service()
        result = execute_tool(
            "validate_secret_ref",
            {"name": "OPENROUTER_API_KEY"},
            state,
            catalog,
            secret_service=svc,
            user_id="test-user",
        )
        assert result.success is True
        assert result.data["name"] == "OPENROUTER_API_KEY"
        assert result.data["available"] is True

    def test_validate_secret_ref_without_service_returns_failure(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "validate_secret_ref",
            {"name": "OPENROUTER_API_KEY"},
            state,
            catalog,
        )
        assert result.success is False

    def test_wire_secret_ref_sets_marker_in_source_options(self) -> None:
        """wire_secret_ref patches source options with a secret_ref marker."""
        catalog = _mock_catalog()
        svc = self._mock_secret_service()
        # First set a source
        state = _empty_state()
        r1 = execute_tool(
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
        assert r1.success is True
        # Now wire a secret into the source
        r2 = execute_tool(
            "wire_secret_ref",
            {
                "name": "OPENROUTER_API_KEY",
                "target": "source",
                "option_key": "api_key",
            },
            r1.updated_state,
            catalog,
            secret_service=svc,
            user_id="test-user",
        )
        assert r2.success is True
        assert r2.updated_state.source is not None
        from elspeth.contracts.freeze import deep_thaw

        opts = deep_thaw(r2.updated_state.source.options)
        assert opts["api_key"] == {"secret_ref": "OPENROUTER_API_KEY"}
        # Original options preserved
        assert opts["path"] == "/data/in.csv"

    def test_wire_secret_ref_without_service_returns_failure(self) -> None:
        state = _empty_state()
        catalog = _mock_catalog()
        result = execute_tool(
            "wire_secret_ref",
            {
                "name": "OPENROUTER_API_KEY",
                "target": "source",
                "option_key": "api_key",
            },
            state,
            catalog,
        )
        assert result.success is False

    def test_wire_secret_ref_nonexistent_ref_fails(self) -> None:
        """wire_secret_ref fails if the secret ref doesn't exist."""
        catalog = _mock_catalog()
        svc = self._mock_secret_service()
        svc.has_ref.return_value = False
        state = _empty_state()
        r1 = execute_tool(
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
        r2 = execute_tool(
            "wire_secret_ref",
            {
                "name": "NONEXISTENT",
                "target": "source",
                "option_key": "api_key",
            },
            r1.updated_state,
            catalog,
            secret_service=svc,
            user_id="test-user",
        )
        assert r2.success is False
