"""Tests for plugin configuration validation subsystem."""

import pytest

from elspeth.plugins.validation import PluginConfigValidator


def test_validator_accepts_valid_source_config():
    """Valid source config passes validation."""
    validator = PluginConfigValidator()

    config = {
        "path": "/tmp/test.csv",
        "schema": {"fields": "dynamic"},
        "on_validation_failure": "quarantine",
    }

    errors = validator.validate_source_config("csv", config)
    assert errors == []


def test_validator_rejects_missing_required_field():
    """Missing required field returns error."""
    validator = PluginConfigValidator()

    config = {
        # Missing 'path' - required by CSVSourceConfig
        "schema": {"fields": "dynamic"},
        "on_validation_failure": "quarantine",
    }

    errors = validator.validate_source_config("csv", config)
    assert len(errors) == 1
    assert "path" in errors[0].field
    assert "required" in errors[0].message.lower()


def test_validator_rejects_invalid_field_type():
    """Invalid field type returns error."""
    validator = PluginConfigValidator()

    config = {
        "path": "/tmp/test.csv",
        "skip_rows": "not_an_int",  # Should be int
        "schema": {"fields": "dynamic"},
        "on_validation_failure": "quarantine",
    }

    errors = validator.validate_source_config("csv", config)
    assert len(errors) == 1
    assert "skip_rows" in errors[0].field


def test_validator_accepts_null_source_with_empty_config():
    """null_source has no config class, validation should pass with empty dict."""
    validator = PluginConfigValidator()

    config = {}

    errors = validator.validate_source_config("null_source", config)
    assert errors == []


def test_validator_accepts_null_source_with_arbitrary_config():
    """null_source ignores config, validation should pass with any dict."""
    validator = PluginConfigValidator()

    config = {
        "arbitrary_field": "ignored",
        "another_field": 42,
    }

    errors = validator.validate_source_config("null_source", config)
    assert errors == []


def test_validator_accepts_valid_transform_config():
    """Valid transform config passes validation."""
    validator = PluginConfigValidator()

    config = {
        "schema": {"fields": "dynamic"},
    }

    errors = validator.validate_transform_config("passthrough", config)
    assert errors == []


def test_validator_accepts_valid_sink_config():
    """Valid sink config passes validation."""
    validator = PluginConfigValidator()

    config = {
        "path": "/tmp/output.csv",
        "schema": {"fields": "dynamic"},
    }

    errors = validator.validate_sink_config("csv", config)
    assert errors == []


def test_validator_rejects_unknown_gate_type():
    """Gate validation raises error since no gate plugins exist yet."""
    validator = PluginConfigValidator()

    config = {
        "field": "score",
        "threshold": 0.5,
        "schema": {"fields": "dynamic"},
    }

    # No gate plugins exist in codebase yet, so this should raise
    with pytest.raises(ValueError) as exc_info:
        validator.validate_gate_config("threshold", config)

    assert "Unknown gate type" in str(exc_info.value)
