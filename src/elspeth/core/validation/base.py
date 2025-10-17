"""Base validation classes and utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence


class ConfigurationError(RuntimeError):
    """Raised when configuration validation fails."""


@dataclass
class ValidationMessage:
    """Represents a single validation outcome with optional context."""

    message: str
    context: str | None = None

    def format(self) -> str:
        """Return a human-readable message suitable for user display."""

        if self.context:
            return f"{self.context}: {self.message}"
        return self.message


@dataclass
class ValidationReport:
    """Aggregates validation errors and warnings for a configuration."""

    errors: list[ValidationMessage] = field(default_factory=list)
    warnings: list[ValidationMessage] = field(default_factory=list)

    def add_error(self, message: str, context: str | None = None) -> None:
        """Record an error message with optional context."""

        self.errors.append(ValidationMessage(message=message, context=context))

    def add_warning(self, message: str, context: str | None = None) -> None:
        """Record a warning message with optional context."""

        self.warnings.append(ValidationMessage(message=message, context=context))

    def extend(self, other: "ValidationReport") -> None:
        """Merge another report into this one."""

        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def raise_if_errors(self) -> None:
        """Raise a ConfigurationError when the report contains errors."""

        if self.errors:
            formatted = "\n".join(msg.format() for msg in self.errors)
            raise ConfigurationError(formatted)

    def has_errors(self) -> bool:
        """Return True if the report contains errors."""

        return bool(self.errors)

    def has_warnings(self) -> bool:
        """Return True if the report contains warnings."""

        return bool(self.warnings)


def validate_schema(
    data: Mapping[str, object] | None,
    schema: Mapping[str, object],
    *,
    context: str | None = None,
) -> Iterable[ValidationMessage]:
    """Validate ``data`` against ``schema`` returning validation messages."""

    if data is None:
        yield ValidationMessage("value is missing", context=context)
        return

    errors: list[tuple[tuple[object, ...], str]] = []
    _validate_node(data, schema, (), errors)
    for path, message in errors:
        pointer = _format_error_path(path)
        details = message
        if pointer:
            details = f"{details} (path: {pointer})"
        yield ValidationMessage(details, context=context)


def _validate_node(
    value: Any,
    schema: Mapping[str, Any],
    path: tuple[object, ...],
    errors: list[tuple[tuple[object, ...], str]],
) -> None:
    """Recursively validate ``value`` against ``schema`` accumulating errors."""

    # Defensive runtime check: schema is typed as Mapping but we guard against None
    # Mypy considers this unreachable but it's a safety check for untrusted inputs
    if schema is None:
        return  # type: ignore[unreachable]

    any_of = schema.get("anyOf")
    if any_of:
        _validate_any_of(value, any_of, path, errors)

    expected_type = schema.get("type")
    if expected_type and not _check_type(value, expected_type):
        errors.append((path, f"must be of type {expected_type}"))
        return

    if isinstance(value, Mapping):
        _validate_object(value, schema, path, errors)
    if isinstance(value, list):
        _validate_array(value, schema, path, errors)

    _validate_enum_membership(value, schema, path, errors)
    _validate_numeric_bounds(value, schema, path, errors)


def _validate_any_of(
    value: Any,
    options: Sequence[Mapping[str, Any]],
    path: tuple[object, ...],
    errors: list[tuple[tuple[object, ...], str]],
) -> None:
    """Validate ``value`` matches at least one schema in ``options``."""

    for option in options:
        option_errors: list[tuple[tuple[object, ...], str]] = []
        _validate_node(value, option, path, option_errors)
        if not option_errors:
            return
    errors.append((path, "did not match any allowed schemas"))


def _validate_object(
    value: Mapping[str, Any],
    schema: Mapping[str, Any],
    path: tuple[object, ...],
    errors: list[tuple[tuple[object, ...], str]],
) -> None:
    """Validate object-specific constraints for ``value``."""

    required = schema.get("required", [])
    for key in required:
        if key not in value:
            errors.append((path + (key,), "is a required property"))

    properties = schema.get("properties", {})
    for key, subschema in properties.items():
        if key in value:
            _validate_node(value[key], subschema, path + (key,), errors)


def _validate_array(
    value: Sequence[Any],
    schema: Mapping[str, Any],
    path: tuple[object, ...],
    errors: list[tuple[tuple[object, ...], str]],
) -> None:
    """Validate array-specific constraints for ``value``."""

    item_schema = schema.get("items")
    if not item_schema:
        return

    for index, item in enumerate(value):
        _validate_node(item, item_schema, path + (index,), errors)


def _validate_enum_membership(
    value: Any,
    schema: Mapping[str, Any],
    path: tuple[object, ...],
    errors: list[tuple[tuple[object, ...], str]],
) -> None:
    """Ensure ``value`` is one of the allowed enum values if provided."""

    enum = schema.get("enum")
    if enum is not None and value not in enum:
        errors.append((path, f"must be one of {enum}"))


def _validate_numeric_bounds(
    value: Any,
    schema: Mapping[str, Any],
    path: tuple[object, ...],
    errors: list[tuple[tuple[object, ...], str]],
) -> None:
    """Validate numeric upper and lower bounds for ``value``."""

    if not _is_number(value):
        return

    minimum = schema.get("minimum")
    if minimum is not None and value < minimum:
        errors.append((path, f"must be >= {minimum}"))

    exclusive_min = schema.get("exclusiveMinimum")
    if exclusive_min is not None and value <= exclusive_min:
        errors.append((path, f"must be > {exclusive_min}"))

    maximum = schema.get("maximum")
    if maximum is not None and value > maximum:
        errors.append((path, f"must be <= {maximum}"))

    exclusive_max = schema.get("exclusiveMaximum")
    if exclusive_max is not None and value >= exclusive_max:
        errors.append((path, f"must be < {exclusive_max}"))


def _check_type(value: Any, expected: str) -> bool:
    """Return True when ``value`` matches the schema ``expected`` type."""

    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return _is_number(value)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _is_number(value: Any) -> bool:
    """Return True for numeric values excluding booleans."""

    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format_error_path(path: Iterable[object]) -> str:
    parts = []
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
        else:
            if parts:
                parts.append(".")
            parts.append(str(item))
    return "".join(parts)


__all__ = [
    "ConfigurationError",
    "ValidationMessage",
    "ValidationReport",
    "validate_schema",
]
