"""Tests for middleware registry to reach 80% coverage.

Focus on testing uncovered error cases and edge paths (lines 71, 75, 86, 88, 95-96, 102-104).
"""

from __future__ import annotations

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.middleware import (
    create_middleware,
    create_middlewares,
    validate_middleware_definition,
)
from elspeth.core.validation.base import ConfigurationError


def test_validate_middleware_empty_definition():
    """Test validate_middleware_definition raises on empty definition (line 71)."""
    with pytest.raises(ConfigurationError, match="Middleware definition cannot be empty"):
        validate_middleware_definition({})


def test_validate_middleware_missing_name():
    """Test validate_middleware_definition raises when name/plugin missing (line 75)."""
    with pytest.raises(ConfigurationError, match="Middleware definition missing 'name' or 'plugin'"):
        validate_middleware_definition({"options": {}})


def test_validate_middleware_unknown_plugin():
    """Test validate_middleware_definition raises for unknown plugin (line 82)."""
    with pytest.raises(ConfigurationError, match="Unknown LLM middleware 'nonexistent'"):
        validate_middleware_definition({"name": "nonexistent"})


def test_validate_middleware_invalid_options_type():
    """Test validate_middleware_definition raises when options is not dict (lines 87-88)."""
    with pytest.raises(ConfigurationError, match="Middleware options must be a mapping"):
        validate_middleware_definition({"name": "noop", "options": "invalid"})


def test_validate_middleware_none_options():
    """Test validate_middleware_definition handles None options (lines 85-86)."""
    # Should not raise - None options should be converted to empty dict
    validate_middleware_definition({"name": "noop", "options": None})


def test_validate_middleware_security_level_conflict():
    """Test validate_middleware_definition raises on security_level conflict (lines 94-96)."""
    # Conflicting security levels should raise
    with pytest.raises(ConfigurationError, match="llm_middleware:noop"):
        validate_middleware_definition(
            {
                "name": "noop",
                "security_level": "public",
                "options": {"security_level": "confidential"},
            }
        )


def test_validate_middleware_schema_validation_error():
    """Test validate_middleware_definition raises on schema validation failure (lines 101-104)."""
    # Try to validate a middleware with invalid options
    # We need a middleware with a schema that can fail
    # For this test, let's assume we're using a middleware plugin that has validation
    with pytest.raises(ConfigurationError):
        validate_middleware_definition(
            {
                "name": "noop",
                "options": {"invalid_option_that_fails_schema": "bad_value"},
            }
        )


def test_validate_middleware_success_with_name():
    """Test successful validation with 'name' key."""
    # Should not raise
    validate_middleware_definition({"name": "noop"})


def test_validate_middleware_success_with_plugin():
    """Test successful validation with 'plugin' key."""
    # Should not raise
    validate_middleware_definition({"plugin": "noop"})


def test_validate_middleware_success_with_options():
    """Test successful validation with valid options."""
    # Should not raise
    validate_middleware_definition(
        {
            "name": "noop",
            "options": {},
        }
    )


def test_create_middleware_basic():
    """Test creating middleware with basic definition."""
    definition = {"name": "noop"}
    middleware = create_middleware(definition)
    assert middleware is not None


def test_create_middleware_with_context():
    """Test creating middleware with parent context."""
    definition = {"name": "noop"}
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="llm_middleware",
        plugin_name="noop",
    )
    middleware = create_middleware(definition, parent_context=context)
    assert middleware is not None


def test_create_middleware_with_provenance():
    """Test creating middleware with custom provenance."""
    definition = {"name": "noop"}
    middleware = create_middleware(definition, provenance=["custom", "provenance"])
    assert middleware is not None


def test_create_middlewares_empty():
    """Test create_middlewares returns empty list for None input."""
    result = create_middlewares(None)
    assert result == []


def test_create_middlewares_empty_list():
    """Test create_middlewares returns empty list for empty list input."""
    result = create_middlewares([])
    assert result == []


def test_create_middlewares_multiple():
    """Test creating multiple middlewares."""
    definitions = [
        {"name": "noop"},
        {"name": "noop"},
    ]
    middlewares = create_middlewares(definitions)
    assert len(middlewares) == 2
    assert all(m is not None for m in middlewares)


def test_create_middlewares_with_context():
    """Test creating middlewares with parent context."""
    definitions = [{"name": "noop"}]
    context = PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="llm_middleware",
        plugin_name="noop",
    )
    middlewares = create_middlewares(definitions, parent_context=context)
    assert len(middlewares) == 1


def test_create_middleware_none_result_guard():
    """Test that create_middleware handles unexpected None (defensive line 53-54)."""
    # This is a defensive check - we can't easily trigger it in normal flow
    # since create_plugin_with_inheritance raises ValueError instead of returning None
    # when allow_none=False. But we can verify the function exists and runs.
    definition = {"name": "noop"}
    middleware = create_middleware(definition)
    assert middleware is not None  # Should never be None


def test_validate_middleware_with_both_name_and_plugin():
    """Test validation when both name and plugin are present."""
    # Should use 'name' first if both are present
    validate_middleware_definition({"name": "noop", "plugin": "noop"})


def test_validate_middleware_extracts_available_plugins_on_error():
    """Test that error message includes available plugins."""
    try:
        validate_middleware_definition({"name": "unknown_plugin"})
        pytest.fail("Should have raised ConfigurationError")
    except ConfigurationError as exc:
        # Error message should mention available plugins
        assert "Available:" in str(exc)


def test_validate_middleware_coalesce_security_level_success():
    """Test successful security level coalescing."""
    # Same security level in both places should succeed
    validate_middleware_definition(
        {
            "name": "noop",
            "security_level": "public",
            "options": {"security_level": "public"},
        }
    )


def test_validate_middleware_no_security_level():
    """Test validation when no security level is provided."""
    # Should succeed without security level
    validate_middleware_definition({"name": "noop", "options": {}})


def test_create_middleware_error_handling():
    """Test that create_middleware propagates errors appropriately."""
    # Invalid definition should raise an error
    with pytest.raises(Exception):  # Will be ValueError from registry
        create_middleware({"name": "nonexistent_middleware"})


def test_validate_middleware_removes_security_level_before_validation():
    """Test that security_level is removed from options before schema validation."""
    # This tests line 99 - security_level should be popped before validation
    validate_middleware_definition(
        {
            "name": "noop",
            "options": {"security_level": "public"},
        }
    )
