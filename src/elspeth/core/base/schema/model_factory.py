"""
Schema creation from configuration sources.

Utilities here translate YAML/JSON-style configuration dictionaries into
runtime Pydantic models backed by `DataFrameSchema`.
"""

from __future__ import annotations

from typing import Any, Type

import pandas as pd
from pydantic import Field, create_model

from .base import DataFrameSchema


def _parse_type_string(type_str: str) -> Type:
    """
    Parse type string from YAML config to Python type.

    Supported types:
    - "str", "string" → str
    - "int", "integer" → int
    - "float", "number" → float
    - "bool", "boolean" → bool
    - "datetime", "timestamp" → pd.Timestamp
    """
    type_lower = type_str.lower()

    type_map = {
        "str": str,
        "string": str,
        "int": int,
        "integer": int,
        "float": float,
        "number": float,
        "bool": bool,
        "boolean": bool,
        "datetime": pd.Timestamp,
        "timestamp": pd.Timestamp,
    }

    if type_lower not in type_map:
        raise ValueError(f"Unsupported type '{type_str}'. Supported types: {list(type_map.keys())}")

    return type_map[type_lower]


def schema_from_config(
    schema_dict: dict[str, str | dict[str, Any]],
    schema_name: str = "ConfigSchema",
) -> Type[DataFrameSchema]:
    """
    Build Pydantic schema from configuration dictionary.

    Supports both shorthand type strings and extended dicts that include
    constraints such as `required`, `min`, and `max`.

    Notes:
    - For string constraints, use `pattern` (Pydantic v2). The legacy `regex`
      key is not supported and will raise a ValueError to avoid pre-release
      tech debt.
    """
    fields: dict[str, tuple[Any, Any]] = {}

    for col_name, col_spec in schema_dict.items():
        # Handle simple string type
        if isinstance(col_spec, str):
            python_type = _parse_type_string(col_spec)
            fields[col_name] = (python_type, Field(...))  # Required by default
            continue

        # Extended dict format
        if not isinstance(col_spec, dict):
            raise ValueError(f"Column '{col_name}' spec must be string or dict, got {type(col_spec)}")

        if "type" not in col_spec:
            raise ValueError(f"Column '{col_name}' missing 'type' key")

        python_type = _parse_type_string(col_spec["type"])

        # Build Field with constraints
        field_kwargs: dict[str, Any] = {}

        # Required/optional handling
        is_optional = not col_spec.get("required", True)
        if is_optional:
            field_kwargs["default"] = None
            # Pydantic v2: Make type explicitly Optional
            python_type = python_type | None  # type: ignore[assignment]

        # Numeric constraints
        if "min" in col_spec:
            field_kwargs["ge"] = col_spec["min"]  # greater-or-equal
        if "max" in col_spec:
            field_kwargs["le"] = col_spec["max"]  # less-or-equal

        # String constraints
        if "min_length" in col_spec:
            field_kwargs["min_length"] = col_spec["min_length"]
        if "max_length" in col_spec:
            field_kwargs["max_length"] = col_spec["max_length"]
        # String pattern constraints (Pydantic v2 uses 'pattern' only)
        if "pattern" in col_spec:
            field_kwargs["pattern"] = col_spec["pattern"]
        if "regex" in col_spec:
            # No backward-compat in pre-release: fail fast to avoid tech debt
            # Require 'pattern' for Pydantic v2; reject legacy 'regex' key.
            raise ValueError("Column '%s' uses deprecated 'regex'; use 'pattern' for Pydantic v2" % col_name)

        if "default" not in field_kwargs:
            fields[col_name] = (python_type, Field(..., **field_kwargs))
        else:
            fields[col_name] = (python_type, Field(**field_kwargs))

    # Pydantic's create_model() has complex overloads that mypy cannot fully resolve
    # when using **fields with dynamic field definitions. This is safe at runtime.
    return create_model(  # type: ignore[call-overload,no-any-return]
        schema_name,
        __base__=DataFrameSchema,
        __config__=DataFrameSchema.model_config,  # Explicit v2 config inheritance
        **fields,
    )
