"""Tests for secret REST API routes.

Security boundaries tested:
- No route ever returns a plaintext secret value in any response body
- Write-only acknowledgement pattern on POST /api/secrets
- Deletion returns 404 for non-existent secrets (not 204)
- Validate endpoint returns existence only, not values
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.secrets.routes import create_secrets_router
from elspeth.web.secrets.server_store import ServerSecretStore
from elspeth.web.secrets.service import WebSecretService
from elspeth.web.secrets.user_store import UserSecretStore
from elspeth.web.sessions.engine import create_session_engine
from elspeth.web.sessions.migrations import run_migrations


@pytest.fixture(autouse=True)
def _ensure_fingerprint_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ELSPETH_FINGERPRINT_KEY is set for all route tests.

    Without it, has_ref() and list_secrets() report secrets as unavailable,
    which is the correct production behaviour but would fail route-level
    assertions that expect available=True after a successful create.
    """
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-routes-fp-key")


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

_TEST_MASTER_KEY = "test-master-key-for-unit-tests"


class _MockSettings:
    """Minimal mock providing the auth_provider field routes need."""

    auth_provider: str = "local"


def _make_app(
    user_id: str = "alice",
    server_allowlist: tuple[str, ...] = (),
) -> FastAPI:
    """Create a test app with secret routes and an in-memory DB."""
    engine = create_session_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    run_migrations(engine)

    user_store = UserSecretStore(engine, _TEST_MASTER_KEY)
    server_store = ServerSecretStore(server_allowlist)
    secret_service = WebSecretService(user_store, server_store)

    app = FastAPI()

    identity = UserIdentity(user_id=user_id, username=user_id)

    async def mock_user() -> UserIdentity:
        return identity

    app.dependency_overrides[get_current_user] = mock_user
    app.state.secret_service = secret_service
    app.state.settings = _MockSettings()

    app.include_router(create_secrets_router())
    return app


# ---------------------------------------------------------------------------
# LIST secrets
# ---------------------------------------------------------------------------


class TestListSecrets:
    """GET /api/secrets -- metadata inventory, no values."""

    def test_list_secrets_empty(self) -> None:
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/api/secrets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_secrets_returns_metadata_no_values(self) -> None:
        """SECURITY: no item in the list may contain a 'value' field."""
        app = _make_app()
        client = TestClient(app)

        # Create a secret first
        client.post("/api/secrets", json={"name": "MY_KEY", "value": "supersecret"})

        resp = client.get("/api/secrets")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1

        for item in items:
            assert "value" not in item, "SECURITY: value must never appear in list response"
            assert "name" in item
            assert "scope" in item
            assert "available" in item

    def test_list_after_create_shows_new_secret(self) -> None:
        """Create a secret then list -- the new name must appear."""
        app = _make_app()
        client = TestClient(app)

        client.post("/api/secrets", json={"name": "NEW_SECRET", "value": "val"})

        resp = client.get("/api/secrets")
        assert resp.status_code == 200
        names = [item["name"] for item in resp.json()]
        assert "NEW_SECRET" in names


# ---------------------------------------------------------------------------
# CREATE secret
# ---------------------------------------------------------------------------


class TestCreateSecret:
    """POST /api/secrets -- write-only create/update."""

    def test_create_secret_returns_ack_no_value(self) -> None:
        """POST returns 201 with name+scope but NOT the value."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "API_KEY", "value": "hunter2"})
        assert resp.status_code == 201

        body = resp.json()
        assert body["name"] == "API_KEY"
        assert body["scope"] == "user"
        assert body["available"] is True

    def test_create_secret_value_not_in_response_body(self) -> None:
        """SECURITY: explicit check that 'value' key is absent from response JSON."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "SECRET", "value": "plaintext"})
        assert resp.status_code == 201

        body = resp.json()
        assert "value" not in body, "SECURITY: plaintext value must NEVER appear in response"

    def test_create_secret_update_existing(self) -> None:
        """POST with an existing name updates the secret (upsert)."""
        app = _make_app()
        client = TestClient(app)

        resp1 = client.post("/api/secrets", json={"name": "KEY", "value": "v1"})
        assert resp1.status_code == 201

        resp2 = client.post("/api/secrets", json={"name": "KEY", "value": "v2"})
        assert resp2.status_code == 201
        assert resp2.json()["name"] == "KEY"

    def test_rejects_whitespace_only_value(self) -> None:
        """SECURITY: whitespace-only secret values must be rejected."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "KEY", "value": "   "})
        assert resp.status_code == 422

    def test_accepts_value_with_leading_whitespace(self) -> None:
        """Values with mixed content (whitespace + non-whitespace) are fine."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "KEY", "value": "  real-key"})
        assert resp.status_code == 201

    def test_rejects_zero_width_space_only_value(self) -> None:
        """SECURITY: zero-width spaces (U+200B) alone have no visible content."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "KEY", "value": "\u200b"})
        assert resp.status_code == 422

    def test_rejects_bom_only_value(self) -> None:
        """SECURITY: BOM character (U+FEFF) alone has no visible content."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "KEY", "value": "\ufeff"})
        assert resp.status_code == 422

    def test_accepts_value_with_visible_and_invisible_chars(self) -> None:
        """Values mixing visible and invisible characters are acceptable."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets", json={"name": "KEY", "value": "\u200breal-secret"})
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# DELETE secret
# ---------------------------------------------------------------------------


class TestDeleteSecret:
    """DELETE /api/secrets/{name} -- remove user-scoped secret."""

    def test_delete_user_secret(self) -> None:
        """DELETE returns 204 on success."""
        app = _make_app()
        client = TestClient(app)

        client.post("/api/secrets", json={"name": "DOOMED", "value": "val"})

        resp = client.delete("/api/secrets/DOOMED")
        assert resp.status_code == 204

    def test_delete_nonexistent_returns_404(self) -> None:
        """DELETE for a non-existent secret returns 404."""
        app = _make_app()
        client = TestClient(app)

        resp = client.delete("/api/secrets/MISSING")
        assert resp.status_code == 404

    def test_delete_removes_from_list(self) -> None:
        """After deletion, the secret no longer appears in the inventory."""
        app = _make_app()
        client = TestClient(app)

        client.post("/api/secrets", json={"name": "TEMP", "value": "val"})
        client.delete("/api/secrets/TEMP")

        resp = client.get("/api/secrets")
        names = [item["name"] for item in resp.json()]
        assert "TEMP" not in names


# ---------------------------------------------------------------------------
# VALIDATE secret
# ---------------------------------------------------------------------------


class TestValidateSecret:
    """POST /api/secrets/{name}/validate -- existence check."""

    def test_validate_existing_secret(self) -> None:
        """Validate returns available=True for an existing secret."""
        app = _make_app()
        client = TestClient(app)

        client.post("/api/secrets", json={"name": "EXISTS", "value": "val"})

        resp = client.post("/api/secrets/EXISTS/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "EXISTS"
        assert body["available"] is True

    def test_validate_missing_secret(self) -> None:
        """Validate returns available=False for a non-existent secret."""
        app = _make_app()
        client = TestClient(app)

        resp = client.post("/api/secrets/NOPE/validate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "NOPE"
        assert body["available"] is False

    def test_validate_does_not_return_value(self) -> None:
        """SECURITY: validate response must not contain a value field."""
        app = _make_app()
        client = TestClient(app)

        client.post("/api/secrets", json={"name": "CHECK", "value": "secret"})

        resp = client.post("/api/secrets/CHECK/validate")
        body = resp.json()
        assert "value" not in body, "SECURITY: value must never appear in validate response"


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


class TestCrossUserIsolation:
    """SECURITY: secrets are scoped per-user. User B must not see User A's secrets."""

    def _make_two_user_clients(self) -> tuple[TestClient, TestClient]:
        """Create two test clients authenticated as different users sharing the same DB."""
        engine = create_session_engine(
            "sqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        run_migrations(engine)

        user_store = UserSecretStore(engine, _TEST_MASTER_KEY)
        server_store = ServerSecretStore(())
        secret_service = WebSecretService(user_store, server_store)

        mock_settings = _MockSettings()

        # App for User A
        app_a = FastAPI()
        identity_a = UserIdentity(user_id="alice", username="alice")
        app_a.dependency_overrides[get_current_user] = lambda: identity_a
        app_a.state.secret_service = secret_service
        app_a.state.settings = mock_settings
        app_a.include_router(create_secrets_router())

        # App for User B — same service, different identity
        app_b = FastAPI()
        identity_b = UserIdentity(user_id="bob", username="bob")
        app_b.dependency_overrides[get_current_user] = lambda: identity_b
        app_b.state.secret_service = secret_service
        app_b.state.settings = mock_settings
        app_b.include_router(create_secrets_router())

        return TestClient(app_a), TestClient(app_b)

    def test_user_b_cannot_see_user_a_secrets(self) -> None:
        """User B's list must not contain User A's secrets."""
        client_a, client_b = self._make_two_user_clients()

        client_a.post("/api/secrets", json={"name": "ALICE_SECRET", "value": "alice-val"})

        resp_b = client_b.get("/api/secrets")
        assert resp_b.status_code == 200
        names_b = [item["name"] for item in resp_b.json()]
        assert "ALICE_SECRET" not in names_b

    def test_user_b_cannot_delete_user_a_secrets(self) -> None:
        """User B cannot delete User A's secrets."""
        client_a, client_b = self._make_two_user_clients()

        client_a.post("/api/secrets", json={"name": "ALICE_KEY", "value": "val"})

        resp = client_b.delete("/api/secrets/ALICE_KEY")
        assert resp.status_code == 404

        # Verify secret still exists for User A
        resp_a = client_a.get("/api/secrets")
        names_a = [item["name"] for item in resp_a.json()]
        assert "ALICE_KEY" in names_a

    def test_user_b_cannot_validate_user_a_secrets(self) -> None:
        """User B's validate check should not find User A's user-scoped secrets."""
        client_a, client_b = self._make_two_user_clients()

        client_a.post("/api/secrets", json={"name": "ALICE_ONLY", "value": "val"})

        resp = client_b.post("/api/secrets/ALICE_ONLY/validate")
        assert resp.status_code == 200
        assert resp.json()["available"] is False


# ---------------------------------------------------------------------------
# 422 validation response redaction
# ---------------------------------------------------------------------------


class TestSecretValidationRedaction:
    """SECURITY: 422 responses must never echo sensitive request values."""

    _SAFE_KEYS = frozenset({"type", "loc", "msg"})

    @staticmethod
    def _make_app_with_redaction() -> FastAPI:
        """Test app with the global allowlist-based 422 handler."""
        from fastapi.exceptions import RequestValidationError
        from fastapi.responses import JSONResponse

        app = _make_app()
        safe_keys = frozenset({"type", "loc", "msg"})

        @app.exception_handler(RequestValidationError)
        async def handle_validation_error(
            request: Request,
            exc: RequestValidationError,
        ) -> JSONResponse:
            safe_errors = [
                {k: v for k, v in error.items() if k in safe_keys}
                for error in exc.errors()
            ]
            return JSONResponse(status_code=422, content={"detail": safe_errors})

        return app

    def test_422_does_not_echo_secret_value(self) -> None:
        """SECURITY: a 422 must not contain the submitted value."""
        app = self._make_app_with_redaction()
        client = TestClient(app)

        secret_value = "super-secret-hunter2"
        resp = client.post(
            "/api/secrets",
            json={"name": "API_KEY", "value": {"nested": secret_value}},
        )
        assert resp.status_code == 422

        body_text = resp.text
        assert secret_value not in body_text, (
            "SECURITY: secret value must never appear in 422 response"
        )
        for error in resp.json()["detail"]:
            assert "input" not in error
            assert "ctx" not in error
            assert "url" not in error

    def test_422_preserves_error_structure(self) -> None:
        """Redacted errors still have type, loc, msg for client debugging."""
        app = self._make_app_with_redaction()
        client = TestClient(app)

        resp = client.post(
            "/api/secrets",
            json={"name": "API_KEY", "value": {"bad": "type"}},
        )
        assert resp.status_code == 422

        errors = resp.json()["detail"]
        assert len(errors) > 0
        for error in errors:
            assert "type" in error
            assert "loc" in error
            assert "msg" in error
            assert set(error.keys()) <= self._SAFE_KEYS
