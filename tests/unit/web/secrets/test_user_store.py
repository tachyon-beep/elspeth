"""Tests for UserSecretStore — Fernet-encrypted user secret persistence.

Verifies:
- Round-trip encrypt/decrypt integrity
- User-scoped isolation (user A cannot see user B's secrets)
- Upsert semantics (second set overwrites first)
- Delete lifecycle
- List returns metadata only (no values)
- SecretNotFoundError on missing secrets
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from elspeth.contracts.secrets import SecretInventoryItem
from elspeth.core.security.secret_loader import SecretNotFoundError
from elspeth.web.secrets.user_store import UserSecretStore
from elspeth.web.sessions.models import metadata

TEST_MASTER_KEY = "test-master-key-for-encryption"


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with all session tables created."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)
    return engine


@pytest.fixture()
def store(db_engine) -> UserSecretStore:
    return UserSecretStore(engine=db_engine, master_key=TEST_MASTER_KEY)


class TestUserSecretStore:
    def test_store_and_retrieve_roundtrip(self, store: UserSecretStore) -> None:
        """Set a secret then get it back — value must match."""
        store.set_secret("API_KEY", value="sk-secret-123", user_id="user-1")
        value, ref = store.get_secret("API_KEY", user_id="user-1")

        assert value == "sk-secret-123"
        assert ref.name == "API_KEY"
        assert ref.source == "user"
        assert ref.fingerprint == ""

    def test_different_users_isolated(self, store: UserSecretStore) -> None:
        """User A's secret must not be visible to user B."""
        store.set_secret("API_KEY", value="alice-key", user_id="alice")
        store.set_secret("API_KEY", value="bob-key", user_id="bob")

        alice_val, _ = store.get_secret("API_KEY", user_id="alice")
        bob_val, _ = store.get_secret("API_KEY", user_id="bob")

        assert alice_val == "alice-key"
        assert bob_val == "bob-key"

    def test_upsert_updates_existing(self, store: UserSecretStore) -> None:
        """Setting the same name twice must overwrite the first value."""
        store.set_secret("TOKEN", value="old-value", user_id="user-1")
        store.set_secret("TOKEN", value="new-value", user_id="user-1")

        value, _ = store.get_secret("TOKEN", user_id="user-1")
        assert value == "new-value"

    def test_delete_removes_secret(self, store: UserSecretStore) -> None:
        """Delete then get must raise SecretNotFoundError."""
        store.set_secret("TEMP", value="ephemeral", user_id="user-1")
        result = store.delete_secret("TEMP", user_id="user-1")
        assert result is True

        with pytest.raises(SecretNotFoundError):
            store.get_secret("TEMP", user_id="user-1")

    def test_delete_nonexistent_returns_false(self, store: UserSecretStore) -> None:
        """Deleting a secret that doesn't exist returns False."""
        result = store.delete_secret("NOPE", user_id="user-1")
        assert result is False

    def test_list_returns_metadata_only(self, store: UserSecretStore) -> None:
        """List must return names and scope, never values."""
        store.set_secret("KEY_A", value="val-a", user_id="user-1")
        store.set_secret("KEY_B", value="val-b", user_id="user-1")

        items = store.list_secrets(user_id="user-1")
        assert len(items) == 2

        names = {item.name for item in items}
        assert names == {"KEY_A", "KEY_B"}

        for item in items:
            assert isinstance(item, SecretInventoryItem)
            assert item.scope == "user"
            assert item.available is True
            assert item.source_kind == "user_store"
            # SecretInventoryItem has no value field — metadata only by design

    def test_get_nonexistent_raises(self, store: UserSecretStore) -> None:
        """Getting a secret that doesn't exist must raise SecretNotFoundError."""
        with pytest.raises(SecretNotFoundError):
            store.get_secret("MISSING", user_id="user-1")
