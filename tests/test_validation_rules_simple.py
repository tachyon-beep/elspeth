"""Simple tests for validation rules to reach 80% coverage."""

import pytest

from elspeth.core.validation.base import ConfigurationError, ValidationReport
from elspeth.core.validation.rules import (
    _validate_experiment_plugins,
    _validate_middleware_list,
    _validate_plugin_list,
    _validate_plugin_reference,
    _validate_security_level_fields,
)


def test_validate_security_level_fields_both_valid():
    """Test security level validation with matching levels."""
    report = ValidationReport()
    result = _validate_security_level_fields(
        report,
        context="test",
        entry_level="internal",
        options_level="internal",
    )
    # "internal" alias maps to "OFFICIAL" (PSPF normalized value)
    assert result == "OFFICIAL"
    assert not report.has_errors()


def test_validate_security_level_fields_conflict():
    """Test security level validation with conflicting levels."""
    report = ValidationReport()
    _validate_security_level_fields(
        report,
        context="test",
        entry_level="OFFICIAL",  # Use PSPF values directly
        options_level="PROTECTED",  # Different level to create conflict
    )
    assert report.has_errors()
    assert any("Conflicting" in msg.message for msg in report.errors)


def test_validate_security_level_fields_empty_entry():
    """Test security level validation with empty entry level."""
    report = ValidationReport()
    _validate_security_level_fields(
        report,
        context="test",
        entry_level="",
        options_level=None,
    )
    assert report.has_errors()
    assert any("non-empty" in msg.message for msg in report.errors)


def test_validate_security_level_fields_neither_set():
    """Test security level validation when neither level is set."""
    report = ValidationReport()
    _validate_security_level_fields(
        report,
        context="test",
        entry_level=None,
        options_level=None,
    )
    assert report.has_errors()
    assert any("must declare a security_level" in msg.message for msg in report.errors)


def test_validate_plugin_reference_valid():
    """Test plugin reference validation with valid entry."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass  # No errors

    entry = {"plugin": "test_plugin", "security_level": "internal", "options": {}}
    _validate_plugin_reference(
        report,
        entry,
        kind="datasource",
        validator=mock_validator,
        require_security_level=True,
    )
    assert not report.has_errors()


def test_validate_plugin_reference_not_mapping():
    """Test plugin reference validation with non-mapping entry."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass

    _validate_plugin_reference(
        report,
        "not_a_mapping",
        kind="datasource",
        validator=mock_validator,
    )
    assert report.has_errors()
    assert any("must be a mapping" in msg.message for msg in report.errors)


def test_validate_plugin_reference_missing_plugin():
    """Test plugin reference validation with missing plugin name."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass

    _validate_plugin_reference(
        report,
        {"options": {}},
        kind="datasource",
        validator=mock_validator,
    )
    assert report.has_errors()
    assert any("Missing 'plugin'" in msg.message for msg in report.errors)


def test_validate_plugin_reference_invalid_options():
    """Test plugin reference validation with non-mapping options."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass

    entry = {"plugin": "test", "options": "not_a_dict"}
    _validate_plugin_reference(
        report,
        entry,
        kind="datasource",
        validator=mock_validator,
    )
    assert report.has_errors()
    assert any("Options must be a mapping" in msg.message for msg in report.errors)


def test_validate_plugin_list_valid():
    """Test plugin list validation with valid list."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass  # No errors

    plugins = [
        {"plugin": "plugin1", "security_level": "internal"},
        {"plugin": "plugin2", "security_level": "internal"},
    ]
    _validate_plugin_list(report, plugins, mock_validator, context="test_plugins")
    assert not report.has_errors()


def test_validate_plugin_list_not_list():
    """Test plugin list validation with non-list value."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass

    _validate_plugin_list(report, {"plugin": "test"}, mock_validator, context="test_plugins")
    assert report.has_errors()
    assert any("Expected a list" in msg.message for msg in report.errors)


def test_validate_plugin_list_none():
    """Test plugin list validation with None (should pass)."""
    report = ValidationReport()

    def mock_validator(name, options):
        pass

    _validate_plugin_list(report, None, mock_validator, context="test_plugins")
    assert not report.has_errors()


def test_validate_experiment_plugins_valid():
    """Test experiment plugins validation with valid definitions."""
    report = ValidationReport()

    def mock_validator(definition):
        pass  # No errors

    entries = [
        {"name": "noop", "security_level": "internal"},
    ]
    _validate_experiment_plugins(report, entries, mock_validator, context="row_plugins")
    assert not report.has_errors()


def test_validate_experiment_plugins_not_list():
    """Test experiment plugins validation with non-list value."""
    report = ValidationReport()

    def mock_validator(definition):
        pass

    _validate_experiment_plugins(report, "not_a_list", mock_validator, context="row_plugins")
    assert report.has_errors()
    assert any("Expected a list" in msg.message for msg in report.errors)


def test_validate_experiment_plugins_not_mapping():
    """Test experiment plugins validation with non-mapping entry."""
    report = ValidationReport()

    def mock_validator(definition):
        pass

    _validate_experiment_plugins(report, ["string"], mock_validator, context="row_plugins")
    assert report.has_errors()
    assert any("must be a mapping" in msg.message for msg in report.errors)


def test_validate_experiment_plugins_validator_error():
    """Test experiment plugins validation propagates validator errors."""
    report = ValidationReport()

    def failing_validator(definition):
        raise ConfigurationError("Validation failed")

    entries = [{"name": "test", "security_level": "internal"}]
    _validate_experiment_plugins(report, entries, failing_validator, context="row_plugins")
    assert report.has_errors()
    assert any("Validation failed" in msg.message for msg in report.errors)


def test_validate_middleware_list_valid():
    """Test middleware list validation with valid definitions."""
    report = ValidationReport()

    def mock_validator(definition):
        pass  # No errors

    entries = [
        {"name": "audit_logger", "security_level": "internal"},
    ]
    _validate_middleware_list(report, entries, mock_validator, context="middleware")
    assert not report.has_errors()


def test_validate_middleware_list_not_list():
    """Test middleware list validation with non-list value."""
    report = ValidationReport()

    def mock_validator(definition):
        pass

    _validate_middleware_list(report, "not_a_list", mock_validator, context="middleware")
    assert report.has_errors()
    assert any("Expected a list" in msg.message for msg in report.errors)


def test_validate_middleware_list_none():
    """Test middleware list validation with None (should pass)."""
    report = ValidationReport()

    def mock_validator(definition):
        pass

    _validate_middleware_list(report, None, mock_validator, context="middleware")
    assert not report.has_errors()


def test_validate_middleware_list_validator_error():
    """Test middleware list validation propagates validator errors."""
    report = ValidationReport()

    def failing_validator(definition):
        raise ValueError("Invalid middleware")

    entries = [{"name": "test", "security_level": "internal"}]
    _validate_middleware_list(report, entries, failing_validator, context="middleware")
    assert report.has_errors()
    assert any("Invalid middleware" in msg.message for msg in report.errors)
