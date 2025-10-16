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
    if name == "validate_settings":
        from .settings import validate_settings as _validate_settings

        return _validate_settings
    if name in {"validate_suite", "SuiteValidationReport"}:
        from .suite import SuiteValidationReport as _SuiteValidationReport, validate_suite as _validate_suite

        return {"validate_suite": _validate_suite, "SuiteValidationReport": _SuiteValidationReport}[name]
    raise AttributeError(f"module 'elspeth.core.validation' has no attribute {name!r}")
