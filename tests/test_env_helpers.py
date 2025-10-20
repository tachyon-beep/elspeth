"""Tests for environment variable helpers."""

import logging
import os
from unittest.mock import patch

import pytest

from elspeth.core.utils.env_helpers import get_env_var, require_env_var


class TestRequireEnvVar:
    """Tests for require_env_var function."""

    def test_require_env_var_success(self):
        """Test require_env_var returns value when set."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = require_env_var("TEST_VAR")
            assert result == "test_value"

    def test_require_env_var_strips_whitespace(self):
        """Test require_env_var strips whitespace by default."""
        with patch.dict(os.environ, {"TEST_VAR": "  test_value  "}):
            result = require_env_var("TEST_VAR")
            assert result == "test_value"

    def test_require_env_var_no_strip(self):
        """Test require_env_var preserves whitespace when strip=False."""
        with patch.dict(os.environ, {"TEST_VAR": "  test_value  "}):
            result = require_env_var("TEST_VAR", strip=False)
            assert result == "  test_value  "

    def test_require_env_var_missing_raises_error(self):
        """Test require_env_var raises ValueError when variable not set."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Environment variable MISSING_VAR not set"):
                require_env_var("MISSING_VAR")

    def test_require_env_var_empty_raises_error(self):
        """Test require_env_var raises ValueError when variable is empty."""
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            with pytest.raises(ValueError, match="Environment variable EMPTY_VAR not set"):
                require_env_var("EMPTY_VAR")

    def test_require_env_var_custom_error_message(self):
        """Test require_env_var uses custom error message."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Custom error: MISSING_VAR required"):
                require_env_var("MISSING_VAR", error_msg="Custom error: MISSING_VAR required")


class TestGetEnvVar:
    """Tests for get_env_var function."""

    def test_get_env_var_success(self):
        """Test get_env_var returns value when set."""
        with patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            result = get_env_var("TEST_VAR")
            assert result == "test_value"

    def test_get_env_var_strips_whitespace(self):
        """Test get_env_var strips whitespace by default."""
        with patch.dict(os.environ, {"TEST_VAR": "  test_value  "}):
            result = get_env_var("TEST_VAR")
            assert result == "test_value"

    def test_get_env_var_no_strip(self):
        """Test get_env_var preserves whitespace when strip=False."""
        with patch.dict(os.environ, {"TEST_VAR": "  test_value  "}):
            result = get_env_var("TEST_VAR", strip=False)
            assert result == "  test_value  "

    def test_get_env_var_missing_returns_default(self):
        """Test get_env_var returns default when variable not set."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_env_var("MISSING_VAR", default="fallback")
            assert result == "fallback"

    def test_get_env_var_missing_returns_none(self):
        """Test get_env_var returns None when no default provided."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_env_var("MISSING_VAR")
            assert result is None

    def test_get_env_var_empty_returns_default(self):
        """Test get_env_var returns default when variable is empty."""
        with patch.dict(os.environ, {"EMPTY_VAR": ""}):
            result = get_env_var("EMPTY_VAR", default="fallback")
            assert result == "fallback"

    def test_get_env_var_warns_when_missing(self, caplog):
        """Test get_env_var logs warning when warn_if_missing=True."""
        with patch.dict(os.environ, {}, clear=True):
            with caplog.at_level(logging.WARNING):
                result = get_env_var("MISSING_VAR", warn_if_missing=True)
                assert result is None
                assert "Environment variable MISSING_VAR not set" in caplog.text

    def test_get_env_var_no_warn_by_default(self, caplog):
        """Test get_env_var does not warn by default."""
        with patch.dict(os.environ, {}, clear=True):
            with caplog.at_level(logging.WARNING):
                result = get_env_var("MISSING_VAR")
                assert result is None
                assert "MISSING_VAR" not in caplog.text
