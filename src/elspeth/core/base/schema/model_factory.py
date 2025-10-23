"""
Schema creation from configuration sources.

Utilities here translate YAML/JSON-style configuration dictionaries into
runtime Pydantic models backed by `DataFrameSchema`.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import Field, create_model

from .base import DataFrameSchema


def _parse_type_string(type_str: str) -> type[Any]:
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
) -> type[DataFrameSchema]:
    """
    Build Pydantic schema from configuration dictionary.

    Supports both shorthand type strings and extended dicts that include
    constraints such as `required`, `min`, and `max`.

    Notes:
    - For string constraints, use `pattern` (Pydantic v2 >= 2.12.2). The legacy
      `regex` key is not supported and will raise a ValueError to avoid carrying
      pre‑release technical debt.
    """
    # Use Any for values to satisfy static checkers when splatting into create_model(**fields)
    # (Pylance may otherwise attempt to match these against reserved kwargs like __doc__/__module__).
    fields: dict[str, Any] = {}

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
        # Pydantic v2 uses 'pattern' for string pattern constraints (v1 used 'regex').
        # We do not support 'regex' to avoid carrying dual behavior pre‑1.0.
        pattern_value = None
        if "pattern" in col_spec:
            pattern_value = col_spec["pattern"]
        elif "regex" in col_spec:
            raise ValueError(f"Column '{col_name}' uses unsupported 'regex'; use 'pattern' for Pydantic v2")
        if pattern_value is not None:
            field_kwargs["pattern"] = pattern_value

        # Choose the correct annotation, keeping the local python_type unchanged to
        # avoid type-reassignment noise for type checkers.
        annotation: Any = (python_type | None) if is_optional else python_type

        if "default" not in field_kwargs:
            fields[col_name] = (annotation, Field(..., **field_kwargs))
        else:
            fields[col_name] = (annotation, Field(**field_kwargs))

    # Pydantic's create_model() has complex overloads that mypy cannot fully resolve
    # when using **fields with dynamic field definitions. This is safe at runtime.
    return create_model(
        schema_name,
        __base__=DataFrameSchema,
        __config__=DataFrameSchema.model_config,  # Explicit v2 config inheritance
        **fields,
    )
