"""Tests for OIDCAuthProvider -- JWKS discovery, token validation."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from elspeth.web.auth.models import AuthenticationError, UserIdentity
from elspeth.web.auth.oidc import OIDCAuthProvider
from tests.unit.web.auth.conftest import make_rs256_token

ISSUER = "https://login.example.com"
AUDIENCE = "my-app-client-id"


def _valid_claims(overrides: dict[str, object] | None = None) -> dict[str, object]:
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
    """Patch httpx.AsyncClient to return OIDC discovery and JWKS responses.

    NOTE: Similar fixture exists in test_entra_provider.py.
    Intentionally kept separate — different ISSUER and JWKS URL patterns.
    """

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
        jwks_response,
    ) -> None:
        """Second authenticate should use cached JWKS, not re-fetch."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_cache_ttl_seconds=3600,
        )
        token = make_rs256_token(private_key, _valid_claims())

        # First call: mock returns valid JWKS
        async def success_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status = lambda: None
            if ".well-known/openid-configuration" in url:
                response.json.return_value = {"jwks_uri": f"{ISSUER}/keys", "issuer": ISSUER}
            elif url.endswith("/keys"):
                response.json.return_value = jwks_response
            return response

        success_client = AsyncMock()
        success_client.get = success_get
        success_client.__aenter__ = AsyncMock(return_value=success_client)
        success_client.__aexit__ = AsyncMock(return_value=False)

        with patch("elspeth.web.auth.oidc.httpx.AsyncClient", return_value=success_client):
            await provider.authenticate(token)

        # Second call: mock raises on any HTTP call -- if caching works,
        # this mock is never hit
        async def failing_get(url, **kwargs):
            raise AssertionError("JWKS should have been cached -- HTTP call should not happen")

        failing_client = AsyncMock()
        failing_client.get = failing_get
        failing_client.__aenter__ = AsyncMock(return_value=failing_client)
        failing_client.__aexit__ = AsyncMock(return_value=False)

        with patch("elspeth.web.auth.oidc.httpx.AsyncClient", return_value=failing_client):
            identity = await provider.authenticate(token)
            assert identity.user_id == "user-123"


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

    @pytest.mark.asyncio
    async def test_non_list_groups_claim_raises(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """A groups claim that is not a list should raise AuthenticationError."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims({"groups": "not-a-list"})
        token = make_rs256_token(private_key, claims)
        with (
            mock_httpx_discovery,
            pytest.raises(
                AuthenticationError,
                match="Unexpected type for 'groups' claim",
            ),
        ):
            await provider.get_user_info(token)

    @pytest.mark.asyncio
    async def test_authenticate_missing_preferred_username(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """Without preferred_username, username should fall back to sub."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims()
        del claims["preferred_username"]
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery:
            identity = await provider.authenticate(token)
        assert identity.username == identity.user_id
        assert identity.username == "user-123"


class TestOIDCJWKSFailures:
    """Tests for JWKS discovery network failures."""

    @pytest.mark.asyncio
    async def test_jwks_connect_error_raises(self) -> None:
        """httpx.ConnectError during discovery raises AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)

        async def mock_get(url, **kwargs):
            raise httpx.ConnectError("Connection refused")

        client_mock = AsyncMock()
        client_mock.get = mock_get
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "elspeth.web.auth.oidc.httpx.AsyncClient",
                return_value=client_mock,
            ),
            pytest.raises(AuthenticationError, match="Failed to fetch JWKS"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_jwks_missing_jwks_uri_key_raises(self) -> None:
        """Discovery JSON without jwks_uri key raises AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)

        async def mock_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status = lambda: None
            # Discovery response missing the jwks_uri key
            response.json.return_value = {"issuer": ISSUER}
            return response

        client_mock = AsyncMock()
        client_mock.get = mock_get
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "elspeth.web.auth.oidc.httpx.AsyncClient",
                return_value=client_mock,
            ),
            pytest.raises(AuthenticationError, match="Failed to fetch JWKS"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_jwks_malformed_json_raises(self) -> None:
        """Discovery response with malformed JSON raises AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)

        async def mock_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status = lambda: None
            response.json.side_effect = ValueError("No JSON object could be decoded")
            return response

        client_mock = AsyncMock()
        client_mock.get = mock_get
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "elspeth.web.auth.oidc.httpx.AsyncClient",
                return_value=client_mock,
            ),
            pytest.raises(AuthenticationError, match="Failed to fetch JWKS"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_jwks_cache_expiry_refetches(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """With TTL=0, every authenticate call must re-fetch JWKS."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_cache_ttl_seconds=0,
        )
        token = make_rs256_token(private_key, _valid_claims())
        with mock_httpx_discovery:
            identity1 = await provider.authenticate(token)
            identity2 = await provider.authenticate(token)
        assert identity1.user_id == "user-123"
        assert identity2.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_jwks_stale_cache_served_on_fetch_failure(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """After a successful fetch, if re-fetch fails, stale cache is served."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_cache_ttl_seconds=0,
        )
        token = make_rs256_token(private_key, _valid_claims())

        # First call: successful fetch
        with mock_httpx_discovery:
            identity = await provider.authenticate(token)
            assert identity.user_id == "user-123"

        # Second call: fetch fails, but stale cache should be served
        async def failing_get(url, **kwargs):
            raise httpx.ConnectError("IdP is down")

        failing_client = AsyncMock()
        failing_client.get = failing_get
        failing_client.__aenter__ = AsyncMock(return_value=failing_client)
        failing_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "elspeth.web.auth.oidc.httpx.AsyncClient",
            return_value=failing_client,
        ):
            # Should succeed using stale cache, not raise
            identity2 = await provider.authenticate(token)
            assert identity2.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_jwks_http_error_from_discovery(self) -> None:
        """HTTP 500 from discovery endpoint raises AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)

        async def mock_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Server Error",
                request=MagicMock(),
                response=MagicMock(),
            )
            return response

        client_mock = AsyncMock()
        client_mock.get = mock_get
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "elspeth.web.auth.oidc.httpx.AsyncClient",
                return_value=client_mock,
            ),
            pytest.raises(AuthenticationError, match="Failed to fetch JWKS"),
        ):
            await provider.authenticate("some-token")


class TestOIDCProtocolConformance:
    """Verify OIDCAuthProvider satisfies the AuthProvider protocol."""

    def test_oidc_satisfies_auth_provider(self) -> None:
        from elspeth.web.auth.protocol import AuthProvider

        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        assert isinstance(provider, AuthProvider)
