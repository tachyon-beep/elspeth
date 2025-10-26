"""Tests for rate_limiter_registry.py to reach 80% coverage.

Focus on testing uncovered lines 38, 40, 50-61 which are error handling paths.
"""

from __future__ import annotations

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.controls.rate_limiter_registry import (
    _create_adaptive_rate_limiter,
    _create_fixed_window_rate_limiter,
    _create_noop_rate_limiter,
    rate_limiter_registry,
)
from elspeth.core.validation.base import ConfigurationError


def test_noop_rate_limiter_factory():
    """Test noop rate limiter factory."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="noop",
    )
    limiter = _create_noop_rate_limiter({}, context)
    assert limiter is not None


def test_fixed_window_missing_requests():
    """Test fixed_window factory raises ConfigurationError when requests is missing (line 38)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="fixed_window",
    )
    with pytest.raises(ConfigurationError, match="requests is required"):
        _create_fixed_window_rate_limiter({"per_seconds": 1.0}, context)


def test_fixed_window_missing_per_seconds():
    """Test fixed_window factory raises ConfigurationError when per_seconds is missing (line 40)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="fixed_window",
    )
    with pytest.raises(ConfigurationError, match="per_seconds is required"):
        _create_fixed_window_rate_limiter({"requests": 10}, context)


def test_fixed_window_success():
    """Test fixed_window factory succeeds with valid options."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="fixed_window",
    )
    limiter = _create_fixed_window_rate_limiter({"requests": 10, "per_seconds": 60.0}, context)
    assert limiter is not None


def test_adaptive_missing_requests_per_minute():
    """Test adaptive factory raises ConfigurationError when requests_per_minute is missing (line 53)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="adaptive",
    )
    with pytest.raises(ConfigurationError, match="requests_per_minute is required"):
        _create_adaptive_rate_limiter({"interval_seconds": 1.0}, context)


def test_adaptive_missing_interval_seconds():
    """Test adaptive factory raises ConfigurationError when interval_seconds is missing (line 55)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="adaptive",
    )
    with pytest.raises(ConfigurationError, match="interval_seconds is required"):
        _create_adaptive_rate_limiter({"requests_per_minute": 100}, context)


def test_adaptive_without_tokens_per_minute():
    """Test adaptive factory succeeds without tokens_per_minute (lines 58-60)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="adaptive",
    )
    limiter = _create_adaptive_rate_limiter(
        {"requests_per_minute": 100, "interval_seconds": 1.0},
        context,
    )
    assert limiter is not None


def test_adaptive_with_tokens_per_minute():
    """Test adaptive factory succeeds with tokens_per_minute (lines 57-61)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="adaptive",
    )
    limiter = _create_adaptive_rate_limiter(
        {
            "requests_per_minute": 100,
            "tokens_per_minute": 10000,
            "interval_seconds": 1.0,
        },
        context,
    )
    assert limiter is not None


def test_adaptive_with_none_tokens_per_minute():
    """Test adaptive factory handles None tokens_per_minute (lines 58-60)."""
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="rate_limiter",
        plugin_name="adaptive",
    )
    limiter = _create_adaptive_rate_limiter(
        {
            "requests_per_minute": 100,
            "tokens_per_minute": None,
            "interval_seconds": 1.0,
        },
        context,
    )
    assert limiter is not None


def test_registry_has_all_rate_limiters():
    """Test that all rate limiters are registered."""
    plugins = rate_limiter_registry.list_plugins()
    assert "noop" in plugins
    assert "fixed_window" in plugins
    assert "adaptive" in plugins


def test_registry_create_via_registry():
    """Test creating rate limiters via registry interface."""
    # Create parent context for inheritance
    parent_context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="test",
        plugin_name="parent",
    )

    # Test noop
    limiter = rate_limiter_registry.create(
        "noop",
        {},
        parent_context=parent_context,
        require_determinism=False,
    )
    assert limiter is not None

    # Test fixed_window
    limiter = rate_limiter_registry.create(
        "fixed_window",
        {"requests": 10, "per_seconds": 1.0},
        parent_context=parent_context,
        require_determinism=False,
    )
    assert limiter is not None

    # Test adaptive
    limiter = rate_limiter_registry.create(
        "adaptive",
        {"requests_per_minute": 100, "interval_seconds": 1.0},
        parent_context=parent_context,
        require_determinism=False,
    )
    assert limiter is not None


def test_registry_validate_fixed_window_schema():
    """Test schema validation for fixed_window."""
    # Valid schema should pass
    rate_limiter_registry.validate("fixed_window", {"requests": 10, "per_seconds": 1.0})

    # Invalid schema should fail
    with pytest.raises(ConfigurationError):
        rate_limiter_registry.validate("fixed_window", {"requests": 0, "per_seconds": 1.0})

    with pytest.raises(ConfigurationError):
        rate_limiter_registry.validate("fixed_window", {"requests": 10, "per_seconds": 0})


def test_registry_validate_adaptive_schema():
    """Test schema validation for adaptive."""
    # Valid schema should pass
    rate_limiter_registry.validate("adaptive", {"requests_per_minute": 100, "interval_seconds": 1.0})

    # With tokens_per_minute
    rate_limiter_registry.validate(
        "adaptive",
        {"requests_per_minute": 100, "tokens_per_minute": 10000, "interval_seconds": 1.0},
    )

    # Invalid schema should fail
    with pytest.raises(ConfigurationError):
        rate_limiter_registry.validate("adaptive", {"requests_per_minute": 0, "interval_seconds": 1.0})

    with pytest.raises(ConfigurationError):
        rate_limiter_registry.validate("adaptive", {"requests_per_minute": 100, "interval_seconds": 0})
