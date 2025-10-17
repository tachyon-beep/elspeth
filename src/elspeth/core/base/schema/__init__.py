"""
Public interface for DataFrame schema utilities.

This package splits the previous monolithic `schema.py` module into
dedicated units for base definitions, inference helpers, model factory
utilities, and validation routines.  All public objects continue to be
re-exported here so downstream imports using `elspeth.core.base.schema`
remain stable.
"""

from __future__ import annotations

from .base import DataFrameSchema, SchemaCompatibilityError, SchemaViolation
from .inference import infer_schema_from_dataframe
from .model_factory import schema_from_config
from .validation import validate_dataframe, validate_row, validate_schema_compatibility

__all__ = [
    "DataFrameSchema",
    "SchemaCompatibilityError",
    "SchemaViolation",
    "infer_schema_from_dataframe",
    "schema_from_config",
    "validate_dataframe",
    "validate_row",
    "validate_schema_compatibility",
]
