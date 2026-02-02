# tests/integration/test_keyvault_fingerprint.py
"""Integration tests for Azure Key Vault secret loading via config_secrets.

These tests require real Azure credentials and a Key Vault with secrets.
Skip by default; run with: pytest -m integration tests/integration/test_keyvault_fingerprint.py

Setup:
1. Create Azure Key Vault
2. Create secret named 'elspeth-fingerprint-key' with a random value
3. Authenticate via Azure CLI: az login
4. Run with the Key Vault URL:
   pytest -m integration tests/integration/test_keyvault_fingerprint.py \
     --keyvault-url "https://your-vault.vault.azure.net"

BREAKING CHANGE: The old ELSPETH_KEYVAULT_URL env var approach is removed.
Secrets must now be loaded via the YAML-based secrets configuration.
"""

from __future__ import annotations

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line option for Key Vault URL."""
    parser.addoption(
        "--keyvault-url",
        action="store",
        default=None,
        help="Azure Key Vault URL for integration tests",
    )


@pytest.fixture
def keyvault_url(request: pytest.FixtureRequest) -> str:
    """Get Key Vault URL from command line or environment."""
    url = request.config.getoption("--keyvault-url") or os.environ.get("TEST_KEYVAULT_URL")
    if not url:
        pytest.skip(
            "Key Vault URL not configured. Pass --keyvault-url or set TEST_KEYVAULT_URL. "
            "Note: ELSPETH_KEYVAULT_URL is no longer used for fingerprint keys."
        )
    return url


@pytest.mark.integration
class TestKeyVaultSecretsConfig:
    """Integration tests using the new YAML-based secrets configuration."""

    def test_load_fingerprint_key_via_secrets_config(
        self, keyvault_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Can load fingerprint key from Key Vault via secrets config.

        This test verifies the end-to-end flow:
        1. Create SecretsConfig from YAML-like dict
        2. Load secrets from real Key Vault
        3. Verify ELSPETH_FINGERPRINT_KEY is set
        4. Verify get_fingerprint_key() returns the loaded value
        """
        from elspeth.core.config import SecretsConfig
        from elspeth.core.config_secrets import load_secrets
        from elspeth.core.security.fingerprint import get_fingerprint_key

        # Ensure we're starting without the env var
        monkeypatch.delenv("ELSPETH_FINGERPRINT_KEY", raising=False)

        # Create secrets config that loads fingerprint key from Key Vault
        secrets_config = SecretsConfig(
            keyvault_url=keyvault_url,
            load=[
                {
                    "secret": "elspeth-fingerprint-key",
                    "env": "ELSPETH_FINGERPRINT_KEY",
                }
            ],
        )

        # Load secrets (this calls Key Vault)
        load_secrets(secrets_config)

        # Now get_fingerprint_key should work
        key = get_fingerprint_key()

        assert isinstance(key, bytes)
        assert len(key) > 0

    def test_load_multiple_secrets(
        self, keyvault_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Can load multiple secrets from Key Vault in one config."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.config_secrets import load_secrets

        # Clear any existing env vars
        monkeypatch.delenv("ELSPETH_FINGERPRINT_KEY", raising=False)
        monkeypatch.delenv("TEST_API_KEY", raising=False)

        # Create secrets config with multiple secrets
        # Note: This test assumes 'test-api-key' exists in the Key Vault
        secrets_config = SecretsConfig(
            keyvault_url=keyvault_url,
            load=[
                {
                    "secret": "elspeth-fingerprint-key",
                    "env": "ELSPETH_FINGERPRINT_KEY",
                },
                # Uncomment if you have a test-api-key secret:
                # {
                #     "secret": "test-api-key",
                #     "env": "TEST_API_KEY",
                # },
            ],
        )

        # Load secrets
        load_secrets(secrets_config)

        # Verify fingerprint key was loaded
        assert os.environ.get("ELSPETH_FINGERPRINT_KEY") is not None


@pytest.mark.integration
class TestOldEnvVarApproachRemoved:
    """Tests verifying the old ELSPETH_KEYVAULT_URL approach no longer works.

    BREAKING CHANGE: These tests document that the migration is required.
    """

    def test_elspeth_keyvault_url_no_longer_used(
        self, keyvault_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ELSPETH_KEYVAULT_URL no longer triggers Key Vault lookup.

        This is a BREAKING CHANGE. The old approach was:
        - Set ELSPETH_KEYVAULT_URL
        - Call get_fingerprint_key()
        - fingerprint.py would automatically fetch from Key Vault

        The new approach is:
        - Configure secrets in YAML
        - CLI calls load_secrets() at startup
        - ELSPETH_FINGERPRINT_KEY env var is set
        - get_fingerprint_key() reads the env var
        """
        from elspeth.core.security.fingerprint import get_fingerprint_key

        # Clear ELSPETH_FINGERPRINT_KEY
        monkeypatch.delenv("ELSPETH_FINGERPRINT_KEY", raising=False)

        # Set the old env var (this used to trigger Key Vault lookup)
        monkeypatch.setenv("ELSPETH_KEYVAULT_URL", keyvault_url)

        # This should now FAIL because fingerprint.py no longer reads ELSPETH_KEYVAULT_URL
        with pytest.raises(ValueError, match="ELSPETH_FINGERPRINT_KEY"):
            get_fingerprint_key()
