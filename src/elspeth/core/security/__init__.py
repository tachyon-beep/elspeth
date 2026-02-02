# src/elspeth/core/security/__init__.py
"""Security utilities for ELSPETH.

Exports:
- secret_fingerprint: Compute HMAC-SHA256 fingerprint of a secret
- get_fingerprint_key: Get the fingerprint key from environment
- SecretLoadError: Raised when secret loading fails
- load_secrets_from_config: Load secrets from pipeline config
- Secret loader classes: For advanced use cases
"""

from elspeth.core.security.config_secrets import (
    SecretLoadError,
    load_secrets_from_config,
)
from elspeth.core.security.fingerprint import (
    get_fingerprint_key,
    secret_fingerprint,
)
from elspeth.core.security.secret_loader import (
    CachedSecretLoader,
    CompositeSecretLoader,
    EnvSecretLoader,
    KeyVaultSecretLoader,
    SecretLoader,
    SecretNotFoundError,
    SecretRef,
)

__all__ = [
    # Fingerprinting
    "get_fingerprint_key",
    "secret_fingerprint",
    # Config-based loading (new)
    "load_secrets_from_config",
    "SecretLoadError",
    # Secret loader classes (still used by config_secrets and other code)
    "CachedSecretLoader",
    "CompositeSecretLoader",
    "EnvSecretLoader",
    "KeyVaultSecretLoader",
    "SecretLoader",
    "SecretNotFoundError",
    "SecretRef",
]
