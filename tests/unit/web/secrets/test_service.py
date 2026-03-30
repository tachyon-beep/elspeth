"""Tests for WebSecretService -- chained user -> server resolution."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from elspeth.core.security.secret_loader import SecretNotFoundError
from elspeth.web.secrets.server_store import ServerSecretStore
from elspeth.web.secrets.service import WebSecretService
from elspeth.web.secrets.user_store import UserSecretStore
from elspeth.web.sessions.models import metadata as session_metadata


@pytest.fixture()
def engine() -> sa.engine.Engine:
    """In-memory SQLite engine with session tables created."""
    eng = sa.create_engine("sqlite:///:memory:")
    session_metadata.create_all(eng)
    return eng


@pytest.fixture()
def user_store(engine: sa.engine.Engine) -> UserSecretStore:
    """UserSecretStore backed by in-memory SQLite."""
    return UserSecretStore(engine=engine, master_key="test-master-key-32chars-minimum!")


@pytest.fixture()
def server_store(monkeypatch: pytest.MonkeyPatch) -> ServerSecretStore:
    """ServerSecretStore with TEST_KEY in allowlist."""
    monkeypatch.setenv("TEST_KEY", "env-value")
    return ServerSecretStore(allowlist=("TEST_KEY",))


@pytest.fixture()
def service(user_store: UserSecretStore, server_store: ServerSecretStore) -> WebSecretService:
    return WebSecretService(user_store=user_store, server_store=server_store)


class TestResolve:
    def test_user_secret_takes_priority_over_server(
        self,
        service: WebSecretService,
        user_store: UserSecretStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the same secret exists in both user and server stores, user wins."""
        monkeypatch.setenv("TEST_KEY", "server-value")
        user_store.set_secret("TEST_KEY", value="user-value", user_id="user-1")

        result = service.resolve("user-1", "TEST_KEY")

        assert result is not None
        assert result.value == "user-value"
        assert result.scope == "user"

    def test_server_fallback_when_user_missing(
        self,
        service: WebSecretService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When user has no secret, falls back to server store."""
        monkeypatch.setenv("TEST_KEY", "env-value")

        result = service.resolve("user-1", "TEST_KEY")

        assert result is not None
        assert result.value == "env-value"
        assert result.scope == "server"

    def test_resolve_returns_none_when_missing(self, service: WebSecretService) -> None:
        """Returns None when secret is not in either store."""
        result = service.resolve("user-1", "NONEXISTENT")

        assert result is None

    def test_has_ref_checks_both_scopes(
        self,
        service: WebSecretService,
        user_store: UserSecretStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """has_ref returns True for secrets in either scope."""
        monkeypatch.setenv("TEST_KEY", "env-value")
        user_store.set_secret("USER_ONLY", value="val", user_id="user-1")

        # Server scope
        assert service.has_ref("user-1", "TEST_KEY") is True
        # User scope
        assert service.has_ref("user-1", "USER_ONLY") is True
        # Neither
        assert service.has_ref("user-1", "NONEXISTENT") is False


class TestListRefs:
    def test_list_refs_merges_scopes(
        self,
        service: WebSecretService,
        user_store: UserSecretStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """list_refs returns items from both user and server stores."""
        monkeypatch.setenv("TEST_KEY", "env-value")
        user_store.set_secret("MY_SECRET", value="user-val", user_id="user-1")

        refs = service.list_refs("user-1")
        names = [r.name for r in refs]

        assert "TEST_KEY" in names
        assert "MY_SECRET" in names

    def test_list_refs_deduplicates_by_name(
        self,
        service: WebSecretService,
        user_store: UserSecretStore,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When same name exists in both scopes, user scope wins in listing."""
        monkeypatch.setenv("TEST_KEY", "env-value")
        user_store.set_secret("TEST_KEY", value="user-value", user_id="user-1")

        refs = service.list_refs("user-1")
        test_key_items = [r for r in refs if r.name == "TEST_KEY"]

        assert len(test_key_items) == 1
        assert test_key_items[0].scope == "user"


class TestCrud:
    def test_set_and_delete_user_secret(
        self,
        service: WebSecretService,
    ) -> None:
        """CRUD pass-through to user store works correctly."""
        # Set
        service.set_user_secret("user-1", "MY_KEY", "my-value")

        result = service.resolve("user-1", "MY_KEY")
        assert result is not None
        assert result.value == "my-value"
        assert result.scope == "user"

        # Delete
        deleted = service.delete_user_secret("user-1", "MY_KEY")
        assert deleted is True

        # Gone
        result = service.resolve("user-1", "MY_KEY")
        assert result is None

        # Double delete
        deleted = service.delete_user_secret("user-1", "MY_KEY")
        assert deleted is False


class TestServerStore:
    def test_allowlist_restricts_access(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ServerSecretStore only exposes allowlisted env vars."""
        monkeypatch.setenv("ALLOWED", "yes")
        monkeypatch.setenv("FORBIDDEN", "no")
        store = ServerSecretStore(allowlist=("ALLOWED",))

        value, ref = store.get_secret("ALLOWED")
        assert value == "yes"
        assert ref.source == "env"

        with pytest.raises(SecretNotFoundError):
            store.get_secret("FORBIDDEN")

    def test_missing_env_var_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Allowlisted but unset env var raises SecretNotFoundError."""
        monkeypatch.delenv("MISSING_KEY", raising=False)
        store = ServerSecretStore(allowlist=("MISSING_KEY",))

        with pytest.raises(SecretNotFoundError):
            store.get_secret("MISSING_KEY")

    def test_list_secrets_shows_availability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """list_secrets shows which allowlisted vars are set vs missing."""
        monkeypatch.setenv("SET_KEY", "val")
        monkeypatch.delenv("UNSET_KEY", raising=False)
        store = ServerSecretStore(allowlist=("SET_KEY", "UNSET_KEY"))

        items = store.list_secrets()
        by_name = {i.name: i for i in items}

        assert by_name["SET_KEY"].available is True
        assert by_name["UNSET_KEY"].available is False
        assert by_name["SET_KEY"].scope == "server"
        assert by_name["SET_KEY"].source_kind == "env"
