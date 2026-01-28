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

    def test_unicode_bom_stripped(self) -> None:
        """BOM character at start is stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("\ufeffid") == "id"

    def test_zero_width_chars_stripped(self) -> None:
        """Zero-width characters are stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("id\u200b") == "id"

    def test_emoji_stripped(self) -> None:
        """Emoji characters are stripped."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("Status 🔥") == "status"

    def test_python_keyword_gets_suffix(self) -> None:
        """Python keywords get underscore suffix."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("class") == "class_"
        assert normalize_field_name("for") == "for_"
        assert normalize_field_name("import") == "import_"

    def test_header_normalizing_to_keyword_gets_suffix(self) -> None:
        """Headers that normalize to keywords also get suffix."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("CLASS") == "class_"
        assert normalize_field_name("For ") == "for_"

    def test_accented_chars_preserved(self) -> None:
        """Accented characters are valid identifiers (PEP 3131)."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        assert normalize_field_name("café") == "café"
        assert normalize_field_name("naïve") == "naïve"

    def test_unicode_nfc_normalization_consistent(self) -> None:
        """Unicode characters in different forms normalize to same result."""
        from elspeth.plugins.sources.field_normalization import normalize_field_name

        # "é" can be: precomposed U+00E9, or decomposed U+0065 U+0301
        precomposed = "café"
        decomposed = "caf\u0065\u0301"

        assert precomposed != decomposed  # Different byte representations
        assert normalize_field_name(precomposed) == normalize_field_name(decomposed)
