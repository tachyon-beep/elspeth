"""Tests for the get_current_user FastAPI auth dependency."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import AuthenticationError, UserIdentity


def _create_test_app(auth_provider) -> FastAPI:
    """Create a minimal FastAPI app with auth middleware for testing."""
    app = FastAPI()
    app.state.auth_provider = auth_provider

    @app.get("/protected")
    async def protected(user: UserIdentity = Depends(get_current_user)):  # noqa: B008
        return {"user_id": user.user_id, "username": user.username}

    return app


class TestGetCurrentUser:
    """Tests for the auth middleware dependency."""

    def test_valid_bearer_token(self) -> None:
        mock_provider = AsyncMock()
        mock_provider.authenticate.return_value = UserIdentity(
            user_id="alice",
            username="alice",
        )
        app = _create_test_app(mock_provider)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer valid-token-here"},
        )
        assert response.status_code == 200
        assert response.json()["user_id"] == "alice"
        mock_provider.authenticate.assert_called_once_with("valid-token-here")

    def test_missing_authorization_header(self) -> None:
        mock_provider = AsyncMock()
        app = _create_test_app(mock_provider)
        client = TestClient(app)

        response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing or invalid Authorization header"

    def test_non_bearer_scheme(self) -> None:
        mock_provider = AsyncMock()
        app = _create_test_app(mock_provider)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert response.status_code == 401

    def test_bearer_with_no_token(self) -> None:
        mock_provider = AsyncMock()
        app = _create_test_app(mock_provider)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer"},
        )
        assert response.status_code == 401

    def test_invalid_token_returns_401_with_detail(self) -> None:
        mock_provider = AsyncMock()
        mock_provider.authenticate.side_effect = AuthenticationError("Token expired")
        app = _create_test_app(mock_provider)
        client = TestClient(app)

        response = client.get(
            "/protected",
            headers={"Authorization": "Bearer expired-token"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Token expired"
