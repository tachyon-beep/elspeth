# src/elspeth/core/security/__init__.py
"""Security utilities for ELSPETH.

Exports:
- secret_fingerprint: Compute HMAC-SHA256 fingerprint of a secret
- get_fingerprint_key: Get the fingerprint key from environment
- SecretLoadError: Raised when secret loading fails
- load_secrets_from_config: Load secrets from pipeline config
- Secret loader classes: For advanced use cases
- Web security: SSRF prevention (validate_url_scheme, validate_ip)
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
from elspeth.core.security.web import (
    NetworkError,
    SSRFBlockedError,
    validate_ip,
    validate_url_scheme,
)

__all__ = [
    "CachedSecretLoader",
    "CompositeSecretLoader",
    "EnvSecretLoader",
    "KeyVaultSecretLoader",
    "NetworkError",
    "SSRFBlockedError",
    "SecretLoadError",
    "SecretLoader",
    "SecretNotFoundError",
    "SecretRef",
    "get_fingerprint_key",
    "load_secrets_from_config",
    "secret_fingerprint",
    "validate_ip",
    "validate_url_scheme",
]
