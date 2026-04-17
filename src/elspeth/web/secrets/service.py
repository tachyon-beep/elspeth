"""WebSecretService -- composes user + server stores; ScopedSecretResolver adapts it to WebSecretResolver."""

from __future__ import annotations

from elspeth.contracts.secrets import ResolvedSecret, SecretInventoryItem
from elspeth.web.secrets.server_store import ServerSecretStore
from elspeth.web.secrets.user_store import UserSecretStore


class WebSecretService:
    """Chained secret resolution: user -> server.

    All methods require ``auth_provider_type`` to scope user secrets by
    auth provider — the web layer treats (user_id, auth_provider_type) as
    the ownership boundary.  Server secrets are deployment-scoped and do
    not use auth_provider_type.

    Also exposes ``set_user_secret`` / ``delete_user_secret`` for the
    REST API layer.
    """

    def __init__(self, user_store: UserSecretStore, server_store: ServerSecretStore) -> None:
        self._user_store = user_store
        self._server_store = server_store

    # -- Resolution methods ------------------------------------------------

    def list_refs(self, user_id: str, *, auth_provider_type: str) -> list[SecretInventoryItem]:
        """Merge user and server inventories; user scope wins on name clash."""
        user_items = {
            item.name: item
            for item in self._user_store.list_secrets(user_id=user_id, auth_provider_type=auth_provider_type)
        }
        server_items = {item.name: item for item in self._server_store.list_secrets()}
        merged = {**server_items, **user_items}  # user scope wins
        return sorted(merged.values(), key=lambda x: x.name)

    def has_ref(self, user_id: str, name: str, *, auth_provider_type: str) -> bool:
        """Check whether *name* is resolvable in either scope.

        User scope shadows server scope by name: if the user has stored a
        row for ``name``, that row controls availability even when it is
        currently undecryptable.  This keeps validation aligned with
        list_refs(), where user scope also wins on name clash.
        """
        if self._user_store.has_secret_record(
            name, user_id=user_id, auth_provider_type=auth_provider_type
        ):
            return self._user_store.has_secret(
                name, user_id=user_id, auth_provider_type=auth_provider_type
            )
        return self._server_store.has_secret(name)

    def resolve(self, user_id: str, name: str, *, auth_provider_type: str) -> ResolvedSecret | None:
        """Resolve a secret, trying user scope first then server.

        Returns None for missing secrets — callers (resolve_secret_refs in
        core/secrets.py) batch all missing refs and raise SecretResolutionError.
        """
        # User scope first
        if self._user_store.has_secret_record(
            name, user_id=user_id, auth_provider_type=auth_provider_type
        ):
            if not self._user_store.has_secret(
                name, user_id=user_id, auth_provider_type=auth_provider_type
            ):
                return None
            value, ref = self._user_store.get_secret(
                name, user_id=user_id, auth_provider_type=auth_provider_type
            )
            return ResolvedSecret(name=name, value=value, scope="user", fingerprint=ref.fingerprint)
        # Server fallback
        if not self._server_store.has_secret(name):
            return None
        value, ref = self._server_store.get_secret(name)
        return ResolvedSecret(name=name, value=value, scope="server", fingerprint=ref.fingerprint)

    # -- REST API helpers (not part of WebSecretResolver) --------------------

    def set_user_secret(self, user_id: str, name: str, value: str, *, auth_provider_type: str) -> None:
        """Create or update a user-scoped secret."""
        self._user_store.set_secret(name, value=value, user_id=user_id, auth_provider_type=auth_provider_type)

    def delete_user_secret(self, user_id: str, name: str, *, auth_provider_type: str) -> bool:
        """Delete a user-scoped secret. Returns True if deleted."""
        return self._user_store.delete_secret(name, user_id=user_id, auth_provider_type=auth_provider_type)


class ScopedSecretResolver:
    """Binds auth_provider_type into the WebSecretResolver protocol.

    The ``WebSecretResolver`` protocol (L0) uses ``(user_id, name)`` as
    the resolution key.  The web layer scopes user secrets by
    ``(user_id, auth_provider_type, name)``.  This adapter bridges the
    gap so ``resolve_secret_refs()`` in L1 can resolve secrets without
    knowing about auth providers — preserving layer boundaries.

    ``auth_provider_type`` comes from ``WebSettings.auth_provider`` and
    is deployment-level (the same for all requests to a given server).
    """

    def __init__(self, service: WebSecretService, auth_provider_type: str) -> None:
        self._service = service
        self._auth_provider_type = auth_provider_type

    def list_refs(self, user_id: str) -> list[SecretInventoryItem]:
        return self._service.list_refs(user_id, auth_provider_type=self._auth_provider_type)

    def has_ref(self, user_id: str, name: str) -> bool:
        return self._service.has_ref(user_id, name, auth_provider_type=self._auth_provider_type)

    def resolve(self, user_id: str, name: str) -> ResolvedSecret | None:
        return self._service.resolve(user_id, name, auth_provider_type=self._auth_provider_type)
