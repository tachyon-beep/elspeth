"""Tests for worker process protocol handling."""

import io
import os
from unittest.mock import patch

import msgpack
import pytest

from elspeth.orchestrator.worker_process import (
    WorkerProtocolError,
    _handle_request,
    _handle_transform_operation,
)


def test_handle_transform_operation_echo():
    """Test transform operation returns proxy ID (stub implementation)."""
    proxy_id = "abc123"
    plugin_name = "test_plugin"
    params = {"threshold": 0.5}

    # Current stub implementation just returns the same proxy_id
    result = _handle_transform_operation(proxy_id, plugin_name, params)

    assert result == proxy_id


def test_handle_request_success():
    """Test successful request handling."""
    request = {
        "operation": "transform",
        "proxy_id": "abc123",
        "plugin_name": "test_plugin",
        "plugin_params": {"threshold": 0.5},
        "request_id": "req_001",
    }

    response = _handle_request(request)

    assert response["status"] == "ok"
    assert response["result_proxy_id"] == "abc123"  # Echo behavior
    assert response["request_id"] == "req_001"


def test_handle_request_unknown_operation():
    """Test request with unknown operation."""
    request = {
        "operation": "unknown",
        "request_id": "req_002",
    }

    response = _handle_request(request)

    assert response["status"] == "error"
    assert response["error_type"] == "WorkerProtocolError"
    assert "Unknown operation" in response["message"]
    assert response["request_id"] == "req_002"


def test_handle_request_missing_field():
    """Test request with missing required field."""
    request = {
        "operation": "transform",
        "plugin_name": "test_plugin",
        # Missing proxy_id
        "request_id": "req_003",
    }

    response = _handle_request(request)

    assert response["status"] == "error"
    assert response["error_type"] == "WorkerProtocolError"
    assert "Missing required field" in response["message"]
    assert response["request_id"] == "req_003"


def test_handle_request_plugin_error():
    """Test request where plugin execution fails."""
    request = {
        "operation": "transform",
        "proxy_id": "abc123",
        "plugin_name": "failing_plugin",
        "plugin_params": {},
        "request_id": "req_004",
    }

    # Mock _handle_transform_operation to raise exception
    with patch(
        "elspeth.orchestrator.worker_process._handle_transform_operation",
        side_effect=RuntimeError("Plugin failed"),
    ):
        response = _handle_request(request)

    assert response["status"] == "error"
    assert response["error_type"] == "RuntimeError"
    assert "Plugin failed" in response["message"]
    assert response["request_id"] == "req_004"


def test_handle_request_shutdown_operation():
    """Test shutdown operation returns None to signal exit."""
    request = {
        "operation": "shutdown",
    }

    response = _handle_request(request)

    # Shutdown returns None to signal worker should exit
    assert response is None


def test_worker_process_no_sidecar_import(monkeypatch):
    """Test worker_process module never imports sidecar_client.

    This security test MUST run in standalone mode to verify architectural
    isolation. Worker processes should never import sidecar_client regardless
    of integration test mode.
    """
    import sys

    # Force standalone mode for this security test
    monkeypatch.setenv("ELSPETH_SIDECAR_MODE", "standalone")

    # Clear any sidecar_client modules from sys.modules (may have been loaded by integration tests)
    sidecar_modules_before = [name for name in list(sys.modules.keys()) if "sidecar_client" in name]
    for module_name in sidecar_modules_before:
        del sys.modules[module_name]

    # Also clear worker_process if it was already loaded
    if "elspeth.orchestrator.worker_process" in sys.modules:
        del sys.modules["elspeth.orchestrator.worker_process"]

    # Now import worker_process in standalone mode
    import elspeth.orchestrator.worker_process

    # Verify sidecar_client was NOT imported as a result of importing worker_process
    sidecar_modules_after = [
        name for name in sys.modules if "sidecar_client" in name
    ]

    # This should be empty - worker never imports sidecar_client
    assert len(sidecar_modules_after) == 0, (
        f"Worker process should never import sidecar_client, found: {sidecar_modules_after}"
    )
