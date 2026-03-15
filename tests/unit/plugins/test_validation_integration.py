"""Integration tests for validation subsystem.

These tests are written BEFORE implementation and will fail until
PluginConfigValidator and PluginManager integration are complete.

They serve as completion criteria for the migration.
"""

import pytest

from elspeth.plugins.infrastructure.manager import PluginManager


def test_plugin_manager_has_validator():
    """PluginManager has PluginConfigValidator instance."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    assert hasattr(manager, "_validator")
    assert manager._validator is not None


def test_manager_validates_source_config_before_creation():
    """PluginManager validates source config before instantiation."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    # Invalid config - missing required 'path'
    invalid_config = {
        "schema": {"mode": "observed"},
        "on_validation_failure": "quarantine",
    }

    with pytest.raises(ValueError) as exc_info:
        manager.create_source("csv", invalid_config)

    assert "path" in str(exc_info.value)
    assert "required" in str(exc_info.value).lower()


def test_valid_config_creates_working_plugin():
    """Valid config passes validation and creates functional plugin."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    valid_config = {
        "path": "/tmp/test.csv",
        "schema": {"mode": "observed"},
        "on_validation_failure": "quarantine",
    }

    source = manager.create_source("csv", valid_config)

    # Verify plugin is functional
    assert source.name == "csv"
    assert source.output_schema is not None
    assert hasattr(source, "load")


def test_validator_handles_all_builtin_sources():
    """Validator can validate configs for all builtin source types."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    # Registered plugin names: csv, json, null, azure_blob
    source_types = ["csv", "json", "null", "azure_blob"]

    for source_type in source_types:
        # Verify the plugin type is recognized. Config validation errors
        # (missing required fields) are expected — but "unknown plugin"
        # errors must not be silently swallowed.
        try:
            manager.create_source(source_type, {})
        except (ValueError, TypeError) as e:
            # Fail if the error is actually "unknown plugin" — that means
            # the name is wrong, not that config validation caught a bad config.
            if "unknown" in str(e).lower():
                pytest.fail(f"Plugin type {source_type!r} not registered: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error for {source_type}: {e}")


def test_validator_provides_field_level_errors():
    """Validation errors include field name and human-readable message."""
    manager = PluginManager()
    manager.register_builtin_plugins()

    # Wrong type for skip_rows
    invalid_config = {
        "path": "/tmp/test.csv",
        "skip_rows": "not_an_int",  # Should be int
        "schema": {"mode": "observed"},
        "on_validation_failure": "quarantine",
    }

    with pytest.raises(ValueError) as exc_info:
        manager.create_source("csv", invalid_config)

    error_msg = str(exc_info.value)
    assert "skip_rows" in error_msg  # Field name present
    # Should have human-readable message about type
    assert "int" in error_msg.lower() or "type" in error_msg.lower()  # Type mismatch mentioned
