"""Tests for PluginRetryableError base class and error hierarchy."""

from elspeth.contracts.errors import PluginRetryableError


def test_plugin_retryable_error_has_retryable_attribute():
    err = PluginRetryableError("test", retryable=True)
    assert err.retryable is True
    assert str(err) == "test"


def test_plugin_retryable_error_has_status_code():
    err = PluginRetryableError("test", retryable=False, status_code=404)
    assert err.retryable is False
    assert err.status_code == 404


def test_plugin_retryable_error_status_code_defaults_none():
    err = PluginRetryableError("test", retryable=True)
    assert err.status_code is None
