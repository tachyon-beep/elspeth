"""Validation helpers and base classes."""

from typing import TYPE_CHECKING

from .base import ConfigurationError, ValidationMessage, ValidationReport, validate_schema

if TYPE_CHECKING:
    # Imported only for type-checkers and linters (avoids runtime imports while satisfying static tools)
    from .settings import validate_settings  # pragma: no cover - static-only import
    from .suite import (
        SuiteValidationReport,  # pragma: no cover - static-only import
        validate_suite,  # pragma: no cover - static-only import
    )

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
        from .suite import SuiteValidationReport as _SuiteValidationReport
        from .suite import validate_suite as _validate_suite

        return {"validate_suite": _validate_suite, "SuiteValidationReport": _SuiteValidationReport}[name]
    raise AttributeError(f"module 'elspeth.core.validation' has no attribute {name!r}")
