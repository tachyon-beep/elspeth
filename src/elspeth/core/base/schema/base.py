"""
Base definitions for DataFrame schema handling.

Provides the shared error types and base Pydantic model that the
inference, model factory, and validation layers rely on.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict


class SchemaCompatibilityError(ValueError):
    """
    Raised when datasource schema is incompatible with plugin requirements.

    This error is raised at config-time when:
    - Plugin requires columns that datasource doesn't provide
    - Column types are incompatible between datasource and plugin
    """

    def __init__(
        self,
        message: str,
        *,
        missing_columns: list[str] | None = None,
        type_mismatches: dict[str, tuple[str, str]] | None = None,
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
        row_data: dict[str, Any],
        errors: list[dict[str, Any]],
        schema_name: str,
    ):
        self.row_index = row_index
        self.row_data = row_data
        self.errors = errors  # List of Pydantic error dicts
        self.schema_name = schema_name
        self.timestamp = pd.Timestamp.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for sink writing."""
        return {
            "row_index": self.row_index,
            "schema_name": self.schema_name,
            "timestamp": self.timestamp.isoformat(),
            "validation_errors": self.errors,
            "malformed_data": self.row_data,
        }

    def __repr__(self) -> str:
        """Return a concise representation including row and failing fields."""
        error_fields = [e["field"] for e in self.errors]
        return f"SchemaViolation(row={self.row_index}, schema={self.schema_name}, fields={error_fields})"
