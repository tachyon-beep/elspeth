"""Tests for auth API routes -- /api/auth/login, /api/auth/token, /api/auth/me."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from starlette.testclient import TestClient

from elspeth.web.auth.local import LocalAuthProvider
from elspeth.web.auth.routes import create_auth_router
from elspeth.web.config import WebSettings


def _create_test_app(provider, auth_provider_type: str = "local", **settings_overrides) -> FastAPI:
    """Create a FastAPI app with auth routes for testing."""
    app = FastAPI()
    app.state.auth_provider = provider
    app.state.settings = WebSettings(auth_provider=auth_provider_type, **settings_overrides)
    router = create_auth_router()
    app.include_router(router)
    return app


class TestLoginEndpoint:
    """Tests for POST /api/auth/login."""

    def test_login_valid_credentials(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        provider.create_user("alice", "password123", display_name="Alice")
        app = _create_test_app(provider)
        client = TestClient(app)

        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "password123"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        # Verify it's a valid JWT (three segments)
        assert len(body["access_token"].split(".")) == 3

    def test_login_invalid_credentials(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        provider.create_user("alice", "password123", display_name="Alice")
        app = _create_test_app(provider)
        client = TestClient(app)

        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_login_not_available_for_oidc(self, tmp_path) -> None:
        provider = AsyncMock()
        app = _create_test_app(provider, auth_provider_type="oidc")
        client = TestClient(app)

        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pw"},
        )
        assert response.status_code == 404


class TestTokenRefreshEndpoint:
    """Tests for POST /api/auth/token."""

    def test_token_refresh_returns_new_token(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        provider.create_user("alice", "pw", display_name="Alice")
        app = _create_test_app(provider)
        client = TestClient(app)

        # Login first
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pw"},
        )
        old_token = login_resp.json()["access_token"]

        # Refresh
        refresh_resp = client.post(
            "/api/auth/token",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        assert refresh_resp.status_code == 200
        new_body = refresh_resp.json()
        assert "access_token" in new_body
        assert new_body["token_type"] == "bearer"

    def test_token_refresh_invalid_token(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider)
        client = TestClient(app)

        response = client.post(
            "/api/auth/token",
            headers={"Authorization": "Bearer garbage"},
        )
        assert response.status_code == 401


class TestMeEndpoint:
    """Tests for GET /api/auth/me."""

    def test_me_returns_profile(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        provider.create_user(
            "alice",
            "pw",
            display_name="Alice Smith",
            email="alice@example.com",
        )
        app = _create_test_app(provider)
        client = TestClient(app)

        login_resp = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pw"},
        )
        token = login_resp.json()["access_token"]

        me_resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        body = me_resp.json()
        assert body["user_id"] == "alice"
        assert body["display_name"] == "Alice Smith"
        assert body["email"] == "alice@example.com"
        assert body["groups"] == []

    def test_me_unauthenticated(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider)
        client = TestClient(app)

        response = client.get("/api/auth/me")
        assert response.status_code == 401


class TestAuthConfigEndpoint:
    """Tests for GET /api/auth/config (S9/D5)."""

    def test_local_provider_returns_null_oidc_fields(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, auth_provider_type="local")
        client = TestClient(app)

        response = client.get("/api/auth/config")
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "local"
        assert body["oidc_issuer"] is None
        assert body["oidc_client_id"] is None

    def test_oidc_provider_returns_issuer_and_client_id(self) -> None:
        provider = AsyncMock()
        app = _create_test_app(
            provider,
            auth_provider_type="oidc",
            oidc_issuer="https://login.example.com",
            oidc_client_id="my-client-id",
        )
        client = TestClient(app)

        response = client.get("/api/auth/config")
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "oidc"
        assert body["oidc_issuer"] == "https://login.example.com"
        assert body["oidc_client_id"] == "my-client-id"

    def test_config_endpoint_is_unauthenticated(self) -> None:
        """GET /api/auth/config must not require a Bearer token."""
        provider = AsyncMock()
        app = _create_test_app(provider, auth_provider_type="local")
        client = TestClient(app)

        # No Authorization header -- should still return 200
        response = client.get("/api/auth/config")
        assert response.status_code == 200
