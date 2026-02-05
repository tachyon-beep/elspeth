# tests/plugins/sinks/test_sink_protocol_compliance.py
"""Protocol compliance tests for sink plugins.

All sink plugins must implement SinkProtocol and satisfy its contract.
This test suite verifies protocol compliance for all built-in sinks.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

from elspeth.contracts import ArtifactDescriptor

# Schema configs for tests
# CSV and Database sinks require fixed columns (strict mode)
# JSON sink accepts dynamic schemas
STRICT_SCHEMA = {"mode": "fixed", "fields": ["id: int"]}
DYNAMIC_SCHEMA = {"mode": "observed"}

# Sink configurations for parametrized testing
SINK_CONFIGS = [
    pytest.param(
        "elspeth.plugins.sinks.csv_sink.CSVSink",
        {"path": "/tmp/test.csv", "schema": STRICT_SCHEMA},  # CSV requires strict
        "csv",
        id="csv",
    ),
    pytest.param(
        "elspeth.plugins.sinks.json_sink.JSONSink",
        {"path": "/tmp/test.json", "schema": DYNAMIC_SCHEMA},  # JSON accepts dynamic
        "json",
        id="json",
    ),
    pytest.param(
        "elspeth.plugins.sinks.database_sink.DatabaseSink",
        {"url": "sqlite:///:memory:", "table": "test", "schema": STRICT_SCHEMA},  # Database requires strict
        "database",
        id="database",
    ),
]


def _import_sink_class(class_path: str) -> type:
    """Import a sink class from its fully qualified path."""
    module_path, class_name = class_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls: type = getattr(module, class_name)
    return cls


class TestSinkProtocolCompliance:
    """Parametrized protocol compliance tests for all sink plugins."""

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_has_required_class_attributes(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have name class attribute."""
        sink_class = _import_sink_class(class_path)
        # Direct attribute access - crash on missing (our code, our bug)
        assert sink_class.name == expected_name  # type: ignore[attr-defined]

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_has_required_instance_attributes(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have input_schema, idempotent, supports_resume attributes after instantiation."""
        sink_class = _import_sink_class(class_path)
        sink = sink_class(config)

        # Direct attribute access - crash on missing (our code, our bug)
        _ = sink.input_schema  # Verify attribute exists
        _ = sink.idempotent  # Verify attribute exists
        _ = sink.supports_resume  # Verify attribute exists
        _ = sink.determinism  # Verify attribute exists
        _ = sink.plugin_version  # Verify attribute exists
        _ = sink.config  # Verify attribute exists

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_write_method_returns_artifact_descriptor(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have write() method that returns ArtifactDescriptor."""
        sink_class = _import_sink_class(class_path)
        sink = sink_class(config)

        # Create mock context
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        # Call write with empty list (should not crash)
        result = sink.write([], mock_ctx)

        # Verify return type - direct attribute access, crash on wrong type
        assert isinstance(result, ArtifactDescriptor), f"write() must return ArtifactDescriptor, got {type(result)}"
        # Verify required fields exist (our code, crash on missing)
        _ = result.content_hash
        _ = result.size_bytes

        # Clean up
        sink.close()

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_flush_method_callable(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have callable flush() method."""
        sink_class = _import_sink_class(class_path)
        sink = sink_class(config)

        # Direct method call - crash on missing (our code, our bug)
        sink.flush()  # Should not raise

        # Clean up
        sink.close()

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_close_method_callable_and_idempotent(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have callable close() method that is idempotent."""
        sink_class = _import_sink_class(class_path)
        sink = sink_class(config)

        # Direct method call - crash on missing (our code, our bug)
        sink.close()  # First close
        sink.close()  # Second close - should not raise (idempotency)

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_lifecycle_hooks_exist(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have on_start() and on_complete() lifecycle hooks."""
        sink_class = _import_sink_class(class_path)
        sink = sink_class(config)

        # Create mock context
        mock_ctx = MagicMock()
        mock_ctx.run_id = "test-run"

        # Direct method calls - crash on missing (our code, our bug)
        sink.on_start(mock_ctx)  # Should not raise
        sink.on_complete(mock_ctx)  # Should not raise

        # Clean up
        sink.close()

    @pytest.mark.parametrize("class_path,config,expected_name", SINK_CONFIGS)
    def test_resume_methods_exist(self, class_path: str, config: dict[str, Any], expected_name: str) -> None:
        """All sinks must have configure_for_resume() and validate_output_target() methods."""
        sink_class = _import_sink_class(class_path)
        sink = sink_class(config)

        # Direct attribute access - crash on missing (our code, our bug)
        supports_resume = sink.supports_resume

        # configure_for_resume() should only be called if sink supports resume
        # Sinks that don't support resume may raise NotImplementedError
        if supports_resume:
            sink.configure_for_resume()  # Should not raise for resumable sinks

        # validate_output_target() should always be callable
        result = sink.validate_output_target()  # Should not raise

        # Verify return value has expected structure
        _ = result.valid  # Crash if missing field (our code, our bug)

        # Clean up
        sink.close()
