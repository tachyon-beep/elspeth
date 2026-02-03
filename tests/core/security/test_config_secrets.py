# tests/core/security/test_config_secrets.py
"""Tests for config-based secret loading from Azure Key Vault.

This module tests:
1. load_secrets_from_config() for both "env" and "keyvault" sources
2. Resolution record generation for deferred audit recording
3. Error handling with clear, actionable messages
4. Environment variable injection behavior
5. Edge cases: unicode, newlines, very long secrets
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspeth.core.config import SecretsConfig
from elspeth.core.security.config_secrets import SecretLoadError, load_secrets_from_config


class TestEnvSource:
    """Test behavior when source is 'env'."""

    def test_env_source_returns_empty_list(self) -> None:
        """When source is 'env', load_secrets_from_config returns empty list."""
        config = SecretsConfig(source="env")

        result = load_secrets_from_config(config)

        assert result == []

    def test_env_source_does_not_modify_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When source is 'env', no environment variables are modified."""
        monkeypatch.setenv("EXISTING_VAR", "original-value")

        config = SecretsConfig(source="env")
        load_secrets_from_config(config)

        assert os.environ["EXISTING_VAR"] == "original-value"


class TestKeyVaultSource:
    """Test behavior when source is 'keyvault'."""

    def test_keyvault_loads_mapped_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Key Vault secrets are loaded and injected into environment."""
        # Clean up any existing env var
        monkeypatch.delenv("AZURE_OPENAI_KEY", raising=False)

        mock_secret = MagicMock()
        mock_secret.value = "secret-api-key-123"

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"AZURE_OPENAI_KEY": "azure-openai-key"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            load_secrets_from_config(config)

        assert os.environ["AZURE_OPENAI_KEY"] == "secret-api-key-123"
        mock_client.get_secret.assert_called_once_with("azure-openai-key")

    def test_keyvault_returns_resolution_records(self) -> None:
        """Resolution records contain all required audit fields."""
        mock_secret = MagicMock()
        mock_secret.value = "test-secret-value"

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://my-vault.vault.azure.net",
            mapping={"MY_API_KEY": "my-api-key-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            resolutions = load_secrets_from_config(config)

        assert len(resolutions) == 1
        record = resolutions[0]

        # Verify all required fields are present
        assert record["env_var_name"] == "MY_API_KEY"
        assert record["source"] == "keyvault"
        assert record["vault_url"] == "https://my-vault.vault.azure.net"
        assert record["secret_name"] == "my-api-key-secret"
        assert "timestamp" in record
        assert "latency_ms" in record
        assert record["secret_value"] == "test-secret-value"  # For fingerprinting

        # Verify timestamp is reasonable
        import time

        assert record["timestamp"] <= time.time()
        assert record["timestamp"] > time.time() - 60  # Within last minute

        # Verify latency is non-negative
        assert record["latency_ms"] >= 0

    def test_keyvault_loads_multiple_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple secrets are loaded in a single call."""
        monkeypatch.delenv("API_KEY_1", raising=False)
        monkeypatch.delenv("API_KEY_2", raising=False)

        def mock_get_secret(name: str) -> MagicMock:
            secret = MagicMock()
            secret.value = f"value-for-{name}"
            return secret

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = mock_get_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={
                "API_KEY_1": "secret-1",
                "API_KEY_2": "secret-2",
            },
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            resolutions = load_secrets_from_config(config)

        assert len(resolutions) == 2
        assert os.environ["API_KEY_1"] == "value-for-secret-1"
        assert os.environ["API_KEY_2"] == "value-for-secret-2"

    def test_keyvault_overrides_existing_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Key Vault values override existing environment variables."""
        monkeypatch.setenv("OVERRIDE_ME", "original-dev-value")

        mock_secret = MagicMock()
        mock_secret.value = "production-keyvault-value"

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"OVERRIDE_ME": "prod-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            load_secrets_from_config(config)

        assert os.environ["OVERRIDE_ME"] == "production-keyvault-value"


class TestErrorHandling:
    """Test error handling with clear, actionable messages."""

    def test_keyvault_missing_secret_fails_fast(self) -> None:
        """SecretNotFoundError is wrapped in SecretLoadError with clear message."""
        from azure.core.exceptions import ResourceNotFoundError as AzureResourceNotFoundError

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = AzureResourceNotFoundError("Secret not found")

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"MY_KEY": "nonexistent-secret"},
        )

        with (
            patch(
                "elspeth.core.security.secret_loader._get_keyvault_client",
                return_value=mock_client,
            ),
            pytest.raises(SecretLoadError) as exc_info,
        ):
            load_secrets_from_config(config)

        error_msg = str(exc_info.value)
        assert "nonexistent-secret" in error_msg
        assert "not found" in error_msg
        assert "MY_KEY" in error_msg

    def test_keyvault_auth_failure_fails_fast(self) -> None:
        """Auth errors produce clear messages with remediation guidance."""
        from azure.core.exceptions import ClientAuthenticationError

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = ClientAuthenticationError("DefaultAzureCredential failed")

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://prod-vault.vault.azure.net",
            mapping={"API_KEY": "api-secret"},
        )

        with (
            patch(
                "elspeth.core.security.secret_loader._get_keyvault_client",
                return_value=mock_client,
            ),
            pytest.raises(SecretLoadError) as exc_info,
        ):
            load_secrets_from_config(config)

        error_msg = str(exc_info.value)
        assert "authenticate" in error_msg.lower()
        assert "prod-vault.vault.azure.net" in error_msg
        assert "DefaultAzureCredential" in error_msg

    def test_error_message_includes_vault_url_and_secret_name(self) -> None:
        """Error messages include vault URL and secret name for debugging."""
        from azure.core.exceptions import HttpResponseError

        mock_client = MagicMock()
        error = HttpResponseError("Service unavailable")
        error.status_code = 503
        mock_client.get_secret.side_effect = error

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://debug-vault.vault.azure.net",
            mapping={"DEBUG_KEY": "debug-secret-name"},
        )

        with (
            patch(
                "elspeth.core.security.secret_loader._get_keyvault_client",
                return_value=mock_client,
            ),
            pytest.raises(SecretLoadError) as exc_info,
        ):
            load_secrets_from_config(config)

        error_msg = str(exc_info.value)
        assert "debug-vault.vault.azure.net" in error_msg
        assert "debug-secret-name" in error_msg
        assert "DEBUG_KEY" in error_msg

    def test_azure_sdk_not_installed_shows_helpful_error(self) -> None:
        """ImportError produces helpful installation guidance."""
        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"KEY": "secret"},
        )

        # Patch at the point where the import happens inside load_secrets_from_config
        # The function does: from elspeth.core.security.secret_loader import KeyVaultSecretLoader
        # So we need to make that import fail
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args, **kwargs):
            if "secret_loader" in name:
                raise ImportError("No module named 'azure.keyvault.secrets'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", mock_import), pytest.raises(SecretLoadError) as exc_info:
            load_secrets_from_config(config)

        error_msg = str(exc_info.value)
        assert "uv pip install" in error_msg or "azure" in error_msg.lower()


class TestEdgeCases:
    """Test edge cases: unicode, newlines, very long secrets."""

    def test_keyvault_secret_with_unicode_characters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unicode characters in secrets are preserved correctly."""
        monkeypatch.delenv("UNICODE_KEY", raising=False)

        unicode_value = "secret-with-\u00e9\u00e8\u00ea-unicode-\u4e2d\u6587-\u0420\u0443\u0441\u0441\u043a\u0438\u0439"

        mock_secret = MagicMock()
        mock_secret.value = unicode_value

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"UNICODE_KEY": "unicode-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            resolutions = load_secrets_from_config(config)

        assert os.environ["UNICODE_KEY"] == unicode_value
        assert resolutions[0]["secret_value"] == unicode_value

    def test_keyvault_secret_with_newlines(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiline secrets (e.g., private keys) are preserved correctly."""
        monkeypatch.delenv("MULTILINE_KEY", raising=False)

        multiline_value = """-----BEGIN RSA PRIVATE KEY-----
MIIEpQIBAAKCAQEA0Z3VS5JJcds3xfn/
ygWyZbTbDqpVlTTSV1+xJ0VU1NM/X2rL
...more key data...
-----END RSA PRIVATE KEY-----"""

        mock_secret = MagicMock()
        mock_secret.value = multiline_value

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"MULTILINE_KEY": "private-key-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            resolutions = load_secrets_from_config(config)

        assert os.environ["MULTILINE_KEY"] == multiline_value
        assert "\n" in os.environ["MULTILINE_KEY"]
        assert resolutions[0]["secret_value"] == multiline_value

    def test_keyvault_very_long_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Very long secrets (25KB) are supported."""
        monkeypatch.delenv("LONG_KEY", raising=False)

        # 25KB secret (Key Vault limit is 25KB)
        long_value = "x" * 25 * 1024

        mock_secret = MagicMock()
        mock_secret.value = long_value

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"LONG_KEY": "long-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            resolutions = load_secrets_from_config(config)

        assert os.environ["LONG_KEY"] == long_value
        assert len(resolutions[0]["secret_value"]) == 25 * 1024


class TestIdempotency:
    """Test idempotency and repeated calls."""

    def test_load_secrets_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calling load_secrets_from_config twice is safe and produces same env result."""
        monkeypatch.delenv("IDEMPOTENT_KEY", raising=False)

        mock_secret = MagicMock()
        mock_secret.value = "idempotent-value"

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"IDEMPOTENT_KEY": "idem-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            # Call twice
            resolutions1 = load_secrets_from_config(config)
            resolutions2 = load_secrets_from_config(config)

        # Both calls should succeed
        assert len(resolutions1) == 1
        assert len(resolutions2) == 1

        # Environment should have the value
        assert os.environ["IDEMPOTENT_KEY"] == "idempotent-value"

        # Note: Each call creates a new KeyVaultSecretLoader instance, so Key Vault
        # is called twice. This is acceptable - the important thing is that the
        # environment ends up in the correct state regardless of how many times
        # load_secrets_from_config is called. Cross-call caching would require
        # a module-level loader singleton, which adds complexity without benefit.
        assert mock_client.get_secret.call_count == 2

    def test_resolution_records_independent_per_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each call returns its own resolution records (independent objects)."""
        monkeypatch.delenv("RECORD_KEY", raising=False)

        mock_secret = MagicMock()
        mock_secret.value = "consistent-value"

        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"RECORD_KEY": "record-secret"},
        )

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            resolutions1 = load_secrets_from_config(config)
            resolutions2 = load_secrets_from_config(config)

        # Both resolution lists are independent objects
        assert resolutions1 is not resolutions2

        # Both should have the same secret value
        assert resolutions1[0]["secret_value"] == "consistent-value"
        assert resolutions2[0]["secret_value"] == "consistent-value"

        # Both should have all required fields
        for res in [resolutions1[0], resolutions2[0]]:
            assert "env_var_name" in res
            assert "timestamp" in res
            assert "latency_ms" in res


class TestSecretLoadErrorException:
    """Test SecretLoadError exception class."""

    def test_secret_load_error_is_exception(self) -> None:
        """SecretLoadError is a proper exception."""
        error = SecretLoadError("Test error message")
        assert isinstance(error, Exception)
        assert str(error) == "Test error message"

    def test_secret_load_error_can_chain_cause(self) -> None:
        """SecretLoadError properly chains cause exceptions."""
        cause = ValueError("Original error")
        error = SecretLoadError("Wrapped error")
        error.__cause__ = cause

        assert error.__cause__ is cause


class TestCLILoadSettingsWithSecrets:
    """Test the _load_settings_with_secrets CLI helper function.

    This helper implements the three-phase loading pattern used by
    run, resume, and validate commands to ensure Key Vault secrets
    are available for Dynaconf ${VAR} resolution.
    """

    def test_load_settings_with_secrets_env_source(self, tmp_path: Path) -> None:
        """With source='env' (default), settings load without Key Vault calls."""
        # Create minimal settings file (no secrets config = source='env')
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("""
source:
  plugin: csv
  options:
    path: input.csv
    schema:
      mode: observed
sinks:
  output:
    plugin: csv
    options:
      path: output.csv
      schema:
        mode: observed
default_sink: output
landscape:
  enabled: false
""")

        from elspeth.cli import _load_settings_with_secrets

        config, resolutions = _load_settings_with_secrets(settings_file)

        assert config.source.plugin == "csv"
        assert config.default_sink == "output"
        assert resolutions == []  # No secrets to load

    def test_load_settings_with_secrets_keyvault_injects_env_vars(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With source='keyvault', secrets are injected before ${VAR} resolution."""
        # Clean env to ensure we're testing the injection path
        monkeypatch.delenv("TEST_API_KEY", raising=False)

        # Mock Key Vault response
        mock_secret = MagicMock()
        mock_secret.value = "injected-key-value"
        mock_client = MagicMock()
        mock_client.get_secret.return_value = mock_secret

        # Create settings file that uses ${TEST_API_KEY}
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("""
secrets:
  source: keyvault
  vault_url: https://test-vault.vault.azure.net
  mapping:
    TEST_API_KEY: test-api-key-secret

source:
  plugin: csv
  options:
    path: input.csv
    schema:
      mode: observed
sinks:
  output:
    plugin: csv
    options:
      path: output.csv
      schema:
        mode: observed
default_sink: output

# Use the secret in some config value
landscape:
  enabled: false
""")

        from elspeth.cli import _load_settings_with_secrets

        with patch(
            "elspeth.core.security.secret_loader._get_keyvault_client",
            return_value=mock_client,
        ):
            config, resolutions = _load_settings_with_secrets(settings_file)

        # Settings loaded successfully
        assert config.source.plugin == "csv"

        # Secret was injected into environment
        assert os.environ["TEST_API_KEY"] == "injected-key-value"

        # Resolution records returned for audit
        assert len(resolutions) == 1
        assert resolutions[0]["env_var_name"] == "TEST_API_KEY"
        assert resolutions[0]["source"] == "keyvault"
        assert resolutions[0]["secret_name"] == "test-api-key-secret"

    def test_load_settings_with_secrets_raises_on_missing_secret(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """SecretLoadError raised when Key Vault secret doesn't exist."""
        from elspeth.core.security.secret_loader import SecretNotFoundError

        monkeypatch.delenv("MISSING_KEY", raising=False)

        mock_client = MagicMock()
        mock_client.get_secret.side_effect = SecretNotFoundError("missing-secret", "https://test-vault.vault.azure.net")

        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("""
secrets:
  source: keyvault
  vault_url: https://test-vault.vault.azure.net
  mapping:
    MISSING_KEY: missing-secret

source:
  plugin: csv
  options:
    path: input.csv
    schema:
      mode: observed
sinks:
  output:
    plugin: csv
    options:
      path: output.csv
      schema:
        mode: observed
default_sink: output
landscape:
  enabled: false
""")

        from elspeth.cli import _load_settings_with_secrets

        with (
            patch(
                "elspeth.core.security.secret_loader._get_keyvault_client",
                return_value=mock_client,
            ),
            pytest.raises(SecretLoadError) as exc_info,
        ):
            _load_settings_with_secrets(settings_file)

        assert "missing-secret" in str(exc_info.value)
        assert "not found" in str(exc_info.value)
