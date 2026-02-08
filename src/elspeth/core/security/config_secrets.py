# src/elspeth/core/security/config_secrets.py
"""Config-based secret loading from Azure Key Vault.

This module loads secrets specified in pipeline configuration and injects
them into environment variables before config resolution.

IMPORTANT: This module reuses the existing KeyVaultSecretLoader from
secret_loader.py to avoid code duplication and maintain consistent caching.

Resolution records are returned with HMAC fingerprints (not plaintext values)
for deferred audit recording. Fingerprinting happens immediately after each
secret is loaded — plaintext values never leave this module.

Usage:
    from elspeth.core.config import SecretsConfig
    from elspeth.core.security.config_secrets import load_secrets_from_config

    config = SecretsConfig(
        source="keyvault",
        vault_url="https://my-vault.vault.azure.net",
        mapping={"AZURE_OPENAI_KEY": "azure-openai-key"},
    )
    resolutions = load_secrets_from_config(config)
    # Now os.environ["AZURE_OPENAI_KEY"] contains the secret value
    # resolutions contain fingerprints (not values) for audit recording
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.config import SecretsConfig


class SecretLoadError(Exception):
    """Raised when secret loading fails.

    This error indicates a configuration or infrastructure problem that
    prevents the pipeline from starting. The error message includes
    debugging information (vault URL, secret name, env var name).
    """

    pass


def load_secrets_from_config(config: SecretsConfig) -> list[dict[str, Any]]:
    """Load secrets from configured source and inject into environment.

    When source is 'env', this function does nothing (secrets come from
    environment variables as usual).

    When source is 'keyvault', all mapped secrets are loaded from Azure
    Key Vault and injected into os.environ, overriding any existing values.
    Each secret is fingerprinted immediately after loading — plaintext values
    never leave this function.

    Args:
        config: SecretsConfig specifying source and mapping

    Returns:
        List of resolution records for deferred audit recording.
        Each record contains: env_var_name, source, vault_url, secret_name,
        timestamp, latency_ms, fingerprint (HMAC-SHA256 hex digest).

        Plaintext secret values are NOT included in the returned records.

    Raises:
        SecretLoadError: If any secret cannot be loaded (fail fast)
    """
    if config.source == "env":
        # Nothing to do - secrets are already in environment
        return []

    # source == "keyvault"
    # P0-1: No defensive assertions - Pydantic guarantees vault_url and mapping
    # are set when source == "keyvault"

    # P1-2026-02-05: Preflight check for fingerprint key before any Key Vault calls.
    # Audit recording requires ELSPETH_FINGERPRINT_KEY to compute secret fingerprints.
    # Without it, secrets would be fetched but audit recording would fail later,
    # leaving secret resolution events unrecorded (violates auditability standard).
    fingerprint_key_available = os.environ.get("ELSPETH_FINGERPRINT_KEY") or "ELSPETH_FINGERPRINT_KEY" in config.mapping
    if not fingerprint_key_available:
        raise SecretLoadError(
            "ELSPETH_FINGERPRINT_KEY is required when loading secrets from Key Vault.\n"
            "The fingerprint key is used to compute HMAC fingerprints of secrets for the audit trail.\n"
            "Fix by either:\n"
            "  1. Set ELSPETH_FINGERPRINT_KEY environment variable, or\n"
            "  2. Add ELSPETH_FINGERPRINT_KEY to your secrets mapping to load from Key Vault:\n"
            "     secrets:\n"
            "       source: keyvault\n"
            "       vault_url: https://my-vault.vault.azure.net\n"
            "       mapping:\n"
            "         ELSPETH_FINGERPRINT_KEY: elspeth-fingerprint-key\n"
            "         # ... other secrets"
        )

    # P0-4: Reuse existing KeyVaultSecretLoader instead of duplicating code
    try:
        from elspeth.core.security.secret_loader import (
            KeyVaultSecretLoader,
            SecretNotFoundError,
        )
    except ImportError as e:
        raise SecretLoadError("Azure Key Vault packages not installed. Install with: uv pip install 'elspeth[azure]'") from e

    # Create loader (has built-in caching)
    # load_secrets_from_config() only called when config.source == "keyvault"
    assert config.vault_url is not None, "vault_url required when source=keyvault"
    try:
        loader = KeyVaultSecretLoader(vault_url=config.vault_url)
    except ImportError as e:
        raise SecretLoadError("Azure Key Vault packages not installed. Install with: uv pip install 'elspeth[azure]'") from e
    except Exception as e:
        # P0-2: This catches Azure auth errors during client creation
        error_str = str(e)
        if "ClientAuthenticationError" in error_str or "credential" in error_str.lower():
            raise SecretLoadError(
                f"Failed to authenticate to Key Vault ({config.vault_url})\n"
                f"DefaultAzureCredential could not find valid credentials.\n"
                f"Ensure Managed Identity, Azure CLI login, or service principal env vars are configured.\n"
                f"Error: {e}"
            ) from e
        raise SecretLoadError(f"Failed to initialize Key Vault loader for {config.vault_url}\nError: {e}") from e

    # Load each mapped secret, fingerprint immediately, collect resolution records.
    # Plaintext values are fingerprinted and discarded within this loop iteration —
    # they never accumulate in the resolutions list.
    from elspeth.core.security.fingerprint import get_fingerprint_key, secret_fingerprint

    resolutions: list[dict[str, Any]] = []

    # Fingerprint key is available after loading ELSPETH_FINGERPRINT_KEY
    # (either from env or from Key Vault earlier in this loop).
    # Defer key acquisition until the first non-fingerprint-key secret.
    fingerprint_key: bytes | None = None

    # Ensure ELSPETH_FINGERPRINT_KEY is loaded first when present in mapping.
    # Without this, a mapping where ELSPETH_FINGERPRINT_KEY appears after other
    # secrets would fail: get_fingerprint_key() reads os.environ, but the Key Vault
    # secret hasn't been injected yet. User YAML ordering must not cause failures.
    _FP_KEY = "ELSPETH_FINGERPRINT_KEY"
    ordered_mapping: list[tuple[str, str]] = []
    if _FP_KEY in config.mapping:
        ordered_mapping.append((_FP_KEY, config.mapping[_FP_KEY]))
    for env_var_name, keyvault_secret_name in config.mapping.items():
        if env_var_name != _FP_KEY:
            ordered_mapping.append((env_var_name, keyvault_secret_name))

    for env_var_name, keyvault_secret_name in ordered_mapping:
        start_time = time.time()
        try:
            secret_value, _ref = loader.get_secret(keyvault_secret_name)
            latency_ms = (time.time() - start_time) * 1000

            # Inject into environment (overrides existing)
            os.environ[env_var_name] = str(secret_value)

            # Compute fingerprint immediately — plaintext never leaves this function.
            # Acquire fingerprint key lazily (it may have just been loaded above).
            if fingerprint_key is None:
                fingerprint_key = get_fingerprint_key()
            fp = secret_fingerprint(str(secret_value), key=fingerprint_key)

            resolutions.append(
                {
                    "env_var_name": env_var_name,
                    "source": "keyvault",
                    "vault_url": config.vault_url,
                    "secret_name": keyvault_secret_name,
                    "timestamp": start_time,
                    "latency_ms": latency_ms,
                    "fingerprint": fp,
                }
            )

        except SecretNotFoundError as e:
            # P0-2: Catch specific exception for missing secrets
            raise SecretLoadError(
                f"Secret '{keyvault_secret_name}' not found in Key Vault ({config.vault_url})\n"
                f"Mapped from: {env_var_name}\n"
                f"Verify the secret exists: az keyvault secret show --vault-name <vault> --name {keyvault_secret_name}"
            ) from e
        except ImportError as e:
            # Azure SDK not installed
            raise SecretLoadError("Azure Key Vault packages not installed. Install with: uv pip install 'elspeth[azure]'") from e
        except Exception as e:
            # P0-2: Catch auth and other Azure errors
            error_str = str(e)
            if "ClientAuthenticationError" in error_str or "credential" in error_str.lower():
                raise SecretLoadError(
                    f"Failed to authenticate to Key Vault ({config.vault_url})\n"
                    f"DefaultAzureCredential could not find valid credentials.\n"
                    f"Ensure Managed Identity, Azure CLI login, or service principal env vars are configured.\n"
                    f"Error: {e}"
                ) from e
            else:
                raise SecretLoadError(
                    f"Failed to load secret '{keyvault_secret_name}' from Key Vault ({config.vault_url})\n"
                    f"Mapped from: {env_var_name}\n"
                    f"Error: {e}"
                ) from e

    return resolutions
