"""Tests for sink header mode configuration."""

import pytest

from elspeth.contracts.header_modes import HeaderMode
from elspeth.plugins.config_base import SinkPathConfig


class TestSinkHeaderConfig:
    """Test sink header mode parsing from config."""

    def test_default_is_normalized(self) -> None:
        """Default headers mode is normalized."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
            }
        )

        assert config.headers_mode == HeaderMode.NORMALIZED

    def test_headers_normalized(self) -> None:
        """headers: normalized parses correctly."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "normalized",
            }
        )

        assert config.headers_mode == HeaderMode.NORMALIZED

    def test_headers_original(self) -> None:
        """headers: original parses correctly."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "original",
            }
        )

        assert config.headers_mode == HeaderMode.ORIGINAL

    def test_headers_custom_dict(self) -> None:
        """headers: {mapping} parses as CUSTOM."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": {"amount_usd": "AMOUNT_USD"},
            }
        )

        assert config.headers_mode == HeaderMode.CUSTOM
        assert config.headers_mapping == {"amount_usd": "AMOUNT_USD"}

    def test_restore_source_headers_sets_original(self) -> None:
        """restore_source_headers=True sets ORIGINAL mode."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "restore_source_headers": True,
            }
        )

        assert config.headers_mode == HeaderMode.ORIGINAL

    def test_display_headers_sets_custom(self) -> None:
        """display_headers sets CUSTOM mode."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "display_headers": {"id": "ID"},
            }
        )

        assert config.headers_mode == HeaderMode.CUSTOM
        assert config.headers_mapping == {"id": "ID"}

    def test_headers_takes_precedence_over_restore(self) -> None:
        """headers setting takes precedence over restore_source_headers."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "normalized",
                "restore_source_headers": True,  # Should be ignored
            }
        )

        assert config.headers_mode == HeaderMode.NORMALIZED

    def test_headers_takes_precedence_over_display(self) -> None:
        """headers setting takes precedence over display_headers."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "original",
                "display_headers": {"id": "ID"},  # Should be ignored
            }
        )

        assert config.headers_mode == HeaderMode.ORIGINAL

    def test_headers_mapping_none_for_normalized(self) -> None:
        """headers_mapping is None for NORMALIZED mode."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "normalized",
            }
        )

        assert config.headers_mapping is None

    def test_headers_mapping_none_for_original(self) -> None:
        """headers_mapping is None for ORIGINAL mode."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "original",
            }
        )

        assert config.headers_mapping is None


class TestSinkHeaderConfigValidation:
    """Test validation edge cases for header config."""

    def test_invalid_headers_string_raises(self) -> None:
        """Invalid headers string raises ValueError."""
        with pytest.raises(Exception) as exc_info:
            SinkPathConfig.from_dict(
                {
                    "path": "output.csv",
                    "schema": {"mode": "observed"},
                    "headers": "invalid_mode",
                }
            )

        # The error should indicate invalid header mode
        assert "invalid" in str(exc_info.value).lower()

    def test_empty_custom_mapping_is_custom_mode(self) -> None:
        """Empty dict {} is still CUSTOM mode (explicit no mapping)."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": {},
            }
        )

        assert config.headers_mode == HeaderMode.CUSTOM
        assert config.headers_mapping == {}

    def test_headers_dict_with_restore_uses_headers(self) -> None:
        """headers dict takes precedence even when restore_source_headers is True."""
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": {"field": "FIELD"},
                "restore_source_headers": True,
            }
        )

        assert config.headers_mode == HeaderMode.CUSTOM
        assert config.headers_mapping == {"field": "FIELD"}

    def test_legacy_options_still_mutually_exclusive(self) -> None:
        """display_headers + restore_source_headers still rejects (without headers)."""
        with pytest.raises(Exception) as exc_info:
            SinkPathConfig.from_dict(
                {
                    "path": "output.csv",
                    "schema": {"mode": "observed"},
                    "display_headers": {"a": "A"},
                    "restore_source_headers": True,
                }
            )

        assert "both" in str(exc_info.value).lower()

    def test_headers_allows_both_legacy_options(self) -> None:
        """When headers is set, legacy mutual exclusion is bypassed."""
        # This should NOT raise because headers takes precedence
        config = SinkPathConfig.from_dict(
            {
                "path": "output.csv",
                "schema": {"mode": "observed"},
                "headers": "normalized",
                "display_headers": {"a": "A"},
                "restore_source_headers": True,
            }
        )

        assert config.headers_mode == HeaderMode.NORMALIZED
