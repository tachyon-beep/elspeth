# tests/engine/orchestrator/test_export.py
"""Tests for orchestrator export module - JSON schema type mapping.

These tests verify that _json_schema_to_python_type correctly handles
all Pydantic JSON schema patterns for pipeline resume functionality.

Bug: P2-2026-02-03-json-schema-type-mapping-gaps
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from elspeth.engine.orchestrator.export import _json_schema_to_python_type


class TestJsonSchemaToPythonType:
    """Test _json_schema_to_python_type handles all Pydantic patterns."""

    # =========================================================================
    # Primitive types (already working)
    # =========================================================================

    def test_string_type(self) -> None:
        """String type maps correctly."""
        result = _json_schema_to_python_type("name", {"type": "string"})
        assert result is str

    def test_integer_type(self) -> None:
        """Integer type maps correctly."""
        result = _json_schema_to_python_type("count", {"type": "integer"})
        assert result is int

    def test_number_type(self) -> None:
        """Number type maps to float."""
        result = _json_schema_to_python_type("price", {"type": "number"})
        assert result is float

    def test_boolean_type(self) -> None:
        """Boolean type maps correctly."""
        result = _json_schema_to_python_type("active", {"type": "boolean"})
        assert result is bool

    # =========================================================================
    # Datetime with format (partially working)
    # =========================================================================

    def test_datetime_format(self) -> None:
        """date-time format maps to datetime."""
        result = _json_schema_to_python_type("created_at", {"type": "string", "format": "date-time"})
        assert result is datetime

    def test_date_format(self) -> None:
        """date format maps to date."""
        result = _json_schema_to_python_type("birth_date", {"type": "string", "format": "date"})
        assert result is date

    def test_time_format(self) -> None:
        """time format maps to time."""
        result = _json_schema_to_python_type("start_time", {"type": "string", "format": "time"})
        assert result is time

    def test_duration_format(self) -> None:
        """duration format maps to timedelta."""
        result = _json_schema_to_python_type("duration", {"type": "string", "format": "duration"})
        assert result is timedelta

    def test_uuid_format(self) -> None:
        """uuid format maps to UUID."""
        result = _json_schema_to_python_type("user_id", {"type": "string", "format": "uuid"})
        assert result is UUID

    # =========================================================================
    # Decimal (anyOf pattern - already working)
    # =========================================================================

    def test_decimal_anyof_pattern(self) -> None:
        """Decimal's anyOf pattern maps correctly."""
        # Pydantic emits: {"anyOf": [{"type": "number"}, {"type": "string", ...}]}
        result = _json_schema_to_python_type(
            "amount",
            {"anyOf": [{"type": "number"}, {"type": "string"}]},
        )
        assert result is Decimal

    # =========================================================================
    # Nullable types (anyOf with null - BUG: currently crashes)
    # =========================================================================

    def test_nullable_string(self) -> None:
        """str | None maps correctly from anyOf with null."""
        # Pydantic emits: {"anyOf": [{"type": "string"}, {"type": "null"}]}
        result = _json_schema_to_python_type(
            "optional_str",
            {"anyOf": [{"type": "string"}, {"type": "null"}]},
        )
        # Should return str (the non-null type) - Optional is handled by required/default
        assert result is str

    def test_nullable_integer(self) -> None:
        """int | None maps correctly from anyOf with null."""
        result = _json_schema_to_python_type(
            "optional_int",
            {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        )
        assert result is int

    def test_nullable_number(self) -> None:
        """float | None maps correctly from anyOf with null."""
        result = _json_schema_to_python_type(
            "optional_float",
            {"anyOf": [{"type": "number"}, {"type": "null"}]},
        )
        assert result is float

    def test_nullable_boolean(self) -> None:
        """bool | None maps correctly from anyOf with null."""
        result = _json_schema_to_python_type(
            "optional_bool",
            {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
        )
        assert result is bool

    def test_nullable_datetime(self) -> None:
        """datetime | None maps correctly from anyOf with null."""
        # Pydantic emits: {"anyOf": [{"format": "date-time", "type": "string"}, {"type": "null"}]}
        result = _json_schema_to_python_type(
            "optional_datetime",
            {"anyOf": [{"type": "string", "format": "date-time"}, {"type": "null"}]},
        )
        assert result is datetime

    def test_nullable_date(self) -> None:
        """date | None maps correctly from anyOf with null."""
        result = _json_schema_to_python_type(
            "optional_date",
            {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
        )
        assert result is date

    def test_nullable_uuid(self) -> None:
        """UUID | None maps correctly from anyOf with null."""
        result = _json_schema_to_python_type(
            "optional_uuid",
            {"anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]},
        )
        assert result is UUID

    # =========================================================================
    # Collection types
    # =========================================================================

    def test_array_type(self) -> None:
        """Array type maps to list."""
        result = _json_schema_to_python_type("items", {"type": "array", "items": {"type": "string"}})
        assert result is list

    def test_array_without_items(self) -> None:
        """Array without items schema maps to list."""
        result = _json_schema_to_python_type("items", {"type": "array"})
        assert result is list

    def test_object_type(self) -> None:
        """Object type maps to dict."""
        result = _json_schema_to_python_type("metadata", {"type": "object"})
        assert result is dict

    # =========================================================================
    # Error cases
    # =========================================================================

    def test_unknown_type_raises(self) -> None:
        """Unknown type raises ValueError."""
        with pytest.raises(ValueError, match="unsupported type"):
            _json_schema_to_python_type("field", {"type": "unknown"})

    def test_missing_type_key_raises(self) -> None:
        """Schema without type key raises ValueError (unless anyOf)."""
        with pytest.raises(ValueError, match="has no 'type'"):
            _json_schema_to_python_type("field", {"format": "date"})

    def test_unsupported_anyof_raises(self) -> None:
        """Unsupported anyOf pattern raises ValueError."""
        # Multiple non-null types that aren't Decimal pattern
        with pytest.raises(ValueError, match="unsupported anyOf"):
            _json_schema_to_python_type(
                "field",
                {"anyOf": [{"type": "string"}, {"type": "integer"}]},
            )
