"""Tests for ServerSecretStore — env-var allowlist enforcement.

Verifies:
- Allowlist boundary: non-allowlisted names always rejected
- Env-var presence: allowlisted but unset names raise SecretNotFoundError
- get_secret returns (value, SecretRef) with correct fingerprint source
- list_secrets exposes metadata only, never values
- Empty allowlist blocks everything
"""

from __future__ import annotations

import os

import pytest

from elspeth.contracts.secrets import SecretInventoryItem
from elspeth.core.security.secret_loader import SecretNotFoundError, SecretRef
from elspeth.web.secrets.server_store import ServerSecretStore


@pytest.fixture()
def _fingerprint_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ELSPETH_FINGERPRINT_KEY is set for _compute_fingerprint."""
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-fp-key")


@pytest.fixture()
def store(_fingerprint_key: None) -> ServerSecretStore:
    """Store with a two-item allowlist."""
    return ServerSecretStore(allowlist=("ALLOWED_KEY_A", "ALLOWED_KEY_B"))


@pytest.fixture()
def empty_store(_fingerprint_key: None) -> ServerSecretStore:
    """Store with an empty allowlist."""
    return ServerSecretStore(allowlist=())


class TestHasSecret:
    """Allowlist + env-var presence gate."""

    def test_allowlisted_and_set_returns_true(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "some-value")
        assert store.has_secret("ALLOWED_KEY_A") is True

    def test_allowlisted_but_unset_returns_false(self, store: ServerSecretStore) -> None:
        os.environ.pop("ALLOWED_KEY_A", None)
        assert store.has_secret("ALLOWED_KEY_A") is False

    def test_allowlisted_but_empty_returns_false(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "")
        assert store.has_secret("ALLOWED_KEY_A") is False

    def test_not_allowlisted_returns_false_even_if_set(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NOT_ALLOWED", "secret-value")
        assert store.has_secret("NOT_ALLOWED") is False

    def test_empty_allowlist_blocks_everything(
        self, empty_store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "value")
        assert empty_store.has_secret("ALLOWED_KEY_A") is False


class TestGetSecret:
    """Value retrieval with allowlist enforcement."""

    def test_returns_value_and_ref(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "my-secret-value")
        value, ref = store.get_secret("ALLOWED_KEY_A")
        assert value == "my-secret-value"
        assert isinstance(ref, SecretRef)
        assert ref.name == "ALLOWED_KEY_A"
        assert ref.source == "env"
        assert len(ref.fingerprint) == 64  # HMAC-SHA256 hex digest

    def test_not_allowlisted_raises(self, store: ServerSecretStore) -> None:
        with pytest.raises(SecretNotFoundError):
            store.get_secret("NOT_ALLOWED")

    def test_allowlisted_but_unset_raises(self, store: ServerSecretStore) -> None:
        os.environ.pop("ALLOWED_KEY_B", None)
        with pytest.raises(SecretNotFoundError):
            store.get_secret("ALLOWED_KEY_B")

    def test_allowlisted_but_empty_raises(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "")
        with pytest.raises(SecretNotFoundError):
            store.get_secret("ALLOWED_KEY_A")

    def test_fingerprint_is_deterministic(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "same-value")
        _, ref1 = store.get_secret("ALLOWED_KEY_A")
        _, ref2 = store.get_secret("ALLOWED_KEY_A")
        assert ref1.fingerprint == ref2.fingerprint

    def test_different_values_different_fingerprints(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "value-one")
        _, ref1 = store.get_secret("ALLOWED_KEY_A")
        monkeypatch.setenv("ALLOWED_KEY_A", "value-two")
        _, ref2 = store.get_secret("ALLOWED_KEY_A")
        assert ref1.fingerprint != ref2.fingerprint


class TestListSecrets:
    """Inventory metadata without exposing values."""

    def test_lists_all_allowlisted_names(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "val-a")
        os.environ.pop("ALLOWED_KEY_B", None)
        items = store.list_secrets()
        assert len(items) == 2
        by_name = {item.name: item for item in items}
        assert by_name["ALLOWED_KEY_A"].available is True
        assert by_name["ALLOWED_KEY_B"].available is False

    def test_inventory_items_have_correct_fields(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOWED_KEY_A", "val")
        items = store.list_secrets()
        item = next(i for i in items if i.name == "ALLOWED_KEY_A")
        assert isinstance(item, SecretInventoryItem)
        assert item.scope == "server"
        assert item.source_kind == "env"

    def test_empty_allowlist_returns_empty(self, empty_store: ServerSecretStore) -> None:
        assert empty_store.list_secrets() == []

    def test_values_never_exposed(
        self, store: ServerSecretStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SecretInventoryItem has no value field — verify structurally."""
        monkeypatch.setenv("ALLOWED_KEY_A", "super-secret")
        items = store.list_secrets()
        item = items[0]
        assert not hasattr(item, "value")
