"""Tests for composer MCP server — tool registration and dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from elspeth.composer_mcp.server import _build_tool_defs, _dispatch_tool
from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.composer.state import CompositionState, PipelineMetadata


def _empty_state() -> CompositionState:
    return CompositionState(
        source=None,
        nodes=(),
        edges=(),
        outputs=(),
        metadata=PipelineMetadata(),
        version=1,
    )


def _mock_catalog() -> CatalogService:
    catalog = MagicMock(spec=CatalogService)
    catalog.list_sources.return_value = []
    catalog.list_transforms.return_value = []
    catalog.list_sinks.return_value = []
    return catalog


class TestBuildToolDefs:
    """Tests for _build_tool_defs() tool registration."""

    def test_returns_more_than_20_tools(self) -> None:
        tools = _build_tool_defs()
        assert len(tools) > 20

    def test_expected_count_is_29(self) -> None:
        """23 composer (10 discovery + 13 mutation) + 6 session = 29."""
        tools = _build_tool_defs()
        assert len(tools) == 29

    def test_all_tools_have_name_and_description(self) -> None:
        for tool in _build_tool_defs():
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool {tool['name']} missing 'description'"
            assert tool["name"], "Tool name must be non-empty"
            assert tool["description"], f"Tool {tool['name']} has empty description"

    def test_discovery_tools_present(self) -> None:
        names = {t["name"] for t in _build_tool_defs()}
        for expected in ("list_sources", "list_transforms", "list_sinks", "get_plugin_schema", "get_expression_grammar"):
            assert expected in names, f"Discovery tool '{expected}' missing"

    def test_mutation_tools_present(self) -> None:
        names = {t["name"] for t in _build_tool_defs()}
        for expected in ("set_source", "upsert_node", "upsert_edge", "set_output", "set_pipeline"):
            assert expected in names, f"Mutation tool '{expected}' missing"

    def test_session_tools_present(self) -> None:
        names = {t["name"] for t in _build_tool_defs()}
        for expected in ("new_session", "save_session", "load_session", "list_sessions", "generate_yaml", "delete_session"):
            assert expected in names, f"Session tool '{expected}' missing"

    def test_blob_and_secret_tools_excluded(self) -> None:
        names = {t["name"] for t in _build_tool_defs()}
        for excluded in (
            "list_blobs",
            "set_source_from_blob",
            "get_blob_metadata",
            "list_secret_refs",
            "validate_secret_ref",
            "wire_secret_ref",
        ):
            assert excluded not in names, f"Blob/secret tool '{excluded}' should be excluded"


class TestDispatchTool:
    """Tests for _dispatch_tool() dispatch logic."""

    @pytest.fixture()
    def scratch_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "scratch"
        d.mkdir()
        return d

    def test_list_sources_returns_success(self, scratch_dir: Path) -> None:
        result = _dispatch_tool(
            "list_sources",
            {},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        assert result["success"] is True

    def test_set_source_mutates_state(self, scratch_dir: Path) -> None:
        result = _dispatch_tool(
            "set_source",
            {"plugin": "csv", "on_success": "node_1", "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}}},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        assert result["success"] is True
        assert result["state"]["source"]["plugin"] == "csv"

    def test_new_session_returns_session_id(self, scratch_dir: Path) -> None:
        result = _dispatch_tool(
            "new_session",
            {},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        assert result["success"] is True
        assert "session_id" in result["data"]

    def test_save_and_load_round_trip(self, scratch_dir: Path) -> None:
        # Create a session first
        new_result = _dispatch_tool(
            "new_session",
            {},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        session_id = new_result["data"]["session_id"]

        # Modify state via set_source
        modified = _dispatch_tool(
            "set_source",
            {"plugin": "csv", "on_success": "node_1", "options": {"path": "/data/blobs/input.csv", "schema": {"mode": "observed"}}},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        modified_state = CompositionState.from_dict(modified["state"])

        # Save the modified state
        save_result = _dispatch_tool(
            "save_session",
            {"session_id": session_id},
            modified_state,
            _mock_catalog(),
            scratch_dir,
        )
        assert save_result["success"] is True

        # Load it back
        load_result = _dispatch_tool(
            "load_session",
            {"session_id": session_id},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        assert load_result["success"] is True
        assert load_result["state"]["source"]["plugin"] == "csv"

    def test_generate_yaml_returns_string(self, scratch_dir: Path) -> None:
        result = _dispatch_tool(
            "generate_yaml",
            {},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        assert result["success"] is True
        assert isinstance(result["data"], str)

    def test_unknown_tool_returns_failure(self, scratch_dir: Path) -> None:
        result = _dispatch_tool(
            "nonexistent_tool",
            {},
            _empty_state(),
            _mock_catalog(),
            scratch_dir,
        )
        assert result["success"] is False
