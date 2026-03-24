"""Tests for require_int — Tier 1 int-field validation utility."""

import pytest

from elspeth.contracts.freeze import require_int


class TestRequireInt:
    def test_accepts_int(self) -> None:
        require_int(42, "field")

    def test_accepts_zero(self) -> None:
        require_int(0, "field")

    def test_accepts_negative(self) -> None:
        require_int(-1, "field")

    def test_rejects_bool_true(self) -> None:
        with pytest.raises(TypeError, match=r"field must be int.*got bool"):
            require_int(True, "field")

    def test_rejects_bool_false(self) -> None:
        with pytest.raises(TypeError, match=r"field must be int.*got bool"):
            require_int(False, "field")

    def test_rejects_float(self) -> None:
        with pytest.raises(TypeError, match=r"field must be int.*got float"):
            require_int(42.0, "field")

    def test_rejects_str(self) -> None:
        with pytest.raises(TypeError, match=r"field must be int.*got str"):
            require_int("42", "field")

    def test_rejects_none(self) -> None:
        with pytest.raises(TypeError, match=r"field must be int.*got NoneType"):
            require_int(None, "field")

    def test_field_name_in_error(self) -> None:
        with pytest.raises(TypeError, match="my_field"):
            require_int("bad", "my_field")

    def test_value_in_error(self) -> None:
        with pytest.raises(TypeError, match="'bad'"):
            require_int("bad", "field")


class TestRequireIntNonNegative:
    def test_zero_passes(self) -> None:
        require_int(0, "field", min_value=0)

    def test_positive_passes(self) -> None:
        require_int(5, "field", min_value=0)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match=r"field must be >= 0.*got -1"):
            require_int(-1, "field", min_value=0)


class TestRequireIntOptional:
    def test_none_accepted_when_optional(self) -> None:
        require_int(None, "field", optional=True)

    def test_int_accepted_when_optional(self) -> None:
        require_int(42, "field", optional=True)

    def test_bool_rejected_when_optional(self) -> None:
        with pytest.raises(TypeError, match="got bool"):
            require_int(True, "field", optional=True)

    def test_str_rejected_when_optional(self) -> None:
        with pytest.raises(TypeError, match="got str"):
            require_int("42", "field", optional=True)
