# tests/core/security/test_fingerprint_keyvault.py
"""Tests for fingerprint key retrieval - simplified env var only approach.

BREAKING CHANGE: The old ELSPETH_KEYVAULT_URL and ELSPETH_KEYVAULT_SECRET_NAME
environment variables are NO LONGER recognized. Users must migrate to the
YAML-based secrets configuration.

These tests verify:
1. Only ELSPETH_FINGERPRINT_KEY env var is recognized
2. Old Key Vault env vars are NOT recognized (breaking change)
3. Error messages guide users to the new approach
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from elspeth.core.security.fingerprint import (
    _ENV_VAR,
    get_fingerprint_key,
    secret_fingerprint,
)


class TestFingerprintKeyEnvVarOnly:
    """Tests verifying fingerprint key only uses ELSPETH_FINGERPRINT_KEY env var."""

    def test_get_key_from_env_var(self) -> None:
        """get_fingerprint_key() reads from ELSPETH_FINGERPRINT_KEY."""
        with patch.dict(os.environ, {_ENV_VAR: "my-secret-key"}):
            key = get_fingerprint_key()
            assert key == b"my-secret-key"

    def test_raises_when_env_var_missing(self) -> None:
        """Raises ValueError when ELSPETH_FINGERPRINT_KEY not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_VAR, None)

            with pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
                get_fingerprint_key()

    def test_empty_env_var_raises(self) -> None:
        """Empty string env var should raise ValueError."""
        with patch.dict(os.environ, {_ENV_VAR: ""}), pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
            get_fingerprint_key()

    def test_whitespace_only_env_var_is_valid(self) -> None:
        """Whitespace-only env var is used as-is (user's responsibility).

        Note: While empty string is rejected, whitespace-only strings
        are technically valid (the user configured something).
        """
        with patch.dict(os.environ, {_ENV_VAR: "   "}):
            key = get_fingerprint_key()
            assert key == b"   "

    def test_error_message_guides_to_secrets_config(self) -> None:
        """Error message should mention YAML secrets configuration."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_VAR, None)

            with pytest.raises(ValueError) as exc_info:
                get_fingerprint_key()

            error_msg = str(exc_info.value)
            # Should mention the env var
            assert "ELSPETH_FINGERPRINT_KEY" in error_msg
            # Should mention the new secrets config approach
            assert "secrets" in error_msg.lower()


class TestOldKeyVaultEnvVarsNotRecognized:
    """Tests verifying old Key Vault env vars are NOT recognized.

    BREAKING CHANGE: ELSPETH_KEYVAULT_URL and ELSPETH_KEYVAULT_SECRET_NAME
    no longer trigger Key Vault lookups from fingerprint.py. Users must
    migrate to the YAML-based secrets configuration.
    """

    def test_keyvault_url_env_var_not_recognized(self) -> None:
        """ELSPETH_KEYVAULT_URL alone does NOT trigger Key Vault lookup.

        Previously, setting ELSPETH_KEYVAULT_URL would cause fingerprint.py
        to attempt a Key Vault lookup. This is no longer the case.
        """
        with patch.dict(
            os.environ,
            {"ELSPETH_KEYVAULT_URL": "https://my-vault.vault.azure.net"},
            clear=False,
        ):
            os.environ.pop(_ENV_VAR, None)

            # Should raise because ELSPETH_FINGERPRINT_KEY is not set
            # NOT attempt a Key Vault lookup
            with pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
                get_fingerprint_key()

    def test_keyvault_secret_name_env_var_not_recognized(self) -> None:
        """ELSPETH_KEYVAULT_SECRET_NAME is NOT recognized.

        This env var was used to customize the secret name in Key Vault.
        It's no longer recognized - users must use YAML secrets config.
        """
        with patch.dict(
            os.environ,
            {
                "ELSPETH_KEYVAULT_URL": "https://my-vault.vault.azure.net",
                "ELSPETH_KEYVAULT_SECRET_NAME": "custom-fingerprint-key",
            },
            clear=False,
        ):
            os.environ.pop(_ENV_VAR, None)

            # Should raise because ELSPETH_FINGERPRINT_KEY is not set
            with pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
                get_fingerprint_key()

    def test_fingerprint_key_takes_precedence_always(self) -> None:
        """ELSPETH_FINGERPRINT_KEY is always used when set.

        Even with old Key Vault env vars present, the direct env var is used.
        """
        with patch.dict(
            os.environ,
            {
                _ENV_VAR: "direct-env-key",
                "ELSPETH_KEYVAULT_URL": "https://my-vault.vault.azure.net",
                "ELSPETH_KEYVAULT_SECRET_NAME": "ignored-secret-name",
            },
        ):
            key = get_fingerprint_key()
            assert key == b"direct-env-key"


class TestSecretFingerprintFunction:
    """Tests for the secret_fingerprint() convenience function."""

    def test_fingerprint_returns_hex_string(self) -> None:
        """Fingerprint should be a hex string."""
        result = secret_fingerprint("my-api-key", key=b"test-key")
        assert isinstance(result, str)
        assert all(c in "0123456789abcdef" for c in result)

    def test_fingerprint_is_deterministic(self) -> None:
        """Same secret + same key = same fingerprint."""
        key = b"test-key"
        fp1 = secret_fingerprint("my-secret", key=key)
        fp2 = secret_fingerprint("my-secret", key=key)
        assert fp1 == fp2

    def test_different_secrets_have_different_fingerprints(self) -> None:
        """Different secrets should produce different fingerprints."""
        key = b"test-key"
        fp1 = secret_fingerprint("secret-a", key=key)
        fp2 = secret_fingerprint("secret-b", key=key)
        assert fp1 != fp2

    def test_different_keys_produce_different_fingerprints(self) -> None:
        """Same secret with different keys should differ."""
        fp1 = secret_fingerprint("my-secret", key=b"key-1")
        fp2 = secret_fingerprint("my-secret", key=b"key-2")
        assert fp1 != fp2

    def test_fingerprint_length_is_64_chars(self) -> None:
        """SHA256 hex digest is 64 characters."""
        result = secret_fingerprint("test", key=b"key")
        assert len(result) == 64

    def test_fingerprint_golden_vector(self) -> None:
        """Verify HMAC-SHA256 algorithm with known test vector.

        This locks the algorithm to HMAC-SHA256. If the implementation
        changes to plain SHA256 or another algorithm, this test will fail.
        """
        result = secret_fingerprint("my-secret", key=b"test-key")

        # Precomputed: hmac.new(b"test-key", b"my-secret", sha256).hexdigest()
        expected = "2294b9e7a6dcb8be10f155c556b2ca74f419c7bd2ce6e1beec723751498f73c2"
        assert result == expected

    def test_fingerprint_without_key_uses_env_var(self) -> None:
        """When key not provided, uses ELSPETH_FINGERPRINT_KEY env var."""
        with patch.dict(os.environ, {_ENV_VAR: "env-key-value"}):
            result = secret_fingerprint("my-secret")

            # Precomputed: hmac.new(b"env-key-value", b"my-secret", sha256).hexdigest()
            expected = "9bbccfbb68be10d7a8b2649a63b421167e1c05cd78e52fe2761f1743691c5630"
            assert result == expected

    def test_fingerprint_without_key_raises_if_env_missing(self) -> None:
        """Raises ValueError if no key provided and env var missing."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_VAR, None)

            with pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
                secret_fingerprint("my-secret")


class TestNoModuleLevelCache:
    """Tests verifying the simplified implementation has no caching complexity.

    The old implementation had module-level caching for Key Vault lookups.
    The new implementation doesn't need caching since it only reads env vars.
    """

    def test_env_var_changes_are_reflected_immediately(self) -> None:
        """Environment variable changes take effect immediately.

        Unlike the old cached Key Vault lookup, env var changes are
        visible on every call.
        """
        with patch.dict(os.environ, {_ENV_VAR: "first-key"}):
            key1 = get_fingerprint_key()
            assert key1 == b"first-key"

            # Change the env var
            os.environ[_ENV_VAR] = "second-key"

            # Should see the new value immediately
            key2 = get_fingerprint_key()
            assert key2 == b"second-key"
