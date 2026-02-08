# tests/core/security/test_fingerprint.py
"""Tests for secret fingerprinting."""

import pytest

from elspeth.core.security.fingerprint import get_fingerprint_key, secret_fingerprint


class TestSecretFingerprint:
    """Test secret fingerprinting utility."""

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

    def test_fingerprint_without_key_uses_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When key not provided, uses ELSPETH_FINGERPRINT_KEY env var."""
        monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "env-key-value")

        result = secret_fingerprint("my-secret")

        # Verify the env key is actually used by checking against expected HMAC
        # Precomputed: hmac.new(b"env-key-value", b"my-secret", sha256).hexdigest()
        expected = "9bbccfbb68be10d7a8b2649a63b421167e1c05cd78e52fe2761f1743691c5630"
        assert result == expected

    def test_fingerprint_without_key_raises_if_env_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ValueError if no key provided and env var missing."""
        monkeypatch.delenv("ELSPETH_FINGERPRINT_KEY", raising=False)

        with pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
            secret_fingerprint("my-secret")


class TestGetFingerprintKey:
    """Test fingerprint key retrieval."""

    def test_get_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_fingerprint_key() reads from environment."""
        monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "my-secret-key")

        key = get_fingerprint_key()

        assert key == b"my-secret-key"

    def test_get_key_raises_if_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ValueError if env var not set."""
        monkeypatch.delenv("ELSPETH_FINGERPRINT_KEY", raising=False)

        with pytest.raises(ValueError):
            get_fingerprint_key()
