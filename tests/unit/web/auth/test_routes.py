"""Tests for auth API routes -- /api/auth/login, /api/auth/register, /api/auth/token, /api/auth/me."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from elspeth.web.auth.local import LocalAuthProvider
from elspeth.web.auth.models import AuthenticationError, UserIdentity
from elspeth.web.auth.routes import RegisterRequest, create_auth_router
from elspeth.web.config import WebSettings

_OIDC_FIELDS = {
    "oidc_issuer": "https://issuer.example.com",
    "oidc_audience": "test-audience",
    "oidc_client_id": "test-client-id",
}
_ENTRA_FIELDS = {**_OIDC_FIELDS, "entra_tenant_id": "test-tenant-id"}


def _create_test_app(provider, auth_provider_type: str = "local", **settings_overrides) -> FastAPI:
    """Create a FastAPI app with auth routes for testing."""
    app = FastAPI()
    app.state.auth_provider = provider
    app.state.settings = WebSettings(
        auth_provider=auth_provider_type,
        composer_max_composition_turns=15,
        composer_max_discovery_turns=10,
        composer_timeout_seconds=85.0,
        composer_rate_limit_per_minute=10,
        **settings_overrides,
    )
    app.state.oidc_authorization_endpoint = None
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
        app = _create_test_app(provider, auth_provider_type="oidc", **_OIDC_FIELDS)
        client = TestClient(app)

        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pw"},
        )
        assert response.status_code == 404

    def test_login_not_available_for_entra(self) -> None:
        provider = AsyncMock()
        app = _create_test_app(provider, auth_provider_type="entra", **_ENTRA_FIELDS)
        client = TestClient(app)
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pw"},
        )
        assert response.status_code == 404


class TestRegisterEndpoint:
    """Tests for POST /api/auth/register."""

    def test_register_open_mode_creates_user_and_returns_token(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, registration_mode="open")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "pw123", "display_name": "Bob"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"].split(".")) == 3

    def test_register_open_mode_with_email(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, registration_mode="open")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={
                "username": "bob",
                "password": "pw123",
                "display_name": "Bob",
                "email": "bob@example.com",
            },
        )
        assert response.status_code == 200

    def test_register_closed_mode_returns_404(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, registration_mode="closed")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "pw123", "display_name": "Bob"},
        )
        assert response.status_code == 404

    def test_register_email_verified_mode_returns_501(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, registration_mode="email_verified")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "pw123", "display_name": "Bob"},
        )
        assert response.status_code == 501
        assert "Email verification" in response.json()["detail"]

    def test_register_non_local_provider_returns_404(self) -> None:
        provider = AsyncMock()
        app = _create_test_app(
            provider,
            auth_provider_type="oidc",
            registration_mode="open",
            **_OIDC_FIELDS,
        )
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "pw123", "display_name": "Bob"},
        )
        assert response.status_code == 404

    def test_register_duplicate_username_returns_409(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        provider.create_user("bob", "existing", display_name="Bob")
        app = _create_test_app(provider, registration_mode="open")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "pw123", "display_name": "Bob"},
        )
        assert response.status_code == 409

    def test_register_blank_username_returns_422(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, registration_mode="open")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "  ", "password": "pw123", "display_name": "Bob"},
        )
        assert response.status_code == 422

    def test_register_blank_password_returns_422(self, tmp_path) -> None:
        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        app = _create_test_app(provider, registration_mode="open")
        client = TestClient(app)

        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "", "display_name": "Bob"},
        )
        assert response.status_code == 422


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

    def test_token_refresh_unparseable_claims_rejected(self, tmp_path) -> None:
        """Refresh must fail if pre-verification claim decode failed.

        When the middleware can't decode claims (auth_claims=None), the refresh
        endpoint cannot enforce chain lifetime. It must reject with 401 rather
        than silently skipping the chain age check.
        """
        from unittest.mock import patch

        import jwt as pyjwt

        provider = LocalAuthProvider(
            db_path=tmp_path / "auth.db",
            secret_key="test-key",
        )
        provider.create_user("alice", "pw", display_name="Alice")
        app = _create_test_app(provider)
        client = TestClient(app)

        # Login to get a valid token
        login_resp = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pw"},
        )
        valid_token = login_resp.json()["access_token"]

        # Patch jwt.decode to fail on unverified decode but let authenticate()
        # succeed (it uses the provider's own decode path, not the middleware's).
        original_decode = pyjwt.decode

        def selective_decode(token, *args, **kwargs):
            opts = kwargs.get("options", {})
            if not opts.get("verify_signature", True):
                raise pyjwt.PyJWTError("simulated decode failure")
            return original_decode(token, *args, **kwargs)

        with patch("jwt.decode", side_effect=selective_decode):
            response = client.post(
                "/api/auth/token",
                headers={"Authorization": f"Bearer {valid_token}"},
            )
        assert response.status_code == 401
        assert "claims could not be parsed" in response.json()["detail"]

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
        assert body["registration_mode"] == "open"
        assert body["oidc_issuer"] is None
        assert body["oidc_client_id"] is None

    def test_oidc_provider_returns_issuer_and_client_id(self) -> None:
        provider = AsyncMock()
        app = _create_test_app(
            provider,
            auth_provider_type="oidc",
            oidc_issuer="https://login.example.com",
            oidc_audience="test-audience",
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


class TestTokenRefreshNonLocal:
    """Token refresh must be unavailable for non-local providers."""

    def test_token_refresh_not_available_for_oidc(self) -> None:
        provider = AsyncMock()
        provider.authenticate.return_value = UserIdentity(user_id="alice", username="alice")
        app = _create_test_app(provider, auth_provider_type="oidc", **_OIDC_FIELDS)
        client = TestClient(app)
        response = client.post(
            "/api/auth/token",
            headers={"Authorization": "Bearer some-token"},
        )
        assert response.status_code == 404


class TestMeErrorPath:
    """Tests for /me when get_user_info raises."""

    def test_me_get_user_info_failure_returns_401(self) -> None:
        """If get_user_info raises, /me returns 401 with the detail."""
        mock_provider = AsyncMock()
        mock_provider.authenticate.return_value = UserIdentity(user_id="alice", username="alice")
        mock_provider.get_user_info.side_effect = AuthenticationError("Profile lookup failed")
        app = _create_test_app(mock_provider, auth_provider_type="oidc", **_OIDC_FIELDS)
        client = TestClient(app)
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer valid-token"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Profile lookup failed"


class TestRegisterRequestValidation:
    """Registration must reject invisible-only fields to stay aligned with UserIdentity."""

    def test_rejects_zero_width_space_username(self) -> None:
        with pytest.raises(ValueError, match="visible character"):
            RegisterRequest(username="\u200b", password="password123", display_name="Test")

    def test_rejects_bom_only_username(self) -> None:
        with pytest.raises(ValueError, match="visible character"):
            RegisterRequest(username="\ufeff", password="password123", display_name="Test")

    def test_rejects_invisible_display_name(self) -> None:
        with pytest.raises(ValueError, match="visible character"):
            RegisterRequest(username="alice", password="password123", display_name="\u200b")

    def test_rejects_invisible_password(self) -> None:
        with pytest.raises(ValueError, match="visible character"):
            RegisterRequest(username="alice", password="\u200b", display_name="Test")

    def test_accepts_normal_registration(self) -> None:
        req = RegisterRequest(username="alice", password="password123", display_name="Alice")
        assert req.username == "alice"
