"""Validation helpers and base classes."""

from .base import ConfigurationError, ValidationMessage, ValidationReport, validate_schema

__all__ = [
    "ConfigurationError",
    "ValidationMessage",
    "ValidationReport",
    "SuiteValidationReport",
    "validate_schema",
    "validate_settings",
    "validate_suite",
]


def __getattr__(name: str):
    if name in {"SuiteValidationReport", "validate_settings", "validate_suite"}:
        from . import validators

        return getattr(validators, name)
    raise AttributeError(f"module 'elspeth.core.validation' has no attribute {name!r}")
