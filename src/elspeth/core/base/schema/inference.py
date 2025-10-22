"""
Schema inference helpers.

Includes utilities for mapping pandas dtypes to Python types and building
runtime Pydantic models that represent a dataframe's structure.
"""

from __future__ import annotations

import logging
from typing import Any, Type, cast

import pandas as pd
from pydantic import Field, create_model

from .base import DataFrameSchema

logger = logging.getLogger(__name__)


def _pandas_dtype_to_python(dtype: Any) -> Type:
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
    if pd.api.types.is_float_dtype(dtype):
        return float
    if pd.api.types.is_bool_dtype(dtype):
        return bool
    if pd.api.types.is_string_dtype(dtype) or dtype_str == "object":
        return str
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return pd.Timestamp

    logger.warning("Unknown dtype %s, defaulting to str", dtype)
    return str


def infer_schema_from_dataframe(
    df: pd.DataFrame,
    schema_name: str = "InferredSchema",
    *,
    required_columns: list[str | None] | None = None,
) -> Type[DataFrameSchema]:
    """
    Infer Pydantic schema from DataFrame column dtypes.

    Args:
        df: DataFrame to infer schema from
        schema_name: Name for the generated schema class
        required_columns: If provided, only these columns are marked as required

    Returns:
        Dynamically created DataFrameSchema subclass
    """
    fields: dict[str, tuple[Any, Any]] = {}

    for col in df.columns:
        dtype = df[col].dtype
        python_type = _pandas_dtype_to_python(dtype)

        # Check if column should be required
        is_required = required_columns is None or col in required_columns

        if is_required:
            fields[col] = (python_type, Field(...))  # Required field
        else:
            # Pydantic v2 requires explicit Optional for optional fields
            fields[col] = (python_type | None, Field(default=None))  # Optional field

    # Pydantic's create_model() has complex overloads; static checkers may misinterpret
    # the dynamic **fields. Cast create_model to Any to suppress spurious type errors.
    cm = cast(Any, create_model)
    return cm(  # type: ignore[no-any-return]
        schema_name,
        __base__=DataFrameSchema,
        __config__=DataFrameSchema.model_config,  # Explicit v2 config inheritance
        **fields,
    )
