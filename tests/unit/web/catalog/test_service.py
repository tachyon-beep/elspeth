"""Tests for CatalogServiceImpl with real PluginManager."""

from __future__ import annotations

import pytest

from elspeth.plugins.infrastructure.manager import PluginManager
from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.catalog.schemas import PluginSchemaInfo, PluginSummary
from elspeth.web.catalog.service import CatalogServiceImpl


@pytest.fixture(scope="module")
def plugin_manager() -> PluginManager:
    """Shared PluginManager with builtins registered."""
    pm = PluginManager()
    pm.register_builtin_plugins()
    return pm


@pytest.fixture(scope="module")
def catalog(plugin_manager: PluginManager) -> CatalogServiceImpl:
    return CatalogServiceImpl(plugin_manager)


class TestCatalogServiceProtocol:
    """CatalogServiceImpl satisfies the CatalogService protocol."""

    def test_implements_protocol(self, catalog: CatalogServiceImpl) -> None:
        assert isinstance(catalog, CatalogService)


class TestListSources:
    """list_sources() returns all registered source plugins."""

    def test_returns_non_empty_list(self, catalog: CatalogServiceImpl) -> None:
        sources = catalog.list_sources()
        assert len(sources) > 0

    def test_csv_source_present(self, catalog: CatalogServiceImpl) -> None:
        sources = catalog.list_sources()
        names = [s.name for s in sources]
        assert "csv" in names

    def test_all_entries_are_plugin_summaries(self, catalog: CatalogServiceImpl) -> None:
        sources = catalog.list_sources()
        for s in sources:
            assert isinstance(s, PluginSummary)
            assert s.plugin_type == "source"
            assert s.name
            assert s.description

    def test_config_fields_populated_for_csv(self, catalog: CatalogServiceImpl) -> None:
        sources = catalog.list_sources()
        csv_source = next(s for s in sources if s.name == "csv")
        field_names = [f.name for f in csv_source.config_fields]
        assert "path" in field_names

    def test_config_field_has_type_and_required(self, catalog: CatalogServiceImpl) -> None:
        sources = catalog.list_sources()
        csv_source = next(s for s in sources if s.name == "csv")
        for field in csv_source.config_fields:
            assert field.type
            assert isinstance(field.required, bool)

    def test_matches_plugin_manager_count(self, catalog: CatalogServiceImpl, plugin_manager: PluginManager) -> None:
        sources = catalog.list_sources()
        assert len(sources) == len(plugin_manager.get_sources())


class TestListTransforms:
    """list_transforms() returns all registered transform plugins."""

    def test_returns_non_empty_list(self, catalog: CatalogServiceImpl) -> None:
        transforms = catalog.list_transforms()
        assert len(transforms) > 0

    def test_passthrough_present(self, catalog: CatalogServiceImpl) -> None:
        transforms = catalog.list_transforms()
        names = [t.name for t in transforms]
        assert "passthrough" in names

    def test_all_entries_have_transform_type(self, catalog: CatalogServiceImpl) -> None:
        transforms = catalog.list_transforms()
        for t in transforms:
            assert t.plugin_type == "transform"

    def test_matches_plugin_manager_count(self, catalog: CatalogServiceImpl, plugin_manager: PluginManager) -> None:
        transforms = catalog.list_transforms()
        assert len(transforms) == len(plugin_manager.get_transforms())

    def test_no_gates_in_transforms(self, catalog: CatalogServiceImpl) -> None:
        """Gates are config-driven system operations, not plugins (AC6)."""
        transforms = catalog.list_transforms()
        names = {t.name for t in transforms}
        # Gates are not registered in PluginManager.get_transforms(), so they
        # should never appear here. Known gate names for a sanity check:
        gate_names = {"threshold_gate", "routing_gate", "classification_gate"}
        assert names.isdisjoint(gate_names), f"Gates found in transforms: {names & gate_names}"


class TestListSinks:
    """list_sinks() returns all registered sink plugins."""

    def test_returns_non_empty_list(self, catalog: CatalogServiceImpl) -> None:
        sinks = catalog.list_sinks()
        assert len(sinks) > 0

    def test_csv_sink_present(self, catalog: CatalogServiceImpl) -> None:
        sinks = catalog.list_sinks()
        names = [s.name for s in sinks]
        assert "csv" in names

    def test_all_entries_have_sink_type(self, catalog: CatalogServiceImpl) -> None:
        sinks = catalog.list_sinks()
        for s in sinks:
            assert s.plugin_type == "sink"

    def test_matches_plugin_manager_count(self, catalog: CatalogServiceImpl, plugin_manager: PluginManager) -> None:
        sinks = catalog.list_sinks()
        assert len(sinks) == len(plugin_manager.get_sinks())


class TestGetSchema:
    """get_schema() returns full JSON schema for a plugin's config."""

    def test_csv_source_schema(self, catalog: CatalogServiceImpl) -> None:
        info = catalog.get_schema("source", "csv")
        assert isinstance(info, PluginSchemaInfo)
        assert info.name == "csv"
        assert info.plugin_type == "source"
        assert info.description
        assert isinstance(info.json_schema, dict)
        assert "properties" in info.json_schema
        assert info.json_schema["type"] == "object"

    def test_csv_source_schema_matches_model_json_schema(self, catalog: CatalogServiceImpl) -> None:
        """AC2: json_schema output matches model_json_schema() directly."""
        from elspeth.plugins.sources.csv_source import CSVSourceConfig

        info = catalog.get_schema("source", "csv")
        assert info.json_schema == CSVSourceConfig.model_json_schema()

    def test_passthrough_transform_schema(self, catalog: CatalogServiceImpl) -> None:
        info = catalog.get_schema("transform", "passthrough")
        assert info.name == "passthrough"
        assert info.plugin_type == "transform"
        assert isinstance(info.json_schema, dict)

    def test_csv_sink_schema(self, catalog: CatalogServiceImpl) -> None:
        info = catalog.get_schema("sink", "csv")
        assert info.name == "csv"
        assert info.plugin_type == "sink"
        assert isinstance(info.json_schema, dict)

    def test_null_source_returns_empty_schema(self, catalog: CatalogServiceImpl) -> None:
        info = catalog.get_schema("source", "null")
        assert info.name == "null"
        assert info.json_schema == {}

    def test_llm_transform_returns_base_schema(self, catalog: CatalogServiceImpl) -> None:
        info = catalog.get_schema("transform", "llm")
        assert info.name == "llm"
        assert isinstance(info.json_schema, dict)
        if info.json_schema:
            assert "properties" in info.json_schema

    def test_unknown_type_raises_value_error(self, catalog: CatalogServiceImpl) -> None:
        with pytest.raises(ValueError, match="Unknown plugin type"):
            catalog.get_schema("widgets", "csv")

    def test_unknown_name_raises_value_error(self, catalog: CatalogServiceImpl) -> None:
        with pytest.raises(ValueError, match="Unknown source plugin"):
            catalog.get_schema("source", "nonexistent_plugin_xyz")

    def test_unknown_name_includes_available(self, catalog: CatalogServiceImpl) -> None:
        with pytest.raises(ValueError, match="Available:"):
            catalog.get_schema("source", "nonexistent_plugin_xyz")
