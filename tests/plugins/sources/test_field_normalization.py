"""Tests for field normalization algorithm."""

import pytest


class TestNormalizeFieldName:
    """Unit tests for normalize_field_name function."""

    def test_basic_normalization_spaces_to_underscore(self) -> None:
        """Spaces are replaced with underscores."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("User ID") == "user_id"

    def test_basic_normalization_lowercase(self) -> None:
        """Mixed case is lowercased."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("CaSE Study1 !!!! xx!") == "case_study1_xx"

    def test_special_chars_replaced(self) -> None:
        """Special characters become underscores, collapsed."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("data.field") == "data_field"
        assert normalize_field_name("amount$$$") == "amount"

    def test_leading_digit_prefixed(self) -> None:
        """Leading digits get underscore prefix."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("123_field") == "_123_field"

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("  Amount  ") == "amount"

    def test_empty_result_raises_error(self) -> None:
        """Headers that normalize to empty raise ValueError."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        with pytest.raises(ValueError, match="normalizes to empty"):
            normalize_field_name("!!!")

    def test_algorithm_version_available(self) -> None:
        """Algorithm version is accessible for audit trail."""
        from elspeth.plugins.sources.field_normalization import (
            NORMALIZATION_ALGORITHM_VERSION,
            get_normalization_version,
        )

        assert NORMALIZATION_ALGORITHM_VERSION == "1.0.0"
        assert get_normalization_version() == "1.0.0"
