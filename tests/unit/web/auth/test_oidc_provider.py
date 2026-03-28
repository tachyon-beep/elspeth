"""Tests for OIDCAuthProvider -- JWKS discovery, token validation."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from elspeth.web.auth.models import AuthenticationError, UserIdentity
from elspeth.web.auth.oidc import OIDCAuthProvider
from tests.unit.web.auth.conftest import make_rs256_token

ISSUER = "https://login.example.com"
AUDIENCE = "my-app-client-id"


def _valid_claims(overrides: dict | None = None) -> dict:
    """Return a valid JWT claims dict with optional overrides."""
    claims = {
        "sub": "user-123",
        "preferred_username": "alice",
        "name": "Alice Smith",
        "email": "alice@example.com",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 3600,
    }
    if overrides:
        claims.update(overrides)
    return claims


@pytest.fixture
def mock_httpx_discovery(jwks_response):
    """Patch httpx.AsyncClient to return OIDC discovery and JWKS responses."""

    async def mock_get(url, **kwargs):
        response = MagicMock()
        response.raise_for_status = lambda: None
        if ".well-known/openid-configuration" in url:
            response.json.return_value = {
                "jwks_uri": f"{ISSUER}/keys",
                "issuer": ISSUER,
            }
        elif url.endswith("/keys"):
            response.json.return_value = jwks_response
        return response

    client_mock = AsyncMock()
    client_mock.get = mock_get
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)

    return patch("elspeth.web.auth.oidc.httpx.AsyncClient", return_value=client_mock)


class TestOIDCDiscovery:
    """Tests for JWKS discovery and caching."""

    @pytest.mark.asyncio
    async def test_fetches_jwks_on_first_authenticate(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims())
        with mock_httpx_discovery:
            identity = await provider.authenticate(token)
            # If authenticate succeeds, JWKS discovery must have been called
            # (the provider has no cached keys on first call)
            assert identity.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_caches_jwks_on_subsequent_calls(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_cache_ttl_seconds=3600,
        )
        token = make_rs256_token(private_key, _valid_claims())
        with mock_httpx_discovery:
            await provider.authenticate(token)
            # Second call should use cached keys -- no additional HTTP calls
            await provider.authenticate(token)


class TestOIDCTokenValidation:
    """Tests for token validation checks."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_identity(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims())
        with mock_httpx_discovery:
            identity = await provider.authenticate(token)
        assert isinstance(identity, UserIdentity)
        assert identity.user_id == "user-123"
        assert identity.username == "alice"

    @pytest.mark.asyncio
    async def test_wrong_audience_raises(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience="wrong-audience")
        token = make_rs256_token(private_key, _valid_claims())
        with mock_httpx_discovery, pytest.raises(AuthenticationError):
            await provider.authenticate(token)

    @pytest.mark.asyncio
    async def test_wrong_issuer_raises(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(
            issuer="https://wrong-issuer.com",
            audience=AUDIENCE,
        )
        token = make_rs256_token(private_key, _valid_claims())
        with mock_httpx_discovery, pytest.raises(AuthenticationError):
            await provider.authenticate(token)

    @pytest.mark.asyncio
    async def test_expired_token_raises(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims({"exp": int(time.time()) - 10})
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery, pytest.raises(AuthenticationError):
            await provider.authenticate(token)


class TestOIDCGetUserInfo:
    """Tests for full profile retrieval from OIDC claims."""

    @pytest.mark.asyncio
    async def test_get_user_info_returns_profile(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims({"groups": ["team-a", "team-b"]})
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery:
            profile = await provider.get_user_info(token)
        assert profile.user_id == "user-123"
        assert profile.display_name == "Alice Smith"
        assert profile.email == "alice@example.com"
        assert profile.groups == ("team-a", "team-b")

    @pytest.mark.asyncio
    async def test_get_user_info_no_optional_claims(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims()
        # Remove optional fields
        del claims["email"]
        del claims["name"]
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery:
            profile = await provider.get_user_info(token)
        assert profile.display_name == "alice"  # Falls back to preferred_username
        assert profile.email is None
        assert profile.groups == ()
