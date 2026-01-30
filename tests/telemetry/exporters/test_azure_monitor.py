# tests/telemetry/exporters/test_azure_monitor.py
"""Tests for Azure Monitor telemetry exporter.

Tests cover:
- Configuration validation (connection_string required, batch_size > 0)
- Event buffering and batch export
- Event-to-span conversion with Azure-specific attributes
- Attribute serialization (datetime, enum, dict, tuple handling)
- Flush and close lifecycle
- Error handling (export failures don't crash pipeline)

Note: The Azure Monitor SDK is an optional dependency. These tests mock the SDK
to allow running without installing the azure-monitor-opentelemetry-exporter package.
"""

import sys
from datetime import UTC, datetime
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from elspeth.contracts import TokenCompleted
from elspeth.contracts.enums import RowOutcome, RunStatus
from elspeth.telemetry.errors import TelemetryExporterError
from elspeth.telemetry.events import (
    RunFinished,
    RunStarted,
)

# Global mock for the Azure Monitor exporter class
_mock_azure_exporter_class: MagicMock | None = None


def _setup_azure_mock() -> MagicMock:
    """Set up mock for azure.monitor.opentelemetry.exporter module.

    Returns the mock AzureMonitorTraceExporter class.
    """
    global _mock_azure_exporter_class

    # Create mock exporter class
    _mock_azure_exporter_class = MagicMock()
    mock_instance = MagicMock()
    _mock_azure_exporter_class.return_value = mock_instance

    # Create mock module
    mock_module = ModuleType("azure.monitor.opentelemetry.exporter")
    mock_module.AzureMonitorTraceExporter = _mock_azure_exporter_class  # type: ignore[attr-defined]

    # Set up module hierarchy
    if "azure" not in sys.modules:
        azure_mock = ModuleType("azure")
        sys.modules["azure"] = azure_mock

    if "azure.monitor" not in sys.modules:
        monitor_mock = ModuleType("azure.monitor")
        sys.modules["azure.monitor"] = monitor_mock

    if "azure.monitor.opentelemetry" not in sys.modules:
        opentelemetry_mock = ModuleType("azure.monitor.opentelemetry")
        sys.modules["azure.monitor.opentelemetry"] = opentelemetry_mock

    sys.modules["azure.monitor.opentelemetry.exporter"] = mock_module

    return _mock_azure_exporter_class


# Set up the mock before importing the exporter
_setup_azure_mock()

# Now we can import the exporter (it will use our mocked module)
from elspeth.telemetry.exporters.azure_monitor import AzureMonitorExporter  # noqa: E402


def _get_mock_sdk_instance() -> MagicMock:
    """Get the current mock SDK instance."""
    assert _mock_azure_exporter_class is not None
    return _mock_azure_exporter_class.return_value


def _reset_mock() -> None:
    """Reset mock call history for a fresh test."""
    assert _mock_azure_exporter_class is not None
    _mock_azure_exporter_class.reset_mock()


@pytest.fixture(autouse=True)
def reset_mock_per_test():
    """Reset mock before each test."""
    _reset_mock()
    yield


class TestAzureMonitorExporterConfiguration:
    """Tests for AzureMonitorExporter configuration."""

    def test_name_property(self) -> None:
        """Exporter name is 'azure_monitor'."""
        exporter = AzureMonitorExporter()
        assert exporter.name == "azure_monitor"

    def test_missing_connection_string_raises(self) -> None:
        """Configuration without connection_string raises TelemetryExporterError."""
        exporter = AzureMonitorExporter()
        with pytest.raises(TelemetryExporterError) as exc_info:
            exporter.configure({})
        assert "connection_string" in str(exc_info.value)

    def test_empty_connection_string_accepted(self) -> None:
        """Empty string connection_string is accepted (SDK will fail later)."""
        exporter = AzureMonitorExporter()
        exporter.configure({"connection_string": ""})
        assert _mock_azure_exporter_class is not None
        _mock_azure_exporter_class.assert_called_once()

    def test_invalid_batch_size_raises(self) -> None:
        """batch_size < 1 raises TelemetryExporterError."""
        exporter = AzureMonitorExporter()
        with pytest.raises(TelemetryExporterError) as exc_info:
            exporter.configure({"connection_string": "InstrumentationKey=...", "batch_size": 0})
        assert "batch_size" in str(exc_info.value)

    def test_negative_batch_size_raises(self) -> None:
        """Negative batch_size raises TelemetryExporterError."""
        exporter = AzureMonitorExporter()
        with pytest.raises(TelemetryExporterError) as exc_info:
            exporter.configure({"connection_string": "InstrumentationKey=...", "batch_size": -5})
        assert "batch_size" in str(exc_info.value)

    def test_valid_configuration(self) -> None:
        """Valid configuration initializes exporter."""
        exporter = AzureMonitorExporter()

        connection_string = (
            "InstrumentationKey=00000000-0000-0000-0000-000000000000;IngestionEndpoint=https://example.in.applicationinsights.azure.com/"
        )
        exporter.configure(
            {
                "connection_string": connection_string,
                "batch_size": 50,
            }
        )

        assert _mock_azure_exporter_class is not None
        _mock_azure_exporter_class.assert_called_once_with(
            connection_string=connection_string,
        )

    def test_default_batch_size(self) -> None:
        """Default batch_size is 100."""
        exporter = AzureMonitorExporter()
        exporter.configure({"connection_string": "InstrumentationKey=..."})
        assert exporter._batch_size == 100

    def test_connection_string_wrong_type_raises(self) -> None:
        """Non-string connection_string raises TelemetryExporterError with clear message."""
        exporter = AzureMonitorExporter()
        with pytest.raises(TelemetryExporterError) as exc_info:
            exporter.configure({"connection_string": 12345})
        assert "'connection_string' must be a string" in str(exc_info.value)
        assert "int" in str(exc_info.value)

    def test_batch_size_wrong_type_raises(self) -> None:
        """Non-int batch_size raises TelemetryExporterError with clear message."""
        exporter = AzureMonitorExporter()
        with pytest.raises(TelemetryExporterError) as exc_info:
            exporter.configure({"connection_string": "InstrumentationKey=...", "batch_size": "100"})
        assert "'batch_size' must be an integer" in str(exc_info.value)
        assert "str" in str(exc_info.value)


class TestAzureMonitorExporterBuffering:
    """Tests for event buffering and batch export."""

    def _create_configured_exporter(self, batch_size: int = 100) -> tuple[AzureMonitorExporter, MagicMock]:
        """Create a configured exporter with mocked Azure SDK."""
        _reset_mock()
        exporter = AzureMonitorExporter()
        exporter.configure(
            {
                "connection_string": "InstrumentationKey=...",
                "batch_size": batch_size,
            }
        )
        return exporter, _get_mock_sdk_instance()

    def test_events_buffered_until_batch_size(self) -> None:
        """Events are buffered until batch_size is reached."""
        exporter, mock_sdk = self._create_configured_exporter(batch_size=3)

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )

        # First two events: buffered, not exported
        exporter.export(event)
        exporter.export(event)
        mock_sdk.export.assert_not_called()
        assert len(exporter._buffer) == 2

        # Third event: triggers batch export
        exporter.export(event)
        mock_sdk.export.assert_called_once()
        assert len(exporter._buffer) == 0

    def test_flush_exports_partial_batch(self) -> None:
        """flush() exports buffered events even if batch_size not reached."""
        exporter, mock_sdk = self._create_configured_exporter(batch_size=100)

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )

        exporter.export(event)
        exporter.export(event)
        mock_sdk.export.assert_not_called()

        exporter.flush()
        mock_sdk.export.assert_called_once()
        # Verify 2 spans were exported
        exported_spans = mock_sdk.export.call_args[0][0]
        assert len(exported_spans) == 2

    def test_flush_is_noop_when_buffer_empty(self) -> None:
        """flush() is a no-op when buffer is empty."""
        exporter, mock_sdk = self._create_configured_exporter()
        exporter.flush()
        mock_sdk.export.assert_not_called()

    def test_export_without_configure_logs_warning(self) -> None:
        """export() without configure() logs warning and continues."""
        exporter = AzureMonitorExporter()
        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )

        # Should not raise
        exporter.export(event)
        # Buffer should be empty (not configured)
        assert len(exporter._buffer) == 0


class TestAzureMonitorExporterSpanConversion:
    """Tests for event-to-span conversion."""

    def _create_configured_exporter(self) -> tuple[AzureMonitorExporter, MagicMock]:
        """Create a configured exporter with mocked Azure SDK."""
        _reset_mock()
        exporter = AzureMonitorExporter()
        exporter.configure(
            {
                "connection_string": "InstrumentationKey=...",
                "batch_size": 1,  # Export immediately for testing
            }
        )
        return exporter, _get_mock_sdk_instance()

    def test_span_name_is_event_class_name(self) -> None:
        """Span name is the event class name."""
        exporter, mock_sdk = self._create_configured_exporter()

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        assert exported_spans[0].name == "RunStarted"

    def test_span_has_azure_specific_attributes(self) -> None:
        """Span includes Azure-specific attributes for filtering."""
        exporter, mock_sdk = self._create_configured_exporter()

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes

        # Azure-specific attributes
        assert attrs["cloud.provider"] == "azure"
        assert attrs["elspeth.exporter"] == "azure_monitor"

    def test_span_trace_id_derived_from_run_id(self) -> None:
        """Span trace_id is derived from run_id (consistent with OTLP)."""
        from elspeth.telemetry.exporters.otlp import _derive_trace_id

        exporter, mock_sdk = self._create_configured_exporter()

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        expected_trace_id = _derive_trace_id("run-123")
        assert exported_spans[0].context.trace_id == expected_trace_id

    def test_span_attributes_contain_event_fields(self) -> None:
        """Span attributes contain all event fields."""
        exporter, mock_sdk = self._create_configured_exporter()

        event = RunStarted(
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            run_id="run-123",
            config_hash="abc123",
            source_plugin="csv_source",
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes

        assert attrs["run_id"] == "run-123"
        assert attrs["config_hash"] == "abc123"
        assert attrs["source_plugin"] == "csv_source"
        assert attrs["event_type"] == "RunStarted"

    def test_datetime_serialized_as_iso8601(self) -> None:
        """datetime fields are serialized as ISO 8601 strings."""
        exporter, mock_sdk = self._create_configured_exporter()

        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        event = RunStarted(
            timestamp=ts,
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes
        assert attrs["timestamp"] == "2024-01-15T10:30:00+00:00"

    def test_enum_serialized_as_value(self) -> None:
        """Enum fields are serialized as their string values."""
        exporter, mock_sdk = self._create_configured_exporter()

        event = RunFinished(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            status=RunStatus.COMPLETED,
            row_count=100,
            duration_ms=5000.0,
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes
        assert attrs["status"] == "completed"

    def test_tuple_serialized_as_list(self) -> None:
        """Tuple fields are serialized as lists."""
        exporter, mock_sdk = self._create_configured_exporter()

        from elspeth.contracts import GateEvaluated
        from elspeth.contracts.enums import RoutingMode

        event = GateEvaluated(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            row_id="row-1",
            token_id="token-1",
            node_id="gate-1",
            plugin_name="threshold_gate",
            routing_mode=RoutingMode.MOVE,
            destinations=("sink_a", "sink_b"),
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes
        assert attrs["destinations"] == ["sink_a", "sink_b"]

    def test_none_fields_omitted(self) -> None:
        """None fields are omitted from attributes."""
        exporter, mock_sdk = self._create_configured_exporter()

        event = TokenCompleted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            row_id="row-1",
            token_id="token-1",
            outcome=RowOutcome.FAILED,
            sink_name=None,
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes
        assert "sink_name" not in attrs

    def test_dict_serialized_as_json(self) -> None:
        """Dict fields are serialized as JSON strings (Azure Monitor limitation)."""
        exporter, mock_sdk = self._create_configured_exporter()

        from elspeth.contracts.enums import CallStatus, CallType
        from elspeth.telemetry.events import ExternalCallCompleted

        event = ExternalCallCompleted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            state_id="state-1",
            call_type=CallType.LLM,
            provider="azure-openai",
            status=CallStatus.SUCCESS,
            latency_ms=150.0,
            token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        )
        exporter.export(event)

        exported_spans = mock_sdk.export.call_args[0][0]
        attrs = exported_spans[0].attributes
        # Dict should be JSON string
        import json

        token_usage = json.loads(attrs["token_usage"])
        assert token_usage == {"prompt_tokens": 100, "completion_tokens": 50}


class TestAzureMonitorExporterLifecycle:
    """Tests for exporter lifecycle (close, error handling)."""

    def _create_configured_exporter(self) -> tuple[AzureMonitorExporter, MagicMock]:
        """Create a configured exporter with mocked Azure SDK."""
        _reset_mock()
        exporter = AzureMonitorExporter()
        exporter.configure(
            {
                "connection_string": "InstrumentationKey=...",
                "batch_size": 100,
            }
        )
        return exporter, _get_mock_sdk_instance()

    def test_close_flushes_buffer(self) -> None:
        """close() flushes any remaining buffered events."""
        exporter, mock_sdk = self._create_configured_exporter()

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )
        exporter.export(event)

        exporter.close()
        mock_sdk.export.assert_called_once()

    def test_close_shuts_down_sdk_exporter(self) -> None:
        """close() calls shutdown on the underlying SDK exporter."""
        exporter, mock_sdk = self._create_configured_exporter()
        exporter.close()
        mock_sdk.shutdown.assert_called_once()

    def test_close_is_idempotent(self) -> None:
        """close() can be called multiple times safely."""
        exporter, mock_sdk = self._create_configured_exporter()
        exporter.close()
        exporter.close()  # Should not raise
        # shutdown called only once (exporter set to None after first close)
        mock_sdk.shutdown.assert_called_once()

    def test_export_failure_does_not_raise(self) -> None:
        """Export failures are logged but don't raise exceptions."""
        exporter, mock_sdk = self._create_configured_exporter()
        mock_sdk.export.side_effect = Exception("Network error")

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )

        # Should not raise even with batch_size=1 (immediate export)
        exporter._batch_size = 1
        exporter.export(event)  # Triggers export which fails
        # Buffer should be cleared despite failure
        assert len(exporter._buffer) == 0

    def test_flush_failure_does_not_raise(self) -> None:
        """flush() failures are logged but don't raise exceptions."""
        exporter, mock_sdk = self._create_configured_exporter()
        mock_sdk.export.side_effect = Exception("Network error")

        event = RunStarted(
            timestamp=datetime.now(UTC),
            run_id="run-123",
            config_hash="abc",
            source_plugin="csv",
        )
        exporter.export(event)

        # Should not raise
        exporter.flush()

    def test_close_failure_does_not_raise(self) -> None:
        """close() shutdown failures are logged but don't raise."""
        exporter, mock_sdk = self._create_configured_exporter()
        mock_sdk.shutdown.side_effect = Exception("Shutdown error")

        # Should not raise
        exporter.close()


class TestAzureMonitorExporterRegistration:
    """Tests for plugin registration."""

    def test_exporter_in_builtin_plugin(self) -> None:
        """AzureMonitorExporter is registered in BuiltinExportersPlugin."""
        from elspeth.telemetry.exporters import AzureMonitorExporter, BuiltinExportersPlugin

        plugin = BuiltinExportersPlugin()
        exporters = plugin.elspeth_get_exporters()
        assert AzureMonitorExporter in exporters

    def test_exporter_in_package_all(self) -> None:
        """AzureMonitorExporter is exported from package __all__."""
        from elspeth.telemetry import exporters

        assert "AzureMonitorExporter" in exporters.__all__


class TestAzureMonitorProtocolCompliance:
    """Tests verifying ExporterProtocol compliance."""

    def test_implements_exporter_protocol(self) -> None:
        """AzureMonitorExporter implements ExporterProtocol."""
        from elspeth.telemetry.protocols import ExporterProtocol

        exporter = AzureMonitorExporter()
        assert isinstance(exporter, ExporterProtocol)

    def test_name_property_is_string(self) -> None:
        """name property returns a non-empty string."""
        exporter = AzureMonitorExporter()
        assert isinstance(exporter.name, str)
        assert len(exporter.name) > 0

    def test_all_protocol_methods_exist(self) -> None:
        """All protocol methods exist and are callable."""
        exporter = AzureMonitorExporter()

        # These should exist and be callable
        assert callable(exporter.configure)
        assert callable(exporter.export)
        assert callable(exporter.flush)
        assert callable(exporter.close)
