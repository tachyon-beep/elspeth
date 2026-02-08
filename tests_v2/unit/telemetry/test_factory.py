"""Tests for telemetry.factory -- TelemetryManager creation from config."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts.config.runtime import ExporterConfig, RuntimeTelemetryConfig
from elspeth.contracts.enums import BackpressureMode, TelemetryGranularity
from elspeth.telemetry.errors import TelemetryExporterError
from elspeth.telemetry.exporters import (
    AzureMonitorExporter,
    ConsoleExporter,
    DatadogExporter,
    OTLPExporter,
)
from elspeth.telemetry.factory import _EXPORTER_REGISTRY, create_telemetry_manager
from elspeth.telemetry.manager import TelemetryManager


def _make_config(
    *,
    enabled: bool = True,
    exporter_configs: tuple[ExporterConfig, ...] = (),
) -> RuntimeTelemetryConfig:
    return RuntimeTelemetryConfig(
        enabled=enabled,
        granularity=TelemetryGranularity.FULL,
        backpressure_mode=BackpressureMode.DROP,
        fail_on_total_exporter_failure=False,
        exporter_configs=exporter_configs,
    )


class TestCreateTelemetryManagerDisabled:
    def test_disabled_returns_none(self):
        config = _make_config(enabled=False)
        result = create_telemetry_manager(config)
        assert result is None

    def test_disabled_with_exporters_still_returns_none(self):
        config = _make_config(
            enabled=False,
            exporter_configs=(ExporterConfig(name="console", options={}),),
        )
        result = create_telemetry_manager(config)
        assert result is None

    def test_disabled_does_not_instantiate_exporters(self):
        config = _make_config(
            enabled=False,
            exporter_configs=(ExporterConfig(name="console", options={}),),
        )
        with patch.dict(_EXPORTER_REGISTRY, {"console": MagicMock()}) as mock_registry:
            result = create_telemetry_manager(config)
            assert result is None
            mock_registry["console"].assert_not_called()


class TestCreateTelemetryManagerEnabled:
    def test_enabled_no_exporters_returns_manager(self):
        config = _make_config(enabled=True, exporter_configs=())
        manager = create_telemetry_manager(config)
        try:
            assert manager is not None
            assert isinstance(manager, TelemetryManager)
        finally:
            if manager is not None:
                manager.close()

    def test_enabled_with_console_exporter(self):
        config = _make_config(
            enabled=True,
            exporter_configs=(ExporterConfig(name="console", options={}),),
        )
        manager = create_telemetry_manager(config)
        try:
            assert manager is not None
            assert isinstance(manager, TelemetryManager)
        finally:
            if manager is not None:
                manager.close()

    def test_enabled_with_console_exporter_and_options(self):
        config = _make_config(
            enabled=True,
            exporter_configs=(
                ExporterConfig(name="console", options={"format": "pretty", "output": "stderr"}),
            ),
        )
        manager = create_telemetry_manager(config)
        try:
            assert manager is not None
            assert isinstance(manager, TelemetryManager)
        finally:
            if manager is not None:
                manager.close()

    def test_exporter_configure_called_with_options(self):
        mock_exporter = MagicMock()
        mock_class = MagicMock(return_value=mock_exporter)
        options = {"endpoint": "http://localhost:4317"}

        with patch.dict(_EXPORTER_REGISTRY, {"mock_exp": mock_class}):
            config = _make_config(
                enabled=True,
                exporter_configs=(ExporterConfig(name="mock_exp", options=options),),
            )
            manager = create_telemetry_manager(config)
            try:
                assert manager is not None
                mock_class.assert_called_once()
                mock_exporter.configure.assert_called_once_with(options)
            finally:
                if manager is not None:
                    manager.close()

    def test_exporter_configure_called_with_empty_options(self):
        mock_exporter = MagicMock()
        mock_class = MagicMock(return_value=mock_exporter)

        with patch.dict(_EXPORTER_REGISTRY, {"mock_exp": mock_class}):
            config = _make_config(
                enabled=True,
                exporter_configs=(ExporterConfig(name="mock_exp", options={}),),
            )
            manager = create_telemetry_manager(config)
            try:
                assert manager is not None
                mock_exporter.configure.assert_called_once_with({})
            finally:
                if manager is not None:
                    manager.close()

    def test_multiple_exporters_all_configured(self):
        mock_exporter_a = MagicMock()
        mock_class_a = MagicMock(return_value=mock_exporter_a)
        mock_exporter_b = MagicMock()
        mock_class_b = MagicMock(return_value=mock_exporter_b)

        with patch.dict(
            _EXPORTER_REGISTRY,
            {"exp_a": mock_class_a, "exp_b": mock_class_b},
        ):
            config = _make_config(
                enabled=True,
                exporter_configs=(
                    ExporterConfig(name="exp_a", options={"key": "val_a"}),
                    ExporterConfig(name="exp_b", options={"key": "val_b"}),
                ),
            )
            manager = create_telemetry_manager(config)
            try:
                assert manager is not None
                mock_class_a.assert_called_once()
                mock_class_b.assert_called_once()
                mock_exporter_a.configure.assert_called_once_with({"key": "val_a"})
                mock_exporter_b.configure.assert_called_once_with({"key": "val_b"})
            finally:
                if manager is not None:
                    manager.close()

    def test_exporters_instantiated_in_order(self):
        call_order: list[str] = []

        def make_mock(label: str) -> MagicMock:
            m = MagicMock()
            m.configure.side_effect = lambda _opts: call_order.append(label)
            return m

        mock_a = make_mock("first")
        mock_b = make_mock("second")
        mock_c = make_mock("third")

        with patch.dict(
            _EXPORTER_REGISTRY,
            {"ea": MagicMock(return_value=mock_a), "eb": MagicMock(return_value=mock_b), "ec": MagicMock(return_value=mock_c)},
        ):
            config = _make_config(
                enabled=True,
                exporter_configs=(
                    ExporterConfig(name="ea", options={}),
                    ExporterConfig(name="eb", options={}),
                    ExporterConfig(name="ec", options={}),
                ),
            )
            manager = create_telemetry_manager(config)
            try:
                assert call_order == ["first", "second", "third"]
            finally:
                if manager is not None:
                    manager.close()

    def test_returned_manager_receives_config(self):
        mock_exporter = MagicMock()
        mock_class = MagicMock(return_value=mock_exporter)

        with patch.dict(_EXPORTER_REGISTRY, {"mock_exp": mock_class}):
            config = _make_config(
                enabled=True,
                exporter_configs=(ExporterConfig(name="mock_exp", options={}),),
            )
            manager = create_telemetry_manager(config)
            try:
                assert manager is not None
                assert manager._config is config
            finally:
                if manager is not None:
                    manager.close()

    def test_returned_manager_receives_exporters_list(self):
        mock_exporter = MagicMock()
        mock_class = MagicMock(return_value=mock_exporter)

        with patch.dict(_EXPORTER_REGISTRY, {"mock_exp": mock_class}):
            config = _make_config(
                enabled=True,
                exporter_configs=(ExporterConfig(name="mock_exp", options={}),),
            )
            manager = create_telemetry_manager(config)
            try:
                assert manager is not None
                assert len(manager._exporters) == 1
                assert manager._exporters[0] is mock_exporter
            finally:
                if manager is not None:
                    manager.close()


class TestUnknownExporter:
    def test_unknown_exporter_raises_error(self):
        config = _make_config(
            enabled=True,
            exporter_configs=(ExporterConfig(name="nonexistent_exporter", options={}),),
        )
        with pytest.raises(TelemetryExporterError) as exc_info:
            create_telemetry_manager(config)
        assert exc_info.value.exporter_name == "nonexistent_exporter"

    def test_unknown_exporter_error_mentions_available(self):
        config = _make_config(
            enabled=True,
            exporter_configs=(ExporterConfig(name="bad_name", options={}),),
        )
        with pytest.raises(TelemetryExporterError) as exc_info:
            create_telemetry_manager(config)
        error_message = str(exc_info.value)
        assert "console" in error_message
        assert "otlp" in error_message
        assert "azure_monitor" in error_message
        assert "datadog" in error_message

    def test_unknown_exporter_error_message_contains_unknown(self):
        config = _make_config(
            enabled=True,
            exporter_configs=(ExporterConfig(name="phantom", options={}),),
        )
        with pytest.raises(TelemetryExporterError) as exc_info:
            create_telemetry_manager(config)
        assert "Unknown exporter" in exc_info.value.message

    def test_unknown_exporter_does_not_produce_manager(self):
        config = _make_config(
            enabled=True,
            exporter_configs=(
                ExporterConfig(name="console", options={}),
                ExporterConfig(name="does_not_exist", options={}),
            ),
        )
        with pytest.raises(TelemetryExporterError):
            create_telemetry_manager(config)


class TestExporterRegistry:
    def test_registry_contains_console(self):
        assert "console" in _EXPORTER_REGISTRY

    def test_registry_contains_otlp(self):
        assert "otlp" in _EXPORTER_REGISTRY

    def test_registry_contains_azure_monitor(self):
        assert "azure_monitor" in _EXPORTER_REGISTRY

    def test_registry_contains_datadog(self):
        assert "datadog" in _EXPORTER_REGISTRY

    def test_registry_has_exactly_four_entries(self):
        assert len(_EXPORTER_REGISTRY) == 4

    def test_registry_console_is_console_exporter(self):
        assert _EXPORTER_REGISTRY["console"] is ConsoleExporter

    def test_registry_otlp_is_otlp_exporter(self):
        assert _EXPORTER_REGISTRY["otlp"] is OTLPExporter

    def test_registry_azure_monitor_is_azure_monitor_exporter(self):
        assert _EXPORTER_REGISTRY["azure_monitor"] is AzureMonitorExporter

    def test_registry_datadog_is_datadog_exporter(self):
        assert _EXPORTER_REGISTRY["datadog"] is DatadogExporter

    def test_registry_values_are_types(self):
        for name, cls in _EXPORTER_REGISTRY.items():
            assert isinstance(cls, type), f"Registry entry '{name}' is not a type: {cls!r}"
