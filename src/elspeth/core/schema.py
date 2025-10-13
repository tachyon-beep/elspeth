"""
DataFrame schema validation using Pydantic.

This module provides:
- DataFrameSchema base class for type-safe column declarations
- Schema inference from pandas DataFrames
- Schema construction from YAML configuration
- Row-level validation with detailed error reporting
"""

from __future__ import annotations

import logging
import typing
from typing import Any, Dict, List, Optional, Tuple, Type

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class SchemaCompatibilityError(ValueError):
    """
    Raised when datasource schema is incompatible with plugin requirements.

    This error is raised at config-time when:
    - Plugin requires columns that datasource doesn't provide
    - Column types are incompatible between datasource and plugin
    """

    def __init__(
        self, message: str, *, missing_columns: List[str] | None = None, type_mismatches: Dict[str, tuple[str, str]] | None = None
    ):
        super().__init__(message)
        self.missing_columns = missing_columns or []
        self.type_mismatches = type_mismatches or {}


class DataFrameSchema(BaseModel):
    """
    Base class for DataFrame column schemas.

    Subclass this to declare expected DataFrame columns with types:

        class MySchema(DataFrameSchema):
            APPID: str
            question: str
            score: int

    Configuration:
        - extra="allow": Allows undeclared columns (non-strict mode)
        - arbitrary_types_allowed: Supports pandas types if needed
    """

    model_config = ConfigDict(
        extra="allow",  # Allow undeclared columns by default
        arbitrary_types_allowed=True,
    )


class SchemaViolation:
    """
    Represents a schema validation failure for a single row.

    Captures:
    - Row index in DataFrame
    - Raw row data that failed validation
    - Detailed Pydantic validation errors
    - Schema name for debugging
    - Timestamp of violation
    """

    def __init__(
        self,
        row_index: int,
        row_data: Dict[str, Any],
        errors: List[Dict[str, Any]],
        schema_name: str,
    ):
        self.row_index = row_index
        self.row_data = row_data
        self.errors = errors  # List of Pydantic error dicts
        self.schema_name = schema_name
        self.timestamp = pd.Timestamp.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for sink writing."""
        return {
            "row_index": self.row_index,
            "schema_name": self.schema_name,
            "timestamp": self.timestamp.isoformat(),
            "validation_errors": self.errors,
            "malformed_data": self.row_data,
        }

    def __repr__(self) -> str:
        error_fields = [e["field"] for e in self.errors]
        return f"SchemaViolation(row={self.row_index}, schema={self.schema_name}, fields={error_fields})"


def _pandas_dtype_to_python(dtype: pd.api.types.DtypeArg) -> Type:
    """
    Convert pandas dtype to Python type for Pydantic schema.

    Args:
        dtype: Pandas dtype object

    Returns:
        Corresponding Python type (str, int, float, bool, or object)
    """
    dtype_str = str(dtype)

    if pd.api.types.is_integer_dtype(dtype):
        return int
    elif pd.api.types.is_float_dtype(dtype):
        return float
    elif pd.api.types.is_bool_dtype(dtype):
        return bool
    elif pd.api.types.is_string_dtype(dtype) or dtype_str == "object":
        return str
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return pd.Timestamp
    else:
        logger.warning(f"Unknown dtype {dtype}, defaulting to str")
        return str


def infer_schema_from_dataframe(
    df: pd.DataFrame,
    schema_name: str = "InferredSchema",
    *,
    required_columns: Optional[List[str]] = None,
) -> Type[DataFrameSchema]:
    """
    Infer Pydantic schema from DataFrame column dtypes.

    Args:
        df: DataFrame to infer schema from
        schema_name: Name for the generated schema class
        required_columns: If provided, only these columns are marked as required

    Returns:
        Dynamically created DataFrameSchema subclass

    Example:
        >>> df = pd.DataFrame({"name": ["Alice"], "age": [30]})
        >>> Schema = infer_schema_from_dataframe(df, "PersonSchema")
        >>> Schema.__annotations__
        {'name': <class 'str'>, 'age': <class 'int'>}
    """
    fields: Dict[str, tuple] = {}

    for col in df.columns:
        dtype = df[col].dtype
        python_type = _pandas_dtype_to_python(dtype)

        # Check if column should be required
        is_required = required_columns is None or col in required_columns

        if is_required:
            fields[col] = (python_type, Field(...))  # Required field
        else:
            # Pydantic v2 requires explicit Optional for optional fields
            fields[col] = (Optional[python_type], Field(default=None))  # Optional field

    return create_model(
        schema_name,
        __base__=DataFrameSchema,
        __config__=DataFrameSchema.model_config,  # Explicit v2 config inheritance
        **fields,
    )


def _parse_type_string(type_str: str) -> Type:
    """
    Parse type string from YAML config to Python type.

    Supported types:
    - "str", "string" → str
    - "int", "integer" → int
    - "float", "number" → float
    - "bool", "boolean" → bool
    - "datetime", "timestamp" → pd.Timestamp

    Args:
        type_str: Type string from config

    Returns:
        Python type class

    Raises:
        ValueError: If type string is unrecognized
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
        raise ValueError(f"Unsupported type '{type_str}'. " f"Supported types: {list(type_map.keys())}")

    return type_map[type_lower]


def schema_from_config(
    schema_dict: Dict[str, str | Dict[str, Any]],
    schema_name: str = "ConfigSchema",
) -> Type[DataFrameSchema]:
    """
    Build Pydantic schema from configuration dictionary.

    Supports two formats:

    1. Simple type strings:
        schema:
          APPID: str
          score: int

    2. Extended format with constraints:
        schema:
          APPID:
            type: str
            required: true
          score:
            type: int
            min: 0
            max: 100

    Args:
        schema_dict: Column definitions from YAML config
        schema_name: Name for the generated schema class

    Returns:
        Dynamically created DataFrameSchema subclass

    Raises:
        ValueError: If type specification is invalid

    Example:
        >>> config = {"name": "str", "age": {"type": "int", "min": 0}}
        >>> Schema = schema_from_config(config, "PersonSchema")
    """
    fields: Dict[str, tuple] = {}

    for col_name, col_spec in schema_dict.items():
        # Handle simple string type
        if isinstance(col_spec, str):
            python_type = _parse_type_string(col_spec)
            fields[col_name] = (python_type, Field(...))  # Required by default
            continue

        # Handle extended dict format
        if not isinstance(col_spec, dict):
            raise ValueError(f"Column '{col_name}' spec must be string or dict, got {type(col_spec)}")

        # Parse type
        if "type" not in col_spec:
            raise ValueError(f"Column '{col_name}' missing 'type' key")

        python_type = _parse_type_string(col_spec["type"])

        # Build Field with constraints
        field_kwargs: Dict[str, Any] = {}

        # Required/optional handling
        is_optional = not col_spec.get("required", True)
        if is_optional:
            field_kwargs["default"] = None
            # Pydantic v2: Make type explicitly Optional
            python_type = Optional[python_type]

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
        if "pattern" in col_spec:
            field_kwargs["regex"] = col_spec["pattern"]

        # Create field
        if "default" not in field_kwargs:
            fields[col_name] = (python_type, Field(..., **field_kwargs))
        else:
            fields[col_name] = (python_type, Field(**field_kwargs))

    return create_model(
        schema_name,
        __base__=DataFrameSchema,
        __config__=DataFrameSchema.model_config,  # Explicit v2 config inheritance
        **fields,
    )


def validate_row(
    row: Dict[str, Any],
    schema: Type[DataFrameSchema],
    *,
    row_index: int = 0,
) -> Tuple[bool, Optional[SchemaViolation]]:
    """
    Validate a single row against a schema.

    Args:
        row: Dictionary representing a DataFrame row
        schema: DataFrameSchema subclass to validate against
        row_index: Row number in DataFrame (for error reporting)

    Returns:
        Tuple of (is_valid, violation_or_none)
        - (True, None) if row is valid
        - (False, SchemaViolation) if row has validation errors

    Example:
        >>> schema = schema_from_config({"name": "str", "age": "int"})
        >>> valid, violation = validate_row({"name": "Alice", "age": 30}, schema)
        >>> valid
        True
        >>> valid, violation = validate_row({"name": "Bob", "age": "invalid"}, schema)
        >>> valid
        False
        >>> violation.errors[0]["field"]
        'age'
    """
    try:
        # Attempt to validate row using Pydantic v2 model_validate
        schema.model_validate(row)
        return (True, None)

    except PydanticValidationError as e:
        # Convert Pydantic errors to structured format
        errors = []
        for error in e.errors():
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
) -> Tuple[bool, List[SchemaViolation]]:
    """
    Validate all rows in a DataFrame against a schema.

    Args:
        df: DataFrame to validate
        schema: DataFrameSchema subclass to validate against
        early_stop: If True, stop on first error; if False, collect all errors

    Returns:
        Tuple of (is_valid, violations)
        - (True, []) if all rows are valid
        - (False, [violations]) if any rows have errors

    Example:
        >>> df = pd.DataFrame([
        ...     {"name": "Alice", "age": 30},
        ...     {"name": "Bob", "age": "invalid"},
        ... ])
        >>> schema = schema_from_config({"name": "str", "age": "int"})
        >>> valid, violations = validate_dataframe(df, schema, early_stop=False)
        >>> valid
        False
        >>> len(violations)
        1
        >>> violations[0].row_index
        1
    """
    violations = []

    for idx, (_, row) in enumerate(df.iterrows()):
        row_dict = row.to_dict()
        is_valid, violation = validate_row(row_dict, schema, row_index=idx)

        if not is_valid:
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
    1. All required columns in plugin_schema exist in datasource_schema
    2. Column types are compatible (exact match or compatible subtypes)

    Args:
        datasource_schema: Schema produced by datasource
        plugin_schema: Schema required by plugin
        plugin_name: Name of plugin for error messages

    Raises:
        SchemaCompatibilityError: If schemas are incompatible

    Example:
        >>> ds_schema = schema_from_config({"name": "str", "age": "int", "city": "str"})
        >>> plugin_schema = schema_from_config({"name": "str", "age": "int"})
        >>> validate_schema_compatibility(ds_schema, plugin_schema)
        # No error - datasource has all required columns

        >>> plugin_schema2 = schema_from_config({"name": "str", "score": "int"})
        >>> validate_schema_compatibility(ds_schema, plugin_schema2)
        SchemaCompatibilityError: Plugin 'plugin' requires column 'score' not provided by datasource
    """
    # Extract field annotations from both schemas
    datasource_fields = {}
    if hasattr(datasource_schema, "__annotations__"):
        datasource_fields = datasource_schema.__annotations__.copy()

    plugin_fields = {}
    if hasattr(plugin_schema, "__annotations__"):
        plugin_fields = plugin_schema.__annotations__.copy()

    # Check for missing columns
    missing_columns = []
    for col_name, plugin_type in plugin_fields.items():
        if col_name not in datasource_fields:
            missing_columns.append(col_name)

    if missing_columns:
        error_msg = (
            f"Plugin '{plugin_name}' requires columns not provided by datasource: {missing_columns}\n"
            f"Datasource provides: {list(datasource_fields.keys())}\n"
            f"Plugin requires: {list(plugin_fields.keys())}"
        )
        raise SchemaCompatibilityError(error_msg, missing_columns=missing_columns)

    # Check for type mismatches
    type_mismatches = {}
    for col_name, plugin_type in plugin_fields.items():
        if col_name in datasource_fields:
            datasource_type = datasource_fields[col_name]

            # Unwrap Optional types for comparison
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
    Unwrap Optional[T] to T, handling Union types.

    Args:
        type_hint: Type hint potentially wrapped in Optional

    Returns:
        Unwrapped type

    Note:
        Uses typing.get_origin and typing.get_args for Pydantic v2 compatibility.
    """
    # Handle Union types (Optional[T] is Union[T, None])
    origin = typing.get_origin(type_hint)
    if origin is typing.Union:
        # Get the non-None type from Union
        args = typing.get_args(type_hint)
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return non_none_types[0]

    return type_hint


def _types_compatible(datasource_type: Type, plugin_type: Type) -> bool:
    """
    Check if datasource type is compatible with plugin type.

    Args:
        datasource_type: Type provided by datasource
        plugin_type: Type expected by plugin

    Returns:
        True if compatible, False otherwise

    Compatibility rules:
    - Exact match: int == int
    - Numeric widening: int -> float (safe coercion)
    - String compatibility: str compatible with most types (parsing possible)
    """
    # Exact match
    if datasource_type is plugin_type:
        return True

    # Numeric widening: int -> float is safe
    if datasource_type is int and plugin_type is float:
        return True

    # String source can be parsed to most types (permissive for CSV data)
    if datasource_type is str:
        return True  # Assume parsing is possible

    # Otherwise incompatible
    return False


def _type_name(type_hint: Type) -> str:
    """Get human-readable name for a type."""
    if hasattr(type_hint, "__name__"):
        return type_hint.__name__
    return str(type_hint)
