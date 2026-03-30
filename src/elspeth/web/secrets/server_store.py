"""Curated server-secret inventory backed by environment variables.

Only exposes secrets whose names are in the configured allowlist.
Does NOT dump arbitrary env vars to the browser.
"""

from __future__ import annotations

import os

from elspeth.contracts.secrets import SecretInventoryItem
from elspeth.core.security.secret_loader import SecretNotFoundError, SecretRef


class ServerSecretStore:
    """Env-var secret store restricted to an explicit allowlist.

    The allowlist is set from ``WebSettings.server_secret_allowlist``
    so that only operator-approved names are ever readable.
    """

    def __init__(self, allowlist: tuple[str, ...]) -> None:
        self._allowlist = allowlist

    def get_secret(self, name: str) -> tuple[str, SecretRef]:
        """Resolve an allowlisted env var.

        Raises:
            SecretNotFoundError: If *name* is not in the allowlist
                or the env var is unset / empty.
        """
        if name not in self._allowlist:
            raise SecretNotFoundError(name)
        value = os.environ.get(name)  # Tier 3: env vars are external input
        if not value:
            raise SecretNotFoundError(name)
        return value, SecretRef(name=name, fingerprint="", source="env")

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
        ]
