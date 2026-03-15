# tests/unit/plugins/llm/test_validation.py
"""Tests for shared LLM validation helpers.

Covers:
- strip_markdown_fences: Markdown code block stripping
- validate_json_object_response: Tier 3 JSON object validation
- reject_nonfinite_constant: NaN/Infinity rejection
- validate_field_value: Output field type enforcement
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from elspeth.plugins.transforms.llm.multi_query import OutputFieldConfig, OutputFieldType
from elspeth.plugins.transforms.llm.validation import (
    ValidationError,
    ValidationSuccess,
    reject_nonfinite_constant,
    strip_markdown_fences,
    validate_field_value,
    validate_json_object_response,
)

# ── strip_markdown_fences tests ───────────────────────────────────


class TestStripMarkdownFences:
    """Tests for markdown code block fence removal."""

    def test_strip_markdown_fences_removes_triple_backtick(self) -> None:
        content = '```\n{"key": "value"}\n```'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_removes_language_tag(self) -> None:
        content = '```json\n{"key": "value"}\n```'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_noop_when_no_fences(self) -> None:
        content = '{"key": "value"}'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_trailing_whitespace_after_closing_fence(self) -> None:
        """Verify "```json\\n{}\\n``` " (trailing space) handled."""
        content = '```json\n{"key": "value"}\n```  '
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_no_closing_fence(self) -> None:
        """Content after opening fence is still returned when no closing fence."""
        content = '```json\n{"key": "value"}'
        result = strip_markdown_fences(content)
        assert result == '{"key": "value"}'

    def test_strip_markdown_fences_no_newline_after_opening(self) -> None:
        """Opening fence with no body (no newline) returns as-is."""
        content = "```json"
        result = strip_markdown_fences(content)
        # No newline found, so entire content after the ``` start is the "language tag"
        # Since there's no content after, it returns as-is (stripped)
        assert result == "```json"

    def test_strip_markdown_fences_preserves_inner_content(self) -> None:
        content = '```\n{\n  "a": 1,\n  "b": 2\n}\n```'
        result = strip_markdown_fences(content)
        assert result == '{\n  "a": 1,\n  "b": 2\n}'


# ── validate_json_object_response tests ──────────────────────────


class TestValidateJsonObjectResponse:
    """Tests for validate_json_object_response — Tier 3 boundary validation."""

    def test_valid_json_object_returns_success(self) -> None:
        """Valid JSON object should return ValidationSuccess with parsed dict."""
        result = validate_json_object_response('{"category": "spam", "score": 0.9}')
        assert isinstance(result, ValidationSuccess)
        assert result.data == {"category": "spam", "score": 0.9}

    def test_invalid_json_string_returns_error(self) -> None:
        """Malformed JSON should return ValidationError with reason=invalid_json."""
        result = validate_json_object_response("{not valid json}")
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json"
        assert result.detail is not None

    def test_json_array_returns_error(self) -> None:
        """JSON array should return ValidationError with reason=invalid_json_type."""
        result = validate_json_object_response("[1, 2, 3]")
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json_type"
        assert result.expected == "object"
        assert result.actual == "list"

    def test_json_null_returns_error(self) -> None:
        """JSON null should return ValidationError with reason=invalid_json_type."""
        result = validate_json_object_response("null")
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json_type"
        assert result.expected == "object"
        assert result.actual == "NoneType"

    def test_json_with_nan_returns_error(self) -> None:
        """JSON containing NaN should return ValidationError (reject_nonfinite_constant)."""
        result = validate_json_object_response('{"value": NaN}')
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json"
        assert result.detail is not None

    def test_empty_string_returns_error(self) -> None:
        """Empty string should return ValidationError."""
        result = validate_json_object_response("")
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json"

    def test_json_number_primitive_returns_error(self) -> None:
        """JSON number primitive should return ValidationError."""
        result = validate_json_object_response("42")
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json_type"
        assert result.expected == "object"
        assert result.actual == "int"

    def test_json_string_primitive_returns_error(self) -> None:
        """JSON string primitive should return ValidationError."""
        result = validate_json_object_response('"hello"')
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json_type"
        assert result.expected == "object"
        assert result.actual == "str"

    def test_json_boolean_primitive_returns_error(self) -> None:
        """JSON boolean should return ValidationError."""
        result = validate_json_object_response("true")
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json_type"
        assert result.expected == "object"
        assert result.actual == "bool"

    def test_json_with_infinity_returns_error(self) -> None:
        """JSON containing Infinity should return ValidationError."""
        result = validate_json_object_response('{"value": Infinity}')
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json"

    def test_json_with_negative_infinity_returns_error(self) -> None:
        """JSON containing -Infinity should return ValidationError."""
        result = validate_json_object_response('{"value": -Infinity}')
        assert isinstance(result, ValidationError)
        assert result.reason == "invalid_json"

    def test_nested_object_returns_success(self) -> None:
        """Nested JSON object should return ValidationSuccess with deep-frozen contents."""
        content = '{"outer": {"inner": "value"}, "list": [1, 2]}'
        result = validate_json_object_response(content)
        assert isinstance(result, ValidationSuccess)
        # deep_freeze converts inner dicts to MappingProxyType and lists to tuples
        assert result.data["outer"] == MappingProxyType({"inner": "value"})
        assert result.data["list"] == (1, 2)

    def test_empty_object_returns_success(self) -> None:
        """Empty JSON object {} should return ValidationSuccess."""
        result = validate_json_object_response("{}")
        assert isinstance(result, ValidationSuccess)
        assert result.data == {}


# ── reject_nonfinite_constant tests ──────────────────────────────


class TestRejectNonfiniteConstant:
    """Tests for reject_nonfinite_constant — parse_constant callback."""

    def test_nan_raises_value_error(self) -> None:
        """NaN should raise ValueError."""
        with pytest.raises(ValueError, match="NaN"):
            reject_nonfinite_constant("NaN")

    def test_infinity_raises_value_error(self) -> None:
        """Infinity should raise ValueError."""
        with pytest.raises(ValueError, match="Infinity"):
            reject_nonfinite_constant("Infinity")

    def test_negative_infinity_raises_value_error(self) -> None:
        """-Infinity should raise ValueError."""
        with pytest.raises(ValueError, match="-Infinity"):
            reject_nonfinite_constant("-Infinity")


# ── validate_field_value tests ──────────────────────────────────


class TestValidateFieldValue:
    """Tests for validate_field_value — Tier 3 type enforcement on LLM output fields."""

    def _field(self, type_: str, *, suffix: str = "f", values: list[str] | None = None) -> OutputFieldConfig:
        """Create an OutputFieldConfig for testing."""
        return OutputFieldConfig(suffix=suffix, type=OutputFieldType(type_), values=values)

    # -- STRING --

    def test_string_accepts_str(self) -> None:
        assert validate_field_value("hello", self._field("string")) is None

    def test_string_rejects_int(self) -> None:
        err = validate_field_value(42, self._field("string"))
        assert err is not None
        assert "expected string" in err

    def test_string_rejects_bool(self) -> None:
        err = validate_field_value(True, self._field("string"))
        assert err is not None
        assert "expected string" in err

    def test_string_rejects_none(self) -> None:
        err = validate_field_value(None, self._field("string"))
        assert err is not None

    # -- INTEGER --

    def test_integer_accepts_int(self) -> None:
        assert validate_field_value(42, self._field("integer")) is None

    def test_integer_accepts_float_with_integer_value(self) -> None:
        assert validate_field_value(42.0, self._field("integer")) is None

    def test_integer_rejects_bool(self) -> None:
        """bool is subclass of int — must be explicitly rejected."""
        err = validate_field_value(True, self._field("integer"))
        assert err is not None
        assert "boolean" in err

    def test_integer_rejects_string(self) -> None:
        err = validate_field_value("42", self._field("integer"))
        assert err is not None
        assert "expected integer" in err

    def test_integer_rejects_float_with_fraction(self) -> None:
        err = validate_field_value(3.14, self._field("integer"))
        assert err is not None

    def test_integer_rejects_nonfinite_float(self) -> None:
        err = validate_field_value(float("inf"), self._field("integer"))
        assert err is not None
        assert "non-finite" in err

    def test_integer_rejects_nan(self) -> None:
        err = validate_field_value(float("nan"), self._field("integer"))
        assert err is not None
        assert "non-finite" in err

    # -- NUMBER --

    def test_number_accepts_float(self) -> None:
        assert validate_field_value(3.14, self._field("number")) is None

    def test_number_accepts_int(self) -> None:
        assert validate_field_value(42, self._field("number")) is None

    def test_number_rejects_bool(self) -> None:
        err = validate_field_value(False, self._field("number"))
        assert err is not None
        assert "boolean" in err

    def test_number_rejects_string(self) -> None:
        err = validate_field_value("3.14", self._field("number"))
        assert err is not None

    def test_number_rejects_nonfinite_float(self) -> None:
        err = validate_field_value(float("-inf"), self._field("number"))
        assert err is not None
        assert "non-finite" in err

    # -- BOOLEAN --

    def test_boolean_accepts_true(self) -> None:
        assert validate_field_value(True, self._field("boolean")) is None

    def test_boolean_accepts_false(self) -> None:
        assert validate_field_value(False, self._field("boolean")) is None

    def test_boolean_rejects_int(self) -> None:
        err = validate_field_value(1, self._field("boolean"))
        assert err is not None
        assert "expected boolean" in err

    def test_boolean_rejects_string(self) -> None:
        err = validate_field_value("true", self._field("boolean"))
        assert err is not None

    # -- ENUM --

    def test_enum_accepts_valid_value(self) -> None:
        assert validate_field_value("A", self._field("enum", values=["A", "B"])) is None

    def test_enum_rejects_invalid_value(self) -> None:
        err = validate_field_value("C", self._field("enum", values=["A", "B"]))
        assert err is not None
        assert "not in allowed values" in err

    def test_enum_rejects_non_string(self) -> None:
        err = validate_field_value(1, self._field("enum", values=["1", "2"]))
        assert err is not None
        assert "expected string (enum)" in err
