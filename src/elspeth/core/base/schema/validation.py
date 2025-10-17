"""
Validation and compatibility helpers for dataframe schemas.

Contains row/dataframe validation routines and compatibility checks that
ensure datasource schemas satisfy plugin requirements.
"""

from __future__ import annotations

import typing
from typing import Any, Type

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from .base import DataFrameSchema, SchemaCompatibilityError, SchemaViolation


def validate_row(
    row: dict[str, Any],
    schema: Type[DataFrameSchema],
    *,
    row_index: int = 0,
) -> tuple[bool, SchemaViolation | None]:
    """
    Validate a single row against a schema.

    Returns a tuple of `(is_valid, violation_or_none)` where `violation` is a
    structured error payload when validation fails.
    """
    try:
        schema.model_validate(row)
        return (True, None)

    except PydanticValidationError as exc:  # pragma: no cover - exercised via callers
        errors = []
        for error in exc.errors():
            errors.append(
                {
                    "field": ".".join(str(loc) for loc in error["loc"]),
                    "type": error["type"],
                    "message": error["msg"],
                    "input_value": error.get("input"),
                }
            )

        violation = SchemaViolation(
            row_index=row_index,
            row_data=row,
            errors=errors,
            schema_name=schema.__name__,
        )

        return (False, violation)


def validate_dataframe(
    df: pd.DataFrame,
    schema: Type[DataFrameSchema],
    *,
    early_stop: bool = True,
) -> tuple[bool, list[SchemaViolation]]:
    """
    Validate all rows in a DataFrame against a schema.

    Returns `(is_valid, violations)` where `violations` captures any rows that
    failed validation. When `early_stop` is True we bail after the first
    failure.
    """
    violations: list[SchemaViolation] = []

    for idx, (_, row) in enumerate(df.iterrows()):
        row_dict = row.to_dict()
        is_valid, violation = validate_row(row_dict, schema, row_index=idx)

        if not is_valid and violation is not None:
            violations.append(violation)
            if early_stop:
                break

    return (len(violations) == 0, violations)


def validate_schema_compatibility(
    datasource_schema: Type[DataFrameSchema],
    plugin_schema: Type[DataFrameSchema],
    *,
    plugin_name: str = "plugin",
) -> None:
    """
    Validate that datasource schema is compatible with plugin requirements.

    Checks:
    1. All required columns in `plugin_schema` exist in `datasource_schema`
    2. Column types are compatible (exact match or compatible subtypes)
    """
    datasource_fields = {}
    if hasattr(datasource_schema, "__annotations__"):
        datasource_fields = datasource_schema.__annotations__.copy()

    plugin_fields = {}
    if hasattr(plugin_schema, "__annotations__"):
        plugin_fields = plugin_schema.__annotations__.copy()

    missing_columns = []
    for col_name in plugin_fields:
        if col_name not in datasource_fields:
            missing_columns.append(col_name)

    if missing_columns:
        error_msg = (
            f"Plugin '{plugin_name}' requires columns not provided by datasource: {missing_columns}\n"
            f"Datasource provides: {list(datasource_fields.keys())}\n"
            f"Plugin requires: {list(plugin_fields.keys())}"
        )
        raise SchemaCompatibilityError(error_msg, missing_columns=missing_columns)

    type_mismatches = {}
    for col_name, plugin_type in plugin_fields.items():
        if col_name in datasource_fields:
            datasource_type = datasource_fields[col_name]

            plugin_type_unwrapped = _unwrap_optional(plugin_type)
            datasource_type_unwrapped = _unwrap_optional(datasource_type)

            if not _types_compatible(datasource_type_unwrapped, plugin_type_unwrapped):
                type_mismatches[col_name] = (
                    _type_name(datasource_type_unwrapped),
                    _type_name(plugin_type_unwrapped),
                )

    if type_mismatches:
        mismatch_details = "\n".join(
            [
                f"  - Column '{col}': datasource has {ds_type}, plugin expects {plugin_type}"
                for col, (ds_type, plugin_type) in type_mismatches.items()
            ]
        )
        error_msg = f"Plugin '{plugin_name}' has type mismatches with datasource:\n{mismatch_details}"
        raise SchemaCompatibilityError(error_msg, type_mismatches=type_mismatches)


def _unwrap_optional(type_hint: Any) -> Any:
    """
    Unwrap `T | None` to `T`, handling typing `Union` constructs.

    Uses `typing.get_origin` and `typing.get_args` for Pydantic v2 compatibility.
    """
    origin = typing.get_origin(type_hint)
    if origin is typing.Union:
        args = typing.get_args(type_hint)
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return non_none_types[0]

    return type_hint


def _types_compatible(datasource_type: Type, plugin_type: Type) -> bool:
    """
    Check if datasource type is compatible with plugin type.

    Compatibility rules:
    - Exact match: int == int
    - Numeric widening: int -> float (safe coercion)
    - String compatibility: str compatible with most types (parsing possible)
    """
    if datasource_type is plugin_type:
        return True

    if datasource_type is int and plugin_type is float:
        return True

    if datasource_type is str:
        return True

    return False


def _type_name(type_hint: Type) -> str:
    """Get human-readable name for a type."""
    if hasattr(type_hint, "__name__"):
        return type_hint.__name__
    return str(type_hint)
