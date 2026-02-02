# Azure Key Vault Secrets Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable config-based secret loading from Azure Key Vault with explicit mapping, replacing the old environment variable-based fingerprint key mechanism.

**Architecture:** Secrets are configured in the pipeline YAML under a `secrets:` section. When `source: keyvault` is specified, all mapped secrets are loaded from Key Vault and injected into environment variables before Dynaconf resolves `${VAR}` references. This maintains compatibility with existing `${AZURE_OPENAI_KEY}` syntax while centralizing secret management.

**Tech Stack:** Pydantic (validation), Azure Identity SDK (DefaultAzureCredential), Azure Key Vault Secrets SDK

---

## Task 1: Add SecretsConfig Pydantic Model

**Files:**
- Modify: `src/elspeth/core/config.py`
- Test: `tests/core/test_secrets_config.py`

**Step 1: Write the failing test**

Create `tests/core/test_secrets_config.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_secrets_config.py -v`
Expected: FAIL with "cannot import name 'SecretsConfig'"

**Step 3: Write minimal implementation**

Add to `src/elspeth/core/config.py` (after the imports, before TriggerConfig):

```python
from typing import Literal

class SecretsConfig(BaseModel):
    """Configuration for secret loading.

    Secrets can come from environment variables (default) or Azure Key Vault.
    When using Key Vault, an explicit mapping from env var names to Key Vault
    secret names is required.

    Example (env - default):
        secrets:
          source: env  # Uses .env file and environment variables

    Example (keyvault):
        secrets:
          source: keyvault
          vault_url: https://my-vault.vault.azure.net
          mapping:
            AZURE_OPENAI_KEY: azure-openai-key
            ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
    """

    model_config = {"frozen": True, "extra": "forbid"}

    source: Literal["env", "keyvault"] = Field(
        default="env",
        description="Secret source: 'env' (environment variables) or 'keyvault' (Azure Key Vault)",
    )
    vault_url: str | None = Field(
        default=None,
        description="Azure Key Vault URL (required when source is 'keyvault')",
    )
    mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from env var names to Key Vault secret names",
    )

    @model_validator(mode="after")
    def validate_keyvault_requirements(self) -> "SecretsConfig":
        """Validate that keyvault source has required fields."""
        if self.source == "keyvault":
            if not self.vault_url:
                raise ValueError("vault_url is required when source is 'keyvault'")
            if not self.mapping:
                raise ValueError("mapping is required when source is 'keyvault' (cannot be empty)")
        return self
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_secrets_config.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add tests/core/test_secrets_config.py src/elspeth/core/config.py
git commit -m "feat(config): add SecretsConfig Pydantic model

Adds configuration schema for secret loading with two sources:
- env: Load from environment variables (default)
- keyvault: Load from Azure Key Vault with explicit mapping

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Add secrets Field to ElspethSettings

**Files:**
- Modify: `src/elspeth/core/config.py`
- Test: `tests/core/test_secrets_config.py`

**Step 1: Write the failing test**

Add to `tests/core/test_secrets_config.py`:

```python
class TestElspethSettingsSecrets:
    """Tests for secrets field in ElspethSettings."""

    def test_settings_has_optional_secrets_field(self) -> None:
        """ElspethSettings should have optional secrets field."""
        from elspeth.core.config import ElspethSettings, SecretsConfig

        # Minimal valid config without secrets
        settings = ElspethSettings(
            source={"plugin": "null"},
            sinks={"output": {"plugin": "null"}},
            default_sink="output",
        )
        # Should have default SecretsConfig
        assert settings.secrets is not None
        assert settings.secrets.source == "env"

    def test_settings_accepts_keyvault_secrets(self) -> None:
        """ElspethSettings should accept keyvault secrets config."""
        from elspeth.core.config import ElspethSettings

        settings = ElspethSettings(
            source={"plugin": "null"},
            sinks={"output": {"plugin": "null"}},
            default_sink="output",
            secrets={
                "source": "keyvault",
                "vault_url": "https://my-vault.vault.azure.net",
                "mapping": {"AZURE_OPENAI_KEY": "azure-openai-key"},
            },
        )
        assert settings.secrets.source == "keyvault"
        assert settings.secrets.vault_url == "https://my-vault.vault.azure.net"
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_secrets_config.py::TestElspethSettingsSecrets -v`
Expected: FAIL with "unexpected keyword argument 'secrets'"

**Step 3: Write minimal implementation**

Add to `ElspethSettings` class in `src/elspeth/core/config.py` (after the telemetry field):

```python
    # Optional - secrets configuration
    secrets: SecretsConfig = Field(
        default_factory=SecretsConfig,
        description="Secret loading configuration (env vars or Azure Key Vault)",
    )
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_secrets_config.py::TestElspethSettingsSecrets -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspeth/core/config.py tests/core/test_secrets_config.py
git commit -m "feat(config): add secrets field to ElspethSettings

Adds optional secrets configuration to top-level settings.
Defaults to source: env for backwards compatibility.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Create config_secrets.py Module

**Files:**
- Create: `src/elspeth/core/security/config_secrets.py`
- Test: `tests/core/security/test_config_secrets.py`

**Step 1: Write the failing test**

Create `tests/core/security/test_config_secrets.py`:

```python
# tests/core/security/test_config_secrets.py
"""Tests for config-based secret loading."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestLoadSecretsFromConfig:
    """Tests for load_secrets_from_config function."""

    def test_env_source_does_nothing(self) -> None:
        """source: env should not modify environment."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.security.config_secrets import load_secrets_from_config

        config = SecretsConfig(source="env")

        # Should not raise, should not modify env
        with patch.dict(os.environ, {}, clear=False):
            load_secrets_from_config(config)
            # No assertions needed - just verify it doesn't crash

    def test_keyvault_loads_mapped_secrets(self) -> None:
        """source: keyvault should load all mapped secrets into env."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.security.config_secrets import load_secrets_from_config

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={
                "AZURE_OPENAI_KEY": "azure-openai-key",
                "AZURE_OPENAI_ENDPOINT": "openai-endpoint",
            },
        )

        mock_secret_1 = MagicMock()
        mock_secret_1.value = "secret-key-value"
        mock_secret_2 = MagicMock()
        mock_secret_2.value = "https://endpoint.openai.azure.com"

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_secret.side_effect = [mock_secret_1, mock_secret_2]
            mock_get_client.return_value = mock_client

            with patch.dict(os.environ, {}, clear=False):
                load_secrets_from_config(config)

                assert os.environ["AZURE_OPENAI_KEY"] == "secret-key-value"
                assert os.environ["AZURE_OPENAI_ENDPOINT"] == "https://endpoint.openai.azure.com"

    def test_keyvault_missing_secret_fails_fast(self) -> None:
        """Missing secret in Key Vault should raise immediately."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.security.config_secrets import (
            SecretLoadError,
            load_secrets_from_config,
        )

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"AZURE_OPENAI_KEY": "nonexistent-secret"},
        )

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_client = MagicMock()
            # Simulate ResourceNotFoundError
            mock_client.get_secret.side_effect = Exception("SecretNotFound")
            mock_get_client.return_value = mock_client

            with pytest.raises(SecretLoadError, match="nonexistent-secret"):
                load_secrets_from_config(config)

    def test_keyvault_auth_failure_fails_fast(self) -> None:
        """Authentication failure should raise with clear message."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.security.config_secrets import (
            SecretLoadError,
            load_secrets_from_config,
        )

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"KEY": "secret"},
        )

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_get_client.side_effect = Exception("DefaultAzureCredential failed")

            with pytest.raises(SecretLoadError, match="authenticate"):
                load_secrets_from_config(config)

    def test_keyvault_overrides_existing_env_vars(self) -> None:
        """Key Vault secrets should override existing env vars."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.security.config_secrets import load_secrets_from_config

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://test-vault.vault.azure.net",
            mapping={"AZURE_OPENAI_KEY": "azure-openai-key"},
        )

        mock_secret = MagicMock()
        mock_secret.value = "keyvault-value"

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_secret.return_value = mock_secret
            mock_get_client.return_value = mock_client

            with patch.dict(os.environ, {"AZURE_OPENAI_KEY": "env-value"}, clear=False):
                load_secrets_from_config(config)
                assert os.environ["AZURE_OPENAI_KEY"] == "keyvault-value"

    def test_error_message_includes_vault_url_and_secret_name(self) -> None:
        """Error message should include debugging information."""
        from elspeth.core.config import SecretsConfig
        from elspeth.core.security.config_secrets import (
            SecretLoadError,
            load_secrets_from_config,
        )

        config = SecretsConfig(
            source="keyvault",
            vault_url="https://my-specific-vault.vault.azure.net",
            mapping={"MY_ENV_VAR": "my-specific-secret"},
        )

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_secret.side_effect = Exception("Not found")
            mock_get_client.return_value = mock_client

            with pytest.raises(SecretLoadError) as exc_info:
                load_secrets_from_config(config)

            error_msg = str(exc_info.value)
            assert "my-specific-vault" in error_msg
            assert "my-specific-secret" in error_msg
            assert "MY_ENV_VAR" in error_msg
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/security/test_config_secrets.py -v`
Expected: FAIL with "No module named 'elspeth.core.security.config_secrets'"

**Step 3: Write minimal implementation**

Create `src/elspeth/core/security/config_secrets.py`:

```python
# src/elspeth/core/security/config_secrets.py
"""Config-based secret loading from Azure Key Vault.

This module loads secrets specified in pipeline configuration and injects
them into environment variables before config resolution.

Usage:
    from elspeth.core.config import SecretsConfig
    from elspeth.core.security.config_secrets import load_secrets_from_config

    config = SecretsConfig(
        source="keyvault",
        vault_url="https://my-vault.vault.azure.net",
        mapping={"AZURE_OPENAI_KEY": "azure-openai-key"},
    )
    load_secrets_from_config(config)
    # Now os.environ["AZURE_OPENAI_KEY"] contains the secret value
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure.keyvault.secrets import SecretClient

    from elspeth.core.config import SecretsConfig


class SecretLoadError(Exception):
    """Raised when secret loading fails.

    This error indicates a configuration or infrastructure problem that
    prevents the pipeline from starting. The error message includes
    debugging information (vault URL, secret name, env var name).
    """

    pass


def _get_keyvault_client(vault_url: str) -> "SecretClient":
    """Create a Key Vault SecretClient using DefaultAzureCredential.

    Args:
        vault_url: The Key Vault URL (e.g., https://my-vault.vault.azure.net)

    Returns:
        SecretClient configured with DefaultAzureCredential

    Raises:
        SecretLoadError: If azure packages not installed or auth fails
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as e:
        raise SecretLoadError(
            "Azure Key Vault packages not installed. "
            "Install with: uv pip install 'elspeth[azure]'"
        ) from e

    try:
        credential = DefaultAzureCredential()
        return SecretClient(vault_url=vault_url, credential=credential)
    except Exception as e:
        raise SecretLoadError(
            f"Failed to authenticate to Key Vault ({vault_url})\n"
            f"DefaultAzureCredential could not find valid credentials.\n"
            f"Ensure Managed Identity, Azure CLI login, or service principal env vars are configured.\n"
            f"Error: {e}"
        ) from e


def load_secrets_from_config(config: "SecretsConfig") -> None:
    """Load secrets from configured source and inject into environment.

    When source is 'env', this function does nothing (secrets come from
    environment variables as usual).

    When source is 'keyvault', all mapped secrets are loaded from Azure
    Key Vault and injected into os.environ, overriding any existing values.

    Args:
        config: SecretsConfig specifying source and mapping

    Raises:
        SecretLoadError: If any secret cannot be loaded (fail fast)
    """
    if config.source == "env":
        # Nothing to do - secrets are already in environment
        return

    # source == "keyvault"
    assert config.vault_url is not None  # Validated by Pydantic
    assert config.mapping  # Validated by Pydantic

    try:
        client = _get_keyvault_client(config.vault_url)
    except SecretLoadError:
        raise  # Already has good error message

    # Load each mapped secret
    for env_var_name, keyvault_secret_name in config.mapping.items():
        try:
            secret = client.get_secret(keyvault_secret_name)
            if secret.value is None:
                raise SecretLoadError(
                    f"Secret '{keyvault_secret_name}' in Key Vault ({config.vault_url}) has no value\n"
                    f"Mapped from: {env_var_name}"
                )
            # Inject into environment (overrides existing)
            os.environ[env_var_name] = secret.value
        except SecretLoadError:
            raise  # Already has good error message
        except Exception as e:
            raise SecretLoadError(
                f"Secret '{keyvault_secret_name}' not found in Key Vault ({config.vault_url})\n"
                f"Mapped from: {env_var_name}\n"
                f"Error: {e}"
            ) from e
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/security/test_config_secrets.py -v`
Expected: PASS (all 6 tests)

**Step 5: Commit**

```bash
git add src/elspeth/core/security/config_secrets.py tests/core/security/test_config_secrets.py
git commit -m "feat(security): add config-based secret loading from Key Vault

Adds load_secrets_from_config() that loads secrets from Azure Key Vault
based on pipeline configuration and injects them into environment variables.

Features:
- Explicit mapping from env var names to Key Vault secret names
- Fail fast on any missing secret
- Clear error messages with vault URL, secret name, and env var name
- Overrides existing env vars (Key Vault is source of truth)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Integrate Secret Loading into CLI

**Files:**
- Modify: `src/elspeth/cli.py`
- Test: `tests/cli/test_secrets_loading.py`

**Step 1: Write the failing test**

Create `tests/cli/test_secrets_loading.py`:

```python
# tests/cli/test_secrets_loading.py
"""Tests for CLI secret loading integration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class TestCLISecretsLoading:
    """Tests for secret loading in CLI run command."""

    def test_run_with_keyvault_secrets_loads_before_config(
        self, tmp_path: Path
    ) -> None:
        """Secrets should be loaded before config resolution."""
        from elspeth.cli import app

        # Create a settings file that references a secret
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("""
secrets:
  source: keyvault
  vault_url: https://test-vault.vault.azure.net
  mapping:
    TEST_SECRET: test-secret

source:
  plugin: null

sinks:
  output:
    plugin: null

default_sink: output
""")

        mock_secret = MagicMock()
        mock_secret.value = "loaded-from-keyvault"

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_secret.return_value = mock_secret
            mock_get_client.return_value = mock_client

            # Run with --dry-run to avoid full execution
            result = runner.invoke(
                app, ["--no-dotenv", "run", "--settings", str(settings_file), "--dry-run"]
            )

            # Verify secret was loaded
            mock_client.get_secret.assert_called_once_with("test-secret")

    def test_run_with_keyvault_failure_exits_with_error(
        self, tmp_path: Path
    ) -> None:
        """Key Vault failure should exit with clear error message."""
        from elspeth.cli import app

        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("""
secrets:
  source: keyvault
  vault_url: https://test-vault.vault.azure.net
  mapping:
    MISSING_SECRET: nonexistent-secret

source:
  plugin: null

sinks:
  output:
    plugin: null

default_sink: output
""")

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_secret.side_effect = Exception("Not found")
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                app, ["--no-dotenv", "run", "--settings", str(settings_file), "--dry-run"]
            )

            assert result.exit_code == 1
            assert "nonexistent-secret" in result.output or "Secret" in result.output

    def test_run_with_env_source_skips_keyvault(
        self, tmp_path: Path
    ) -> None:
        """source: env should not attempt Key Vault connection."""
        from elspeth.cli import app

        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text("""
secrets:
  source: env

source:
  plugin: null

sinks:
  output:
    plugin: null

default_sink: output
""")

        with patch("elspeth.core.security.config_secrets._get_keyvault_client") as mock_get_client:
            result = runner.invoke(
                app, ["--no-dotenv", "run", "--settings", str(settings_file), "--dry-run"]
            )

            # Key Vault client should NOT be called
            mock_get_client.assert_not_called()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/cli/test_secrets_loading.py -v`
Expected: FAIL (secrets not being loaded in CLI)

**Step 3: Write minimal implementation**

Modify `src/elspeth/cli.py`. Find the `run` command and modify the config loading section.

First, add the import at the top of the file (with other imports):

```python
from elspeth.core.security.config_secrets import SecretLoadError, load_secrets_from_config
```

Then, modify the `run` command. Find the section after `config = load_settings(settings_path)` and add secret loading. The new flow is:

1. Parse YAML without resolution to extract secrets config
2. Load secrets from Key Vault if configured
3. Re-parse with Dynaconf (which resolves `${VAR}`)

Replace the config loading section in the `run` command:

```python
    # Load and validate config via Pydantic
    # Two-phase loading: extract secrets config first, then full resolution
    try:
        # Phase 1: Parse YAML to extract secrets config (no ${VAR} resolution yet)
        raw_config = _load_raw_yaml(settings_path)
        secrets_config = _extract_secrets_config(raw_config)

        # Phase 2: Load secrets from Key Vault if configured
        try:
            load_secrets_from_config(secrets_config)
        except SecretLoadError as e:
            typer.echo(f"Error loading secrets: {e}", err=True)
            raise typer.Exit(1) from None

        # Phase 3: Full config loading with Dynaconf (resolves ${VAR})
        config = load_settings(settings_path)
```

Add helper functions before the `run` command:

```python
def _load_raw_yaml(config_path: Path) -> dict[str, Any]:
    """Load YAML without environment variable resolution.

    This is used to extract the secrets config before loading secrets.
    """
    import yaml

    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def _extract_secrets_config(raw_config: dict[str, Any]) -> "SecretsConfig":
    """Extract and validate secrets config from raw YAML.

    Returns SecretsConfig with defaults if not specified.
    """
    from elspeth.core.config import SecretsConfig

    secrets_dict = raw_config.get("secrets", {})
    return SecretsConfig(**secrets_dict)
```

Add the import for `Any` if not already present:

```python
from typing import TYPE_CHECKING, Any, Literal
```

Also add SecretsConfig to the TYPE_CHECKING imports or regular imports.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/cli/test_secrets_loading.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/elspeth/cli.py tests/cli/test_secrets_loading.py
git commit -m "feat(cli): integrate Key Vault secret loading into run command

Secrets are now loaded in two phases:
1. Parse YAML to extract secrets config (no \${VAR} resolution)
2. Load secrets from Key Vault and inject into environment
3. Full config resolution with Dynaconf (resolves \${VAR})

This ensures secrets are available before config references like
\${AZURE_OPENAI_KEY} are resolved.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Remove Old Fingerprint Key Mechanism

**Files:**
- Modify: `src/elspeth/core/security/fingerprint.py`
- Modify: `tests/core/security/test_fingerprint_keyvault.py`
- Modify: `tests/core/security/test_fingerprint.py`

**Step 1: Update fingerprint.py to remove old env var handling**

Simplify `src/elspeth/core/security/fingerprint.py` to only use `ELSPETH_FINGERPRINT_KEY` from environment (which can now be populated by the secrets config):

```python
# src/elspeth/core/security/fingerprint.py
"""Secret fingerprinting using HMAC-SHA256.

Secrets (API keys, tokens, passwords) should never appear in the audit trail.
Instead, we store a fingerprint that can verify "same secret was used"
without revealing the actual secret value.

Usage:
    from elspeth.core.security import secret_fingerprint

    # With explicit key
    fp = secret_fingerprint(api_key, key=signing_key)

    # With environment variable (ELSPETH_FINGERPRINT_KEY)
    fp = secret_fingerprint(api_key)

Note: ELSPETH_FINGERPRINT_KEY can be set directly or loaded from Azure Key Vault
via the secrets configuration in your pipeline YAML.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ENV_VAR = "ELSPETH_FINGERPRINT_KEY"


def get_fingerprint_key() -> bytes:
    """Get the fingerprint key from environment.

    The fingerprint key should be set via:
    1. Direct environment variable: ELSPETH_FINGERPRINT_KEY=your-key
    2. Pipeline secrets config loading from Azure Key Vault

    Returns:
        The fingerprint key as bytes

    Raises:
        ValueError: If ELSPETH_FINGERPRINT_KEY is not set
    """
    env_key = os.environ.get(_ENV_VAR)
    if not env_key:
        raise ValueError(
            f"Fingerprint key not configured. Set {_ENV_VAR} environment variable "
            f"or configure it in your pipeline's secrets section to load from Azure Key Vault."
        )
    return env_key.encode("utf-8")


def secret_fingerprint(secret: str, *, key: bytes | None = None) -> str:
    """Compute HMAC-SHA256 fingerprint of a secret.

    The fingerprint can be stored in the audit trail to verify that
    the same secret was used across runs, without exposing the secret.

    Args:
        secret: The secret value to fingerprint (API key, token, etc.)
        key: HMAC key. If not provided, reads from ELSPETH_FINGERPRINT_KEY env var.

    Returns:
        64-character hex string (SHA256 digest)

    Raises:
        ValueError: If key is None and ELSPETH_FINGERPRINT_KEY not set

    Example:
        >>> fp = secret_fingerprint("sk-abc123", key=b"my-signing-key")
        >>> len(fp)
        64
        >>> fp == secret_fingerprint("sk-abc123", key=b"my-signing-key")
        True
    """
    if key is None:
        key = get_fingerprint_key()

    digest = hmac.new(
        key=key,
        msg=secret.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return digest
```

**Step 2: Update test_fingerprint_keyvault.py**

Replace the entire file with tests for the simplified behavior:

```python
# tests/core/security/test_fingerprint_keyvault.py
"""Tests for fingerprint key retrieval.

The fingerprint key now comes solely from ELSPETH_FINGERPRINT_KEY environment
variable, which can be populated by the secrets config loading from Key Vault.
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


class TestFingerprintKeyRetrieval:
    """Tests for fingerprint key retrieval from environment."""

    def test_missing_env_var_raises_value_error(self) -> None:
        """Must raise ValueError when env var not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_VAR, None)

            with pytest.raises(ValueError, match="Fingerprint key not configured"):
                get_fingerprint_key()

    def test_empty_env_var_raises_value_error(self) -> None:
        """Empty string env var should raise ValueError."""
        with patch.dict(os.environ, {_ENV_VAR: ""}, clear=False):
            with pytest.raises(ValueError, match="Fingerprint key not configured"):
                get_fingerprint_key()

    def test_env_var_returns_key_as_bytes(self) -> None:
        """Valid env var should return key as bytes."""
        with patch.dict(os.environ, {_ENV_VAR: "test-fingerprint-key"}):
            key = get_fingerprint_key()
            assert key == b"test-fingerprint-key"

    def test_secret_fingerprint_without_key_uses_env(self) -> None:
        """secret_fingerprint() without key should use env var."""
        with patch.dict(os.environ, {_ENV_VAR: "test-key"}):
            fp = secret_fingerprint("my-secret")
            assert len(fp) == 64  # SHA256 hex digest

    def test_secret_fingerprint_with_explicit_key(self) -> None:
        """secret_fingerprint() with explicit key ignores env."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_VAR, None)

            # Should work with explicit key even if env not set
            fp = secret_fingerprint("my-secret", key=b"explicit-key")
            assert len(fp) == 64

    def test_fingerprint_is_deterministic(self) -> None:
        """Same secret + key should produce same fingerprint."""
        key = b"test-key"
        secret = "my-api-key"

        fp1 = secret_fingerprint(secret, key=key)
        fp2 = secret_fingerprint(secret, key=key)

        assert fp1 == fp2

    def test_different_secrets_produce_different_fingerprints(self) -> None:
        """Different secrets should produce different fingerprints."""
        key = b"test-key"

        fp1 = secret_fingerprint("secret-1", key=key)
        fp2 = secret_fingerprint("secret-2", key=key)

        assert fp1 != fp2
```

**Step 3: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/security/test_fingerprint_keyvault.py tests/core/security/test_fingerprint.py -v`
Expected: PASS

**Step 4: Commit**

```bash
git add src/elspeth/core/security/fingerprint.py tests/core/security/test_fingerprint_keyvault.py
git commit -m "refactor(security): simplify fingerprint key to use env var only

Removes the old ELSPETH_KEYVAULT_URL / ELSPETH_KEYVAULT_SECRET_NAME mechanism.
Fingerprint key now comes from ELSPETH_FINGERPRINT_KEY environment variable,
which can be populated by the secrets config loading from Azure Key Vault.

This is simpler and more consistent - all secrets use the same mechanism.

BREAKING CHANGE: ELSPETH_KEYVAULT_URL and ELSPETH_KEYVAULT_SECRET_NAME are
no longer recognized. Use the secrets config in pipeline YAML instead.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Update __init__.py Exports

**Files:**
- Modify: `src/elspeth/core/security/__init__.py`

**Step 1: Read current exports**

Check what's currently exported and update.

**Step 2: Update exports**

```python
# src/elspeth/core/security/__init__.py
"""Security utilities for ELSPETH.

Exports:
- secret_fingerprint: Compute HMAC-SHA256 fingerprint of a secret
- get_fingerprint_key: Get the fingerprint key from environment
- SecretLoadError: Raised when secret loading fails
- load_secrets_from_config: Load secrets from pipeline config
"""

from elspeth.core.security.config_secrets import SecretLoadError, load_secrets_from_config
from elspeth.core.security.fingerprint import get_fingerprint_key, secret_fingerprint

__all__ = [
    "get_fingerprint_key",
    "load_secrets_from_config",
    "secret_fingerprint",
    "SecretLoadError",
]
```

**Step 3: Commit**

```bash
git add src/elspeth/core/security/__init__.py
git commit -m "refactor(security): update __init__.py exports

Exports the new config_secrets functions and removes references to
removed Key Vault env var functions.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Update Documentation - Configuration Reference

**Files:**
- Modify: `docs/reference/configuration.md`

**Step 1: Add secrets section**

Add after the "Top-Level Settings" table (around line 71), before "Run Modes":

```markdown
### Secrets Settings

Configure how secrets (API keys, tokens) are loaded for the pipeline.

```yaml
secrets:
  source: keyvault
  vault_url: https://my-vault.vault.azure.net
  mapping:
    AZURE_OPENAI_KEY: azure-openai-key
    AZURE_OPENAI_ENDPOINT: openai-endpoint
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source` | string | No | `"env"` | Secret source: `env` or `keyvault` |
| `vault_url` | string | When `source: keyvault` | - | Azure Key Vault URL |
| `mapping` | object | When `source: keyvault` | - | Env var name → Key Vault secret name |

**Source Options:**

| Source | Behavior |
|--------|----------|
| `env` | Secrets come from environment variables / .env file (default) |
| `keyvault` | Secrets loaded from Azure Key Vault using explicit mapping |

**Authentication (Key Vault):**

Uses Azure DefaultAzureCredential, which tries (in order):
1. Managed Identity (Azure VMs, App Service, AKS)
2. Azure CLI (`az login`)
3. Environment variables (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`)
4. Visual Studio Code Azure extension

**Example - Local Development:**

```yaml
# Use .env file for local development
secrets:
  source: env
```

**Example - Production with Key Vault:**

```yaml
secrets:
  source: keyvault
  vault_url: https://prod-vault.vault.azure.net
  mapping:
    AZURE_OPENAI_KEY: azure-openai-api-key
    AZURE_OPENAI_ENDPOINT: azure-openai-endpoint
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
```

---
```

**Step 2: Update the Top-Level Settings table**

Add a row for `secrets`:

```markdown
| `secrets` | object | No | (defaults) | Secret loading configuration |
```

**Step 3: Commit**

```bash
git add docs/reference/configuration.md
git commit -m "docs: add secrets configuration reference

Documents the new secrets configuration section for loading
secrets from environment variables or Azure Key Vault.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Create Example Pipeline with Key Vault Secrets

**Files:**
- Create: `examples/azure_keyvault_secrets/settings.yaml`
- Create: `examples/azure_keyvault_secrets/README.md`
- Create: `examples/azure_keyvault_secrets/input/data.csv`

**Step 1: Create the example directory and files**

`examples/azure_keyvault_secrets/settings.yaml`:

```yaml
# Example: Loading secrets from Azure Key Vault
#
# This pipeline demonstrates using Azure Key Vault for secret management.
# All API keys and the fingerprint key are loaded from Key Vault at startup.

secrets:
  source: keyvault
  vault_url: ${AZURE_KEYVAULT_URL}  # Set this env var to your vault URL
  mapping:
    # Map environment variable names to Key Vault secret names
    AZURE_OPENAI_KEY: azure-openai-api-key
    AZURE_OPENAI_ENDPOINT: azure-openai-endpoint
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key

source:
  plugin: csv
  options:
    path: ./input/data.csv

transforms:
  - plugin: passthrough

sinks:
  output:
    plugin: csv
    options:
      path: ./output/results.csv

default_sink: output

landscape:
  url: sqlite:///./runs/audit.db
```

`examples/azure_keyvault_secrets/README.md`:

```markdown
# Azure Key Vault Secrets Example

This example demonstrates loading secrets from Azure Key Vault instead of environment variables.

## Prerequisites

1. An Azure Key Vault with secrets:
   - `azure-openai-api-key` - Your Azure OpenAI API key
   - `azure-openai-endpoint` - Your Azure OpenAI endpoint URL
   - `elspeth-fingerprint-key` - A random key for secret fingerprinting

2. Azure authentication configured (one of):
   - Managed Identity (in Azure)
   - Azure CLI logged in (`az login`)
   - Service principal env vars (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`)

## Setup

1. Create secrets in your Key Vault:

```bash
az keyvault secret set --vault-name YOUR_VAULT --name azure-openai-api-key --value "your-api-key"
az keyvault secret set --vault-name YOUR_VAULT --name azure-openai-endpoint --value "https://your-resource.openai.azure.com"
az keyvault secret set --vault-name YOUR_VAULT --name elspeth-fingerprint-key --value "$(openssl rand -hex 32)"
```

2. Set the vault URL:

```bash
export AZURE_KEYVAULT_URL=https://YOUR_VAULT.vault.azure.net
```

3. Run the pipeline:

```bash
elspeth run --settings settings.yaml --execute
```

## How It Works

1. ELSPETH parses `settings.yaml` and extracts the `secrets:` section
2. Connects to Azure Key Vault using DefaultAzureCredential
3. Loads each mapped secret and sets it as an environment variable
4. Continues with normal config resolution (${VAR} syntax now works)

## Security Notes

- Secrets are loaded once at startup and cached in memory
- Secrets are never written to disk or logs
- The audit trail stores fingerprints of secrets, not actual values
- Key Vault access can be audited via Azure Monitor
```

`examples/azure_keyvault_secrets/input/data.csv`:

```csv
id,text
1,Hello world
2,Test message
```

**Step 2: Commit**

```bash
git add examples/azure_keyvault_secrets/
git commit -m "docs: add Azure Key Vault secrets example

Complete working example showing how to configure a pipeline
to load secrets from Azure Key Vault.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update CLAUDE.md Secret Handling Section

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Find and update the Secret Handling section**

Search for "Secret Handling" or "HMAC fingerprints" and update to reference the new config-based approach.

Update to:

```markdown
### Secret Handling

Never store secrets directly - use HMAC fingerprints for audit:

```python
fingerprint = hmac.new(fingerprint_key, secret.encode(), hashlib.sha256).hexdigest()
```

**Secret Loading:**

Secrets can be loaded from environment variables (default) or Azure Key Vault:

```yaml
# Pipeline settings.yaml
secrets:
  source: keyvault
  vault_url: https://my-vault.vault.azure.net
  mapping:
    AZURE_OPENAI_KEY: azure-openai-key
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key
```

When `source: keyvault`, secrets are loaded at startup and injected into environment variables before config resolution. This means `${AZURE_OPENAI_KEY}` in your config will resolve to the Key Vault secret value.

**Fingerprint Key:**

The `ELSPETH_FINGERPRINT_KEY` is used to compute HMAC fingerprints of secrets for the audit trail. Configure it:

1. **Environment variable:** `export ELSPETH_FINGERPRINT_KEY=your-random-key`
2. **Key Vault:** Include in your secrets mapping (recommended for production)
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md secret handling section

Documents the new config-based secret loading from Azure Key Vault.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Create Runbook for Key Vault Setup

**Files:**
- Create: `docs/runbooks/configure-keyvault-secrets.md`

**Step 1: Write the runbook**

```markdown
# Configure Azure Key Vault Secrets

This runbook walks through setting up Azure Key Vault for ELSPETH secret management.

## Prerequisites

- Azure subscription
- Azure CLI installed and logged in (`az login`)
- Permission to create Key Vault and secrets

## Step 1: Create Key Vault (if needed)

```bash
# Set variables
RESOURCE_GROUP=my-resource-group
VAULT_NAME=my-elspeth-vault
LOCATION=eastus

# Create resource group (if needed)
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Key Vault
az keyvault create \
  --name $VAULT_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --enable-rbac-authorization true
```

## Step 2: Grant Access

For your user (local development):

```bash
USER_ID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $USER_ID \
  --scope /subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$VAULT_NAME
```

For Managed Identity (production):

```bash
IDENTITY_ID=<your-managed-identity-principal-id>
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $IDENTITY_ID \
  --scope /subscriptions/$(az account show --query id -o tsv)/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.KeyVault/vaults/$VAULT_NAME
```

## Step 3: Create Secrets

```bash
# Generate a random fingerprint key
FINGERPRINT_KEY=$(openssl rand -hex 32)

# Store secrets
az keyvault secret set --vault-name $VAULT_NAME --name azure-openai-api-key --value "your-actual-api-key"
az keyvault secret set --vault-name $VAULT_NAME --name azure-openai-endpoint --value "https://your-resource.openai.azure.com"
az keyvault secret set --vault-name $VAULT_NAME --name elspeth-fingerprint-key --value "$FINGERPRINT_KEY"
```

## Step 4: Configure Pipeline

Update your `settings.yaml`:

```yaml
secrets:
  source: keyvault
  vault_url: https://my-elspeth-vault.vault.azure.net
  mapping:
    AZURE_OPENAI_KEY: azure-openai-api-key
    AZURE_OPENAI_ENDPOINT: azure-openai-endpoint
    ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key

source:
  plugin: csv
  # ... rest of your config
```

## Step 5: Verify

```bash
# Test with dry-run
elspeth run --settings settings.yaml --dry-run
```

## Troubleshooting

### "DefaultAzureCredential could not find valid credentials"

1. **Local:** Run `az login` to authenticate
2. **Azure VM:** Ensure Managed Identity is enabled
3. **Service Principal:** Set `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`

### "Secret 'xxx' not found in Key Vault"

1. Verify secret exists: `az keyvault secret show --vault-name $VAULT_NAME --name xxx`
2. Check secret name matches exactly (case-sensitive)

### "Forbidden" or "Access Denied"

1. Verify RBAC assignment: `az role assignment list --assignee <your-id> --scope <vault-resource-id>`
2. Ensure "Key Vault Secrets User" role is assigned
```

**Step 2: Commit**

```bash
git add docs/runbooks/configure-keyvault-secrets.md
git commit -m "docs: add Key Vault setup runbook

Step-by-step guide for configuring Azure Key Vault for
ELSPETH secret management.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Run Full Test Suite and Fix Any Issues

**Step 1: Run all tests**

```bash
.venv/bin/python -m pytest tests/ -v --tb=short
```

**Step 2: Run type checking**

```bash
.venv/bin/python -m mypy src/elspeth/
```

**Step 3: Run linting**

```bash
.venv/bin/python -m ruff check src/elspeth/
```

**Step 4: Fix any issues found**

Address any test failures, type errors, or lint warnings.

**Step 5: Commit fixes**

```bash
git add -A
git commit -m "fix: address test/lint issues from Key Vault secrets implementation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan implements config-based Azure Key Vault secret loading with:

1. **SecretsConfig Pydantic model** - Validates `source`, `vault_url`, `mapping`
2. **config_secrets.py** - Loads secrets and injects into environment
3. **CLI integration** - Two-phase config loading (secrets first, then resolution)
4. **Simplified fingerprint.py** - Uses env var only (populated by secrets config)
5. **Comprehensive documentation** - Reference, example, runbook
6. **Full test coverage** - Unit and integration tests

**Breaking change:** `ELSPETH_KEYVAULT_URL` and `ELSPETH_KEYVAULT_SECRET_NAME` environment variables are no longer recognized. Use the `secrets:` configuration in pipeline YAML instead.
