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

    @pytest.mark.asyncio
    async def test_missing_sub_claim_raises_authentication_error(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """Token without sub claim must raise AuthenticationError, not KeyError."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims()
        del claims["sub"]
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery, pytest.raises(AuthenticationError, match="Missing required 'sub' claim"):
            await provider.authenticate(token)

    @pytest.mark.asyncio
    async def test_blank_sub_claim_raises_authentication_error(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """Token with blank sub must raise AuthenticationError."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims({"sub": ""}))
        with mock_httpx_discovery, pytest.raises(AuthenticationError, match="user_id"):
            await provider.authenticate(token)

    @pytest.mark.asyncio
    async def test_null_preferred_username_authenticate_falls_back_to_sub(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """authenticate() with null preferred_username falls back to sub."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims({"preferred_username": None}))
        with mock_httpx_discovery:
            identity = await provider.authenticate(token)
        assert identity.username == "user-123"

    @pytest.mark.asyncio
    async def test_empty_preferred_username_authenticate_falls_back_to_sub(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """authenticate() with empty preferred_username falls back to sub."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims({"preferred_username": ""}))
        with mock_httpx_discovery:
            identity = await provider.authenticate(token)
        assert identity.username == "user-123"


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
    async def test_get_user_info_no_name_claims_returns_none(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """When IdP provides neither name nor preferred_username, display_name is None."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims()
        del claims["name"]
        del claims["preferred_username"]
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery:
            profile = await provider.get_user_info(token)
        assert profile.display_name is None
        assert profile.username == "user-123"  # Falls back to sub

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

    @pytest.mark.asyncio
    async def test_get_user_info_missing_sub_raises(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """get_user_info must also reject tokens without sub claim."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        claims = _valid_claims()
        del claims["sub"]
        token = make_rs256_token(private_key, claims)
        with mock_httpx_discovery, pytest.raises(AuthenticationError, match="Missing required 'sub' claim"):
            await provider.get_user_info(token)

    @pytest.mark.asyncio
    async def test_get_user_info_blank_sub_raises(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """get_user_info with blank sub must raise AuthenticationError."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims({"sub": ""}))
        with mock_httpx_discovery, pytest.raises(AuthenticationError, match="user_id"):
            await provider.get_user_info(token)

    @pytest.mark.asyncio
    async def test_null_preferred_username_falls_back_to_sub(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """IdP may send preferred_username: null — username must fall back to sub."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims({"preferred_username": None}))
        with mock_httpx_discovery:
            profile = await provider.get_user_info(token)
        assert profile.username == "user-123"

    @pytest.mark.asyncio
    async def test_empty_preferred_username_falls_back_to_sub(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """IdP may send preferred_username: "" — username must fall back to sub."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        token = make_rs256_token(private_key, _valid_claims({"preferred_username": ""}))
        with mock_httpx_discovery:
            profile = await provider.get_user_info(token)
        assert profile.username == "user-123"


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
            pytest.raises(
                AuthenticationError,
                match="missing non-empty string 'jwks_uri'",
            ),
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


class TestOIDCJWKSShapeValidation:
    """Tests that shape-malformed IdP responses surface as AuthenticationError.

    Regression coverage for bug elspeth-c98e8e7047: a JSON-valid response
    with the wrong top-level type must not escape as TypeError/AttributeError
    (which would become HTTP 500 via middleware) and must not poison the
    JWKS cache.
    """

    @staticmethod
    def _patch_responses(discovery_json: object, keys_json: object):
        async def mock_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status = lambda: None
            if ".well-known/openid-configuration" in url:
                response.json.return_value = discovery_json
            else:
                response.json.return_value = keys_json
            return response

        client_mock = AsyncMock()
        client_mock.get = mock_get
        client_mock.__aenter__ = AsyncMock(return_value=client_mock)
        client_mock.__aexit__ = AsyncMock(return_value=False)
        return patch("elspeth.web.auth.oidc.httpx.AsyncClient", return_value=client_mock)

    @pytest.mark.asyncio
    async def test_discovery_json_array_raises_auth_error(self) -> None:
        """Discovery returning a JSON array must raise AuthenticationError, not TypeError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        with (
            self._patch_responses([], {"keys": []}),
            pytest.raises(AuthenticationError, match="not a JSON object"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_discovery_jwks_uri_empty_string_raises(self) -> None:
        """Discovery with empty jwks_uri must raise AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        with (
            self._patch_responses({"jwks_uri": "", "issuer": ISSUER}, {"keys": []}),
            pytest.raises(AuthenticationError, match="non-empty string 'jwks_uri'"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_discovery_jwks_uri_non_string_raises(self) -> None:
        """Discovery with non-string jwks_uri must raise AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        with (
            self._patch_responses({"jwks_uri": 42, "issuer": ISSUER}, {"keys": []}),
            pytest.raises(AuthenticationError, match="non-empty string 'jwks_uri'"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_jwks_json_array_raises_auth_error_and_does_not_poison_cache(self) -> None:
        """JWKS returning a JSON array must raise AuthenticationError and leave cache untouched."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        with (
            self._patch_responses({"jwks_uri": f"{ISSUER}/keys"}, []),
            pytest.raises(AuthenticationError, match="not a JSON object"),
        ):
            await provider.authenticate("some-token")
        # Cache must remain empty: a malformed response must not persist.
        assert provider._validator._jwks is None

    @pytest.mark.asyncio
    async def test_jwks_missing_keys_list_raises(self) -> None:
        """JWKS document without 'keys' list must raise AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        with (
            self._patch_responses({"jwks_uri": f"{ISSUER}/keys"}, {"not_keys": []}),
            pytest.raises(AuthenticationError, match="missing 'keys' list"),
        ):
            await provider.authenticate("some-token")

    @pytest.mark.asyncio
    async def test_jwks_keys_non_list_raises(self) -> None:
        """JWKS document with non-list 'keys' must raise AuthenticationError."""
        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        with (
            self._patch_responses({"jwks_uri": f"{ISSUER}/keys"}, {"keys": "not-a-list"}),
            pytest.raises(AuthenticationError, match="missing 'keys' list"),
        ):
            await provider.authenticate("some-token")


class TestOIDCStaleCacheBackoff:
    """Tests that stale-cache fallback throttles IdP re-fetches during an outage.

    Regression coverage for bug elspeth-7f262cf7e1: once the JWKS cache
    expires during an IdP outage, stale-cache fallback must advance the
    refresh horizon so concurrent auth requests do not all queue behind
    the refresh lock re-hitting a dead IdP.
    """

    @pytest.mark.asyncio
    async def test_stale_cache_throttles_refetch_within_retry_window(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """After a failed refresh with stale cache served, subsequent calls within the retry window must not re-hit the IdP."""
        private_key, _ = rsa_keypair
        # TTL=0: every call is "past due" under the old implementation.
        # Failure retry 60s: second call within this window should NOT re-fetch.
        provider = OIDCAuthProvider(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_cache_ttl_seconds=0,
            jwks_failure_retry_seconds=60,
        )
        token = make_rs256_token(private_key, _valid_claims())

        # Seed the cache with a successful fetch.
        with mock_httpx_discovery:
            await provider.authenticate(token)

        # Now simulate IdP outage. Count network attempts.
        attempt_count = 0

        async def failing_get(url, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            raise httpx.ConnectError("IdP is down")

        failing_client = AsyncMock()
        failing_client.get = failing_get
        failing_client.__aenter__ = AsyncMock(return_value=failing_client)
        failing_client.__aexit__ = AsyncMock(return_value=False)

        with patch("elspeth.web.auth.oidc.httpx.AsyncClient", return_value=failing_client):
            # First call under outage: attempts one fetch, falls back to stale cache.
            identity1 = await provider.authenticate(token)
            # Second call within the 60s backoff window: MUST use cache, not re-fetch.
            identity2 = await provider.authenticate(token)
            # Third call too — still within window.
            identity3 = await provider.authenticate(token)

        assert identity1.user_id == "user-123"
        assert identity2.user_id == "user-123"
        assert identity3.user_id == "user-123"
        # The fix: only one network attempt during the backoff window.
        # Pre-fix behaviour: 3 attempts (one per authenticate call).
        assert attempt_count == 1, (
            f"Expected 1 IdP fetch during backoff window, got {attempt_count}. Stale-cache fallback is not advancing _next_refresh_at."
        )

    @pytest.mark.asyncio
    async def test_retry_window_elapses_allows_new_fetch(
        self,
        rsa_keypair,
        mock_httpx_discovery,
    ) -> None:
        """Once the failure-retry window elapses, a fresh fetch is attempted."""
        private_key, _ = rsa_keypair
        provider = OIDCAuthProvider(
            issuer=ISSUER,
            audience=AUDIENCE,
            jwks_cache_ttl_seconds=0,
            jwks_failure_retry_seconds=60,
        )
        token = make_rs256_token(private_key, _valid_claims())

        # Seed the cache with a successful fetch.
        with mock_httpx_discovery:
            await provider.authenticate(token)

        attempt_count = 0

        async def failing_get(url, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            raise httpx.ConnectError("IdP is down")

        failing_client = AsyncMock()
        failing_client.get = failing_get
        failing_client.__aenter__ = AsyncMock(return_value=failing_client)
        failing_client.__aexit__ = AsyncMock(return_value=False)

        with patch("elspeth.web.auth.oidc.httpx.AsyncClient", return_value=failing_client):
            await provider.authenticate(token)  # first failed fetch
            # Simulate time passing past the retry window.
            provider._validator._next_refresh_at = time.time() - 1
            await provider.authenticate(token)  # should attempt fetch again

        assert attempt_count == 2


class TestOIDCProtocolConformance:
    """Verify OIDCAuthProvider satisfies the AuthProvider protocol."""

    def test_oidc_satisfies_auth_provider(self) -> None:
        from elspeth.web.auth.protocol import AuthProvider

        provider = OIDCAuthProvider(issuer=ISSUER, audience=AUDIENCE)
        assert isinstance(provider, AuthProvider)
