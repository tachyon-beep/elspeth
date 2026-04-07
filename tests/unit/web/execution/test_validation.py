"""Tests for dry-run validation using real engine code paths.

Validation calls the actual engine functions: load_settings(),
instantiate_plugins_from_config(), ExecutionGraph.from_plugin_instances(),
graph.validate(). No parallel validation logic exists.

W18 fix: Only typed exceptions are caught — no bare except Exception.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from elspeth.contracts.secrets import ResolvedSecret
from elspeth.core.dag.models import GraphValidationError
from elspeth.web.execution.validation import _collect_secret_refs, validate_pipeline


class FakeSourceSpec:
    """Minimal stand-in for SourceSpec during validation tests."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = options or {}


class FakeNodeSpec:
    """Minimal stand-in for NodeSpec during validation tests."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = options or {}


class FakeOutputSpec:
    """Minimal stand-in for OutputSpec during validation tests."""

    def __init__(self, options: dict[str, Any] | None = None, name: str = "primary") -> None:
        self.name = name
        self.options = options or {}


class FakeCompositionState:
    """Minimal stand-in for CompositionState during validation tests.

    Mimics the typed CompositionState domain object — source is a SourceSpec-like
    object with an .options attribute, not a raw dict.
    """

    def __init__(
        self,
        yaml_content: str = "",
        source_options: dict[str, Any] | None = None,
        nodes: tuple[FakeNodeSpec, ...] | None = None,
        outputs: tuple[FakeOutputSpec, ...] | None = None,
    ) -> None:
        self.yaml_content = yaml_content
        self.source: FakeSourceSpec | None = FakeSourceSpec(source_options) if source_options is not None else None
        self.nodes = nodes or ()
        self.outputs = outputs or ()


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


class TestValidatePipelineSinkPathAllowlist:
    """Sink path allowlist — prevents arbitrary file writes via sink options."""

    def test_sink_path_outside_outputs_blocked(self) -> None:
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="evil_sink", options={"path": "/etc/cron.d/backdoor.csv"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        result = validate_pipeline(state, settings, mock_yaml_gen)
        assert result.is_valid is False
        assert any("Path traversal" in e.message for e in result.errors)
        assert any("evil_sink" in e.message for e in result.errors)

    def test_sink_path_traversal_blocked(self) -> None:
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="tricky", options={"path": "/tmp/test_data/outputs/../../etc/passwd"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        result = validate_pipeline(state, settings, mock_yaml_gen)
        assert result.is_valid is False

    def test_sink_path_under_outputs_passes(self) -> None:
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="primary", options={"path": "/tmp/test_data/outputs/result.csv"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True
        assert "All paths within allowed directories" in path_check.detail

    def test_sink_path_under_blobs_passes(self) -> None:
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="blob_out", options={"path": "/tmp/test_data/blobs/out.json"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True

    def test_sink_without_path_passes(self) -> None:
        """Sinks without path/file options (e.g. database) skip the check."""
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="db_sink", options={"connection_string": "sqlite:///out.db"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True


class TestValidatePipelineRelativePaths:
    """Relative paths must resolve against data_dir, not CWD."""

    def test_relative_sink_path_resolves_against_data_dir(self) -> None:
        """outputs/result.csv should resolve under {data_dir}/outputs/."""
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="primary", options={"path": "outputs/result.csv"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True

    def test_relative_source_path_resolves_against_data_dir(self) -> None:
        """uploads/data.csv should resolve under {data_dir}/uploads/."""
        state = FakeCompositionState(
            source_options={"path": "uploads/data.csv"},
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True

    def test_relative_traversal_still_blocked(self) -> None:
        """../etc/passwd relative to data_dir must still be blocked."""
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="evil", options={"path": "../etc/passwd"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        result = validate_pipeline(state, settings, mock_yaml_gen)
        assert result.is_valid is False
        assert any("Path traversal" in e.message for e in result.errors)

    def test_relative_sink_path_under_blobs(self) -> None:
        """blobs/out.json should resolve under {data_dir}/blobs/."""
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(name="blob_out", options={"path": "blobs/out.json"}),),
        )
        settings = FakeWebSettings(data_dir="/tmp/test_data")
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)
        path_check = next(c for c in result.checks if c.name == "source_path_allowlist")
        assert path_check.passed is True


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
        assert len(result.checks) == 6
        assert all(c.passed for c in result.checks)
        # B11 fix: source_path_allowlist check is always recorded
        assert result.checks[0].name == "source_path_allowlist"
        assert result.checks[0].passed is True
        assert result.checks[1].name == "secret_refs"
        assert result.checks[1].passed is True
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
                    "input": {},
                }
            ],
        )

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 0=path_allowlist, 1=secret_refs, 2=settings_load
        assert result.checks[0].name == "source_path_allowlist"
        assert result.checks[0].passed is True
        assert result.checks[1].name == "secret_refs"
        assert result.checks[1].passed is True
        assert result.checks[2].name == "settings_load"
        assert result.checks[2].passed is False
        # Downstream checks are skipped but recorded
        assert all(not c.passed for c in result.checks[3:])
        assert any("Skipped" in c.detail for c in result.checks[3:])
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
        # B11: index 2 is settings_load (0=path_allowlist, 1=secret_refs)
        assert result.checks[2].passed is False


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
        from elspeth.plugins.infrastructure.manager import PluginNotFoundError

        mock_instantiate.side_effect = PluginNotFoundError("Unknown source plugin: 'unknown'")

        state = FakeCompositionState()
        settings = FakeWebSettings()
        result = validate_pipeline(state, settings, mock_yaml_gen)

        assert result.is_valid is False
        # B11: index 0=path_allowlist, 1=secret_refs, 2=settings_load, 3=plugin_instantiation
        assert result.checks[2].passed is True  # settings_load passed
        assert result.checks[3].passed is False  # plugin_instantiation failed
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
        # B11: index 0=path_allowlist, 1=secret_refs, 2=settings_load, 3=plugins, 4=graph_structure
        assert result.checks[4].passed is False  # graph_structure failed
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
        # B11: index 0=path_allowlist, 1=secret_refs, 2=settings, 3=plugins, 4=graph, 5=schema
        assert result.checks[4].passed is True  # graph_structure passed
        assert result.checks[5].passed is False  # schema_compatibility failed


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


# ── Secret Ref Helpers ────────────────────────────────────────────────


class FakeSecretService:
    """Minimal WebSecretResolver stand-in for validation tests."""

    def __init__(self, available_refs: set[str]) -> None:
        self._available = available_refs

    def list_refs(self, user_id: str) -> list[Any]:
        return []

    def has_ref(self, user_id: str, name: str) -> bool:
        return name in self._available

    def resolve(self, user_id: str, name: str) -> ResolvedSecret | None:
        if name in self._available:
            return ResolvedSecret(name=name, value="fake", scope="user", fingerprint="abc123")
        return None


class TestCollectSecretRefs:
    """Unit tests for _collect_secret_refs helper."""

    def test_empty_dict(self) -> None:
        assert _collect_secret_refs({}) == []

    def test_single_secret_ref(self) -> None:
        assert _collect_secret_refs({"secret_ref": "API_KEY"}) == ["API_KEY"]

    def test_nested_secret_ref(self) -> None:
        data = {"source": {"options": {"api_key": {"secret_ref": "MY_KEY"}}}}
        assert _collect_secret_refs(data) == ["MY_KEY"]

    def test_multiple_refs(self) -> None:
        data = {
            "auth": {"secret_ref": "TOKEN"},
            "db": {"password": {"secret_ref": "DB_PASS"}},
        }
        refs = _collect_secret_refs(data)
        assert sorted(refs) == ["DB_PASS", "TOKEN"]

    def test_list_with_refs(self) -> None:
        data = [{"secret_ref": "A"}, {"secret_ref": "B"}]
        assert _collect_secret_refs(data) == ["A", "B"]

    def test_non_secret_dict(self) -> None:
        data = {"secret_ref": "KEY", "extra": "field"}  # len > 1, not a secret ref
        assert _collect_secret_refs(data) == []

    def test_mapping_proxy_type(self) -> None:
        """Frozen dataclass fields use MappingProxyType — must be walkable."""
        from types import MappingProxyType

        data = MappingProxyType({"api_key": MappingProxyType({"secret_ref": "KEY"})})
        assert _collect_secret_refs(data) == ["KEY"]


class TestValidatePipelineSecretRefs:
    """Secret ref validation check in validate_pipeline()."""

    def test_missing_refs_fail_validation(self) -> None:
        """Validation fails when secret refs can't be resolved."""
        state = FakeCompositionState(
            source_options={"api_key": {"secret_ref": "MISSING_KEY"}},
        )
        settings = FakeWebSettings()
        mock_yaml_gen = MagicMock()
        secret_svc = FakeSecretService(available_refs=set())

        result = validate_pipeline(
            state,
            settings,
            mock_yaml_gen,
            secret_service=secret_svc,
            user_id="user-1",
        )

        assert result.is_valid is False
        secret_check = next(c for c in result.checks if c.name == "secret_refs")
        assert secret_check.passed is False
        assert "MISSING_KEY" in secret_check.detail
        assert any("MISSING_KEY" in e.message for e in result.errors)
        # Downstream checks should be skipped
        assert any("Skipped" in c.detail for c in result.checks if c.name == "settings_load")

    def test_all_refs_present_passes(self) -> None:
        """Validation passes when all secret refs are resolvable."""
        state = FakeCompositionState(
            source_options={"api_key": {"secret_ref": "MY_KEY"}},
        )
        settings = FakeWebSettings()
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        secret_svc = FakeSecretService(available_refs={"MY_KEY"})

        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(
                state,
                settings,
                mock_yaml_gen,
                secret_service=secret_svc,
                user_id="user-1",
            )

        secret_check = next(c for c in result.checks if c.name == "secret_refs")
        assert secret_check.passed is True
        assert "1 secret reference(s) resolved" in secret_check.detail

    def test_no_secret_service_skips_check(self) -> None:
        """Without secret_service, the check is skipped (passed=True)."""
        state = FakeCompositionState(
            source_options={"api_key": {"secret_ref": "KEY"}},
        )
        settings = FakeWebSettings()
        mock_yaml_gen = MagicMock()
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"

        with patch("elspeth.web.execution.validation.load_settings") as mock_load:
            mock_load.side_effect = FileNotFoundError("no temp file")
            result = validate_pipeline(state, settings, mock_yaml_gen)

        secret_check = next(c for c in result.checks if c.name == "secret_refs")
        assert secret_check.passed is True
        assert "skipped" in secret_check.detail.lower()

    def test_refs_in_node_options_detected(self) -> None:
        """Secret refs in node options are found and validated."""
        state = FakeCompositionState(
            source_options={},
            nodes=(FakeNodeSpec(options={"token": {"secret_ref": "NODE_TOKEN"}}),),
        )
        settings = FakeWebSettings()
        mock_yaml_gen = MagicMock()
        secret_svc = FakeSecretService(available_refs=set())

        result = validate_pipeline(
            state,
            settings,
            mock_yaml_gen,
            secret_service=secret_svc,
            user_id="user-1",
        )

        assert result.is_valid is False
        assert any("NODE_TOKEN" in e.message for e in result.errors)

    def test_refs_in_output_options_detected(self) -> None:
        """Secret refs in output options are found and validated."""
        state = FakeCompositionState(
            source_options={},
            outputs=(FakeOutputSpec(options={"password": {"secret_ref": "DB_PASS"}}),),
        )
        settings = FakeWebSettings()
        mock_yaml_gen = MagicMock()
        secret_svc = FakeSecretService(available_refs=set())

        result = validate_pipeline(
            state,
            settings,
            mock_yaml_gen,
            secret_service=secret_svc,
            user_id="user-1",
        )

        assert result.is_valid is False
        assert any("DB_PASS" in e.message for e in result.errors)

    def test_multiple_missing_refs_listed(self) -> None:
        """All missing refs are collected and reported at once."""
        state = FakeCompositionState(
            source_options={
                "key1": {"secret_ref": "REF_A"},
                "key2": {"secret_ref": "REF_B"},
            },
        )
        settings = FakeWebSettings()
        mock_yaml_gen = MagicMock()
        secret_svc = FakeSecretService(available_refs={"REF_A"})  # REF_B missing

        result = validate_pipeline(
            state,
            settings,
            mock_yaml_gen,
            secret_service=secret_svc,
            user_id="user-1",
        )

        assert result.is_valid is False
        secret_check = next(c for c in result.checks if c.name == "secret_refs")
        assert "REF_B" in secret_check.detail
        assert "REF_A" not in secret_check.detail  # REF_A resolved fine
