"""Curated server-secret inventory backed by environment variables.

Only exposes secrets whose names are in the configured allowlist.
Does NOT dump arbitrary env vars to the browser.
"""

from __future__ import annotations

import os

from elspeth.contracts.secrets import SecretInventoryItem
from elspeth.core.security.secret_loader import SecretNotFoundError, SecretRef
from elspeth.web.secrets.user_store import _compute_fingerprint

_RESERVED_PREFIX = "ELSPETH_"
"""Server secrets are for third-party API keys, not ELSPETH internals.

Any env var whose name starts with ELSPETH_ is an internal secret
(fingerprint key, JWT signing key, audit passphrase, etc.) and must
never be exposed through the server secret store.
"""


def _is_reserved(name: str) -> bool:
    return name.startswith(_RESERVED_PREFIX)


class ServerSecretStore:
    """Env-var secret store restricted to an explicit allowlist.

    The allowlist is set from ``WebSettings.server_secret_allowlist``
    so that only operator-approved names are ever readable.
    """

    def __init__(self, allowlist: tuple[str, ...]) -> None:
        reserved = [n for n in allowlist if _is_reserved(n)]
        if reserved:
            raise ValueError(
                f"Server secret allowlist contains ELSPETH internal names "
                f"that must never be exposed: {sorted(reserved)}"
            )
        self._allowlist = allowlist

    def has_secret(self, name: str) -> bool:
        """Check if an allowlisted env var secret exists without reading the value.

        Raises:
            SecretNotFoundError: If *name* is reserved (ELSPETH_* prefix).
        """
        if _is_reserved(name):
            raise SecretNotFoundError(name)
        return name in self._allowlist and bool(os.environ.get(name))

    def get_secret(self, name: str) -> tuple[str, SecretRef]:
        """Resolve an allowlisted env var.

        Raises:
            SecretNotFoundError: If *name* is not in the allowlist,
                is reserved, or the env var is unset / empty.
        """
        if _is_reserved(name):
            raise SecretNotFoundError(name)
        if name not in self._allowlist:
            raise SecretNotFoundError(name)
        value = os.environ.get(name)  # Tier 3: env vars are external input
        if not value:
            raise SecretNotFoundError(name)
        fp = _compute_fingerprint(name, value)
        return value, SecretRef(name=name, fingerprint=fp, source="env")

    def list_secrets(self) -> list[SecretInventoryItem]:
        """Return metadata for every allowlisted name (never exposes values)."""
        return [
            SecretInventoryItem(
                name=name,
                scope="server",
                available=bool(os.environ.get(name)),  # Tier 3: env vars
                source_kind="env",
            )
            for name in self._allowlist
            if not _is_reserved(name)
        ]
