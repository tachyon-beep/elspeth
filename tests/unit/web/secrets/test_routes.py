"""Tests for secret REST API routes.

Security boundaries tested:
- No route ever returns a plaintext secret value in any response body
- Write-only acknowledgement pattern on POST /api/secrets
- Deletion returns 404 for non-existent secrets (not 204)
- Validate endpoint returns existence only, not values
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.secrets.routes import create_secrets_router
from elspeth.web.secrets.server_store import ServerSecretStore
from elspeth.web.secrets.service import WebSecretService
from elspeth.web.secrets.user_store import UserSecretStore
from elspeth.web.sessions.models import metadata

# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------

_TEST_MASTER_KEY = "test-master-key-for-unit-tests"


def _make_app(
    user_id: str = "alice",
    server_allowlist: tuple[str, ...] = (),
) -> FastAPI:
    """Create a test app with secret routes and an in-memory DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    metadata.create_all(engine)

    user_store = UserSecretStore(engine, _TEST_MASTER_KEY)
    server_store = ServerSecretStore(server_allowlist)
    secret_service = WebSecretService(user_store, server_store)

    app = FastAPI()

    identity = UserIdentity(user_id=user_id, username=user_id)

    async def mock_user() -> UserIdentity:
        return identity

    app.dependency_overrides[get_current_user] = mock_user
    app.state.secret_service = secret_service

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
