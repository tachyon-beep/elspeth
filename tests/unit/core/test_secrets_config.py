# tests/core/test_secrets_config.py
"""Tests for SecretsConfig Pydantic model validation."""

import pytest
from pydantic import ValidationError


class TestSecretsConfigValidation:
    """Tests for SecretsConfig schema validation."""

    def test_env_source_requires_no_additional_fields(self) -> None:
        """source: env should work with no other fields."""
        from elspeth.core.config import SecretsConfig

        config = SecretsConfig(source="env")
        assert config.source == "env"
        assert config.vault_url is None
        assert config.mapping == {}

    def test_keyvault_source_requires_vault_url(self) -> None:
        """source: keyvault must have vault_url."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match="vault_url is required"):
            SecretsConfig(source="keyvault", mapping={"KEY": "key"})

    def test_keyvault_source_requires_mapping(self) -> None:
        """source: keyvault must have non-empty mapping."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match="mapping is required"):
            SecretsConfig(
                source="keyvault",
                vault_url="https://my-vault.vault.azure.net",
                mapping={},
            )

    def test_keyvault_source_valid_config(self) -> None:
        """Valid keyvault config passes validation."""
        from elspeth.core.config import SecretsConfig

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://my-vault.vault.azure.net",
            mapping={
                "AZURE_OPENAI_KEY": "azure-openai-key",
                "AZURE_OPENAI_ENDPOINT": "openai-endpoint",
            },
        )
        assert config.source == "keyvault"
        assert config.vault_url == "https://my-vault.vault.azure.net"
        assert len(config.mapping) == 2

    def test_invalid_source_rejected(self) -> None:
        """Invalid source value is rejected."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match="Input should be 'env' or 'keyvault'"):
            SecretsConfig(source="invalid")

    def test_default_source_is_env(self) -> None:
        """Default source is 'env' when not specified."""
        from elspeth.core.config import SecretsConfig

        config = SecretsConfig()
        assert config.source == "env"

    # P0-3: Vault URL format validation tests
    def test_vault_url_must_be_https(self) -> None:
        """vault_url must use HTTPS protocol."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match="must use HTTPS"):
            SecretsConfig(
                source="keyvault",
                vault_url="http://my-vault.vault.azure.net",  # HTTP not allowed
                mapping={"KEY": "key"},
            )

    def test_vault_url_rejects_env_var_reference(self) -> None:
        """vault_url cannot contain ${VAR} references (chicken-egg problem)."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match=r"cannot contain.*\$\{"):
            SecretsConfig(
                source="keyvault",
                vault_url="${AZURE_KEYVAULT_URL}",  # Not allowed
                mapping={"KEY": "key"},
            )

    def test_vault_url_rejects_malformed_url(self) -> None:
        """vault_url must be a valid URL."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match="Invalid URL"):
            SecretsConfig(
                source="keyvault",
                vault_url="not-a-valid-url",
                mapping={"KEY": "key"},
            )

    def test_vault_url_with_trailing_slash_normalized(self) -> None:
        """vault_url with trailing slash should be accepted."""
        from elspeth.core.config import SecretsConfig

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://my-vault.vault.azure.net/",
            mapping={"KEY": "key"},
        )
        # Trailing slash should be stripped for consistency
        assert config.vault_url == "https://my-vault.vault.azure.net"

    def test_vault_url_rejects_non_string(self) -> None:
        """Non-string vault_url should be rejected with type error."""
        from elspeth.core.config import SecretsConfig

        with pytest.raises(ValidationError, match="str"):
            SecretsConfig(
                source="keyvault",
                vault_url=123,  # type: ignore[arg-type]  # Integer instead of string
                mapping={"KEY": "key"},
            )
