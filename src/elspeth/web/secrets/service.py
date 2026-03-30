"""WebSecretService -- composes user + server stores behind WebSecretResolver."""

from __future__ import annotations

from elspeth.contracts.secrets import ResolvedSecret, SecretInventoryItem
from elspeth.core.security.secret_loader import SecretNotFoundError
from elspeth.web.secrets.server_store import ServerSecretStore
from elspeth.web.secrets.user_store import UserSecretStore


class WebSecretService:
    """Chained secret resolution: user -> server.

    Implements the ``WebSecretResolver`` protocol for use by
    ``resolve_secret_refs()``.  Also exposes ``set_user_secret`` /
    ``delete_user_secret`` for the REST API layer.
    """

    def __init__(self, user_store: UserSecretStore, server_store: ServerSecretStore) -> None:
        self._user_store = user_store
        self._server_store = server_store

    # -- WebSecretResolver protocol ------------------------------------------

    def list_refs(self, user_id: str) -> list[SecretInventoryItem]:
        """Merge user and server inventories; user scope wins on name clash."""
        user_items = {item.name: item for item in self._user_store.list_secrets(user_id=user_id)}
        server_items = {item.name: item for item in self._server_store.list_secrets()}
        merged = {**server_items, **user_items}  # user scope wins
        return sorted(merged.values(), key=lambda x: x.name)

    def has_ref(self, user_id: str, name: str) -> bool:
        """Check whether *name* is resolvable in either scope."""
        return self.resolve(user_id, name) is not None

    def resolve(self, user_id: str, name: str) -> ResolvedSecret | None:
        """Resolve a secret, trying user scope first then server."""
        # User scope first
        try:
            value, ref = self._user_store.get_secret(name, user_id=user_id)  # keyword-only
            return ResolvedSecret(name=name, value=value, scope="user", fingerprint=ref.fingerprint)
        except SecretNotFoundError:
            pass
        # Server fallback
        try:
            value, ref = self._server_store.get_secret(name)
            return ResolvedSecret(name=name, value=value, scope="server", fingerprint=ref.fingerprint)
        except SecretNotFoundError:
            return None

    # -- REST API helpers (not part of WebSecretResolver) --------------------

    def set_user_secret(self, user_id: str, name: str, value: str) -> None:
        """Create or update a user-scoped secret."""
        self._user_store.set_secret(name, value=value, user_id=user_id)

    def delete_user_secret(self, user_id: str, name: str) -> bool:
        """Delete a user-scoped secret. Returns True if deleted."""
        return self._user_store.delete_secret(name, user_id=user_id)
