"""Secret fingerprinting using HMAC-SHA256.

The canonical implementation lives in contracts/security.py (stdlib-only,
no heavy dependencies). This module re-exports as part of the core.security
package API.

Usage:
    from elspeth.core.security import secret_fingerprint

    # With explicit key
    fp = secret_fingerprint(api_key, key=signing_key)

    # With environment variable (ELSPETH_FINGERPRINT_KEY)
    fp = secret_fingerprint(api_key)

Note: ELSPETH_FINGERPRINT_KEY can be set directly or loaded from Azure Key Vault
via the secrets configuration in your pipeline YAML.
"""

from elspeth.contracts.security import (
    _ENV_VAR,
    get_fingerprint_key,
    secret_fingerprint,
)

__all__ = [
    "_ENV_VAR",
    "get_fingerprint_key",
    "secret_fingerprint",
]
