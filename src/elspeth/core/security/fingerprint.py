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

# P1-8: Removed module-level cache (_cached_fingerprint_key, _cached_keyvault_loader)
# The cache was for Key Vault lookups which are now handled by config_secrets.py
# Env var lookups don't need caching - os.environ is already a dict lookup


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

    if len(key) == 0:
        raise ValueError("Fingerprint key must not be empty — an empty HMAC key produces meaningless fingerprints")

    digest = hmac.new(
        key=key,
        msg=secret.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return digest
