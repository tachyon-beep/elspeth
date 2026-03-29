"""Tests for dry-run validation using real engine code paths.

Validation calls the actual engine functions: load_settings(),
instantiate_plugins_from_config(), ExecutionGraph.from_plugin_instances(),
graph.validate(). No parallel validation logic exists.

W18 fix: Only typed exceptions are caught — no bare except Exception.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from elspeth.core.dag.models import GraphValidationError
from elspeth.web.execution.validation import validate_pipeline


class FakeSourceSpec:
    """Minimal stand-in for SourceSpec during validation tests."""

    def __init__(self, options: dict | None = None) -> None:
        self.options = options or {}


class FakeCompositionState:
    """Minimal stand-in for CompositionState during validation tests.

    Mimics the typed CompositionState domain object — source is a SourceSpec-like
    object with an .options attribute, not a raw dict.
    """

    def __init__(self, yaml_content: str = "", source_options: dict | None = None) -> None:
        self.yaml_content = yaml_content
        self.source: FakeSourceSpec | None = FakeSourceSpec(source_options) if source_options is not None else None


class FakeWebSettings:
    """Minimal stand-in for WebSettings during validation tests."""

    def __init__(self, data_dir: str = "/tmp/test_data") -> None:
        self.data_dir = data_dir


class TestValidatePipelinePathAllowlist:
    """C3/S2: Source path allowlist check — defense-in-depth."""

    def test_path_within_uploads_passes(self) -> None:
        state = FakeCompositionState(
            source_options={"path": "/tmp/test_data/uploads/data.csv"},
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        # B11: path check is always recorded — verify it passed
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True

    def test_path_outside_uploads_blocked(self) -> None:
        state = FakeCompositionState(
            source_options={"path": "/etc/passwd"},
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        result = validate_pipeline(state, settings, mock_yaml_gen)
        assert result.is_valid is False
        assert result.checks[0].name == "source_path_allowlist"
        assert result.checks[0].passed is False
        assert any("Path traversal" in e.message for e in result.errors)

    def test_path_traversal_via_dotdot_blocked(self) -> None:
        state = FakeCompositionState(
            source_options={"path": "/tmp/test_data/uploads/../../secret.csv"},
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        result = validate_pipeline(state, settings, mock_yaml_gen)
        assert result.is_valid is False

    def test_no_path_option_records_skipped_check(self) -> None:
        """B11 fix: path allowlist check is always recorded, even when skipped."""
        state = FakeCompositionState(source_options={})
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        # B11: check IS recorded with passed=True and "skipped" detail
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True
        assert "skipped" in path_check.detail.lower()


class TestValidatePipelineSuccess:
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_valid_pipeline_returns_all_checks_passed(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle

        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is True
        assert len(result.checks) == 5
        assert all(c.passed for c in result.checks)
        # B11 fix: source_path_allowlist check is always recorded
        assert result.checks[0].name == "source_path_allowlist"
        assert result.checks[0].passed is True
        assert result.errors == []

        # Verify real engine functions were called
        mock_load.assert_called_once()
        mock_instantiate.assert_called_once_with(mock_settings)
        mock_graph_cls.from_plugin_instances.assert_called_once()
        mock_graph.validate.assert_called_once()
        mock_graph.validate_edge_compatibility.assert_called_once()


class TestValidatePipelineSettingsFailure:
    @patch("elspeth.web.execution.validation.load_settings")
    def test_pydantic_validation_error_short_circuits(
        self,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "bad: yaml"
        # Note: from_exception_data() is a Pydantic v2 internal API. If this breaks
        # on a Pydantic upgrade, replace with: `ElspethSettings(bad_field="x")` to
        # trigger a real PydanticValidationError.
        mock_load.side_effect = PydanticValidationError.from_exception_data(
            title="ElspethSettings",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("source",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        )

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 0 is source_path_allowlist (passed), index 1 is settings_load
        assert result.checks[0].name == "source_path_allowlist"
        assert result.checks[0].passed is True
        assert result.checks[1].name == "settings_load"
        assert result.checks[1].passed is False
        # Downstream checks are skipped but recorded
        assert all(not c.passed for c in result.checks[2:])
        assert any("Skipped" in c.detail for c in result.checks[2:])
        assert len(result.errors) >= 1

    @patch("elspeth.web.execution.validation.load_settings")
    def test_file_not_found_error_from_settings(
        self,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source: {}"
        mock_load.side_effect = FileNotFoundError("temp file missing")

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 1 is settings_load (index 0 is source_path_allowlist)
        assert result.checks[1].passed is False


class TestValidatePipelinePluginFailure:
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    def test_unknown_plugin_returns_attributed_error(
        self,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: unknown"
        mock_load.return_value = MagicMock()
        mock_instantiate.side_effect = ValueError("Unknown source plugin: 'unknown'")

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 0=path_allowlist, 1=settings_load, 2=plugin_instantiation
        assert result.checks[1].passed is True  # settings_load passed
        assert result.checks[2].passed is False  # plugin_instantiation failed
        assert any("unknown" in e.message.lower() for e in result.errors)


class TestValidatePipelineGraphFailure:
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_graph_validation_error_attributed_to_node(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_load.return_value = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle

        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph
        mock_graph.validate.side_effect = GraphValidationError("Route destination 'nonexistent' in gate_1 not found")

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 0=path_allowlist, 1=settings_load, 2=plugins, 3=graph_structure
        assert result.checks[3].passed is False  # graph_structure failed
        assert len(result.errors) >= 1

    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_edge_compatibility_error(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_load.return_value = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle

        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph
        mock_graph.validate.return_value = None  # structural check passes
        mock_graph.validate_edge_compatibility.side_effect = GraphValidationError("Schema mismatch on edge transform_1 -> sink_primary")

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 0=path_allowlist, 1=settings, 2=plugins, 3=graph, 4=schema
        assert result.checks[3].passed is True  # graph_structure passed
        assert result.checks[4].passed is False  # schema_compatibility failed


class TestValidatePipelineNoBareCatch:
    """W18 fix: unexpected exceptions propagate — no bare except Exception."""

    @patch("elspeth.web.execution.validation.load_settings")
    def test_unexpected_exception_propagates(
        self,
        mock_load: MagicMock,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_load.side_effect = RuntimeError("Unexpected engine bug")

        state = FakeCompositionState()
        settings = FakeWebSettings()
        # RuntimeError is NOT in the typed exception list — it must propagate
        with pytest.raises(RuntimeError, match="Unexpected engine bug"):
            validate_pipeline(state, settings, mock_yaml_gen)


class TestValidatePipelineTempFileCleanup:
    """Verify temp file is created and cleaned up in finally block."""

    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_temp_file_cleaned_up_on_success(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle
        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph

        state = FakeCompositionState()
        settings = FakeWebSettings()
        validate_pipeline(state, settings, mock_yaml_gen)

        # load_settings was called with a Path, not YAML content
        call_args = mock_load.call_args
        arg = call_args[0][0] if call_args[0] else call_args[1].get("config_path")
        assert isinstance(arg, Path)

        # The temp file should have been cleaned up
        assert not arg.exists()
