"""OIDC authentication provider -- JWKS discovery and JWT validation.

Validates tokens issued by any OIDC-compliant identity provider.
The frontend handles the IdP redirect; this backend only validates
the resulting token.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import jwt
import structlog
from jwt.exceptions import PyJWTError

from elspeth.web.auth.models import AuthenticationError, UserIdentity, UserProfile

slog = structlog.get_logger()


class JWKSTokenValidator:
    """JWKS discovery, caching, and JWT decode -- shared by OIDC and Entra."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_cache_ttl_seconds: int = 3600,
        jwks_failure_retry_seconds: int = 30,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_cache_ttl_seconds = jwks_cache_ttl_seconds
        self._jwks_failure_retry_seconds = jwks_failure_retry_seconds
        self._jwks: dict[str, Any] | None = None
        # Separate "when should we try to refresh next" from "when did we
        # last succeed." A successful fetch sets this to now+ttl; a failure
        # that serves stale cache sets this to now+failure_retry so concurrent
        # auth requests during an IdP outage don't all queue behind the lock
        # re-hitting a dead IdP.
        self._next_refresh_at: float = 0.0
        self._jwks_lock = asyncio.Lock()

    @staticmethod
    def _validate_discovery_document(discovery: Any) -> str:
        """Shape-validate the OIDC discovery document and return jwks_uri.

        Tier 3 boundary: an IdP (or a misbehaving proxy in front of one)
        can return JSON-valid payloads with the wrong top-level shape.
        Reject them at the boundary as ``AuthenticationError`` rather
        than letting ``TypeError``/``KeyError`` escape as HTTP 500.
        """
        if not isinstance(discovery, dict):
            raise AuthenticationError(f"OIDC discovery document is not a JSON object (got {type(discovery).__name__})")
        jwks_uri = discovery.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri.strip():
            raise AuthenticationError("OIDC discovery document missing non-empty string 'jwks_uri'")
        return jwks_uri

    @staticmethod
    def _validate_jwks_document(jwks: Any) -> dict[str, Any]:
        """Shape-validate the JWKS document.

        Returns the same dict on success; raises ``AuthenticationError``
        on shape mismatch. Called BEFORE caching so a malformed response
        cannot poison ``self._jwks`` for the TTL window.
        """
        if not isinstance(jwks, dict):
            raise AuthenticationError(f"JWKS document is not a JSON object (got {type(jwks).__name__})")
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise AuthenticationError("JWKS document missing 'keys' list")
        return jwks

    async def ensure_jwks(self) -> dict[str, Any]:
        """Fetch and cache JWKS keys from the OIDC discovery endpoint.

        Uses double-checked locking to prevent thundering herd at TTL
        boundary. On fetch failure, serves stale cache if available
        and advances the refresh horizon by ``jwks_failure_retry_seconds``
        so concurrent auth requests during an IdP outage don't all queue
        behind the lock re-hitting a dead IdP. (JWKS keys are long-lived;
        stale keys during a transient IdP blip are safer than a hard
        auth outage.)
        """
        now = time.time()
        if self._jwks is not None and now < self._next_refresh_at:
            return self._jwks

        async with self._jwks_lock:
            # Re-check inside lock (another coroutine may have refreshed)
            now = time.time()
            if self._jwks is not None and now < self._next_refresh_at:
                return self._jwks

            stale_jwks = self._jwks
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                    discovery_url = f"{self._issuer}/.well-known/openid-configuration"
                    discovery_resp = await client.get(discovery_url)
                    discovery_resp.raise_for_status()
                    jwks_uri = self._validate_discovery_document(discovery_resp.json())

                    jwks_resp = await client.get(jwks_uri)
                    jwks_resp.raise_for_status()
                    # Shape-validate BEFORE assigning to cache: a wrong-shaped
                    # response must not poison self._jwks.
                    validated = self._validate_jwks_document(jwks_resp.json())
                    self._jwks = validated
                    self._next_refresh_at = now + self._jwks_cache_ttl_seconds
            except AuthenticationError:
                # Shape-validation failure: do not serve stale cache. The
                # response was reachable but structurally wrong, which is a
                # different failure mode than a network blip and should
                # surface as a clean 401, not a silent fallback.
                raise
            except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError) as exc:
                if stale_jwks is not None:
                    # Serve stale cache -- JWKS keys are long-lived
                    self._next_refresh_at = now + self._jwks_failure_retry_seconds
                    slog.debug(
                        "JWKS fetch failed, serving stale cache",
                        issuer=self._issuer,
                        error=str(exc),
                        next_refresh_in_seconds=self._jwks_failure_retry_seconds,
                    )
                    return stale_jwks
                raise AuthenticationError(f"Failed to fetch JWKS: {exc}") from exc

        return self._jwks

    def decode_token(self, token: str, jwks: dict[str, Any]) -> dict[str, Any]:
        """Decode and validate a JWT using the cached JWKS.

        Extracts the signing key from the JWKS by matching the token's
        ``kid`` header to the correct JWK entry.
        """
        try:
            jwk_set = jwt.PyJWKSet.from_dict(jwks)
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            matched_jwk = None
            for key in jwk_set.keys:
                if key.key_id == kid:
                    matched_jwk = key
                    break
            if matched_jwk is None:
                raise AuthenticationError(f"No matching key found in JWKS for kid={kid!r}")
            # Derive algorithm from the JWK rather than hardcoding RS256.
            # PyJWT's PyJWK.algorithm_name reads the JWK's "alg" field, or
            # infers from "kty" when absent (e.g., kty=RSA → RS256,
            # kty=EC → ES256). This supports providers using ES256, PS256, etc.
            payload: dict[str, Any] = jwt.decode(
                token,
                matched_jwk.key,
                algorithms=[matched_jwk.algorithm_name],
                audience=self._audience,
                issuer=self._issuer,
            )
        except PyJWTError as exc:
            raise AuthenticationError(f"Invalid token: {exc}") from exc
        return payload


class OIDCAuthProvider:
    """Validates OIDC tokens via JWKS discovery."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_cache_ttl_seconds: int = 3600,
        jwks_failure_retry_seconds: int = 30,
    ) -> None:
        self._validator = JWKSTokenValidator(
            issuer,
            audience,
            jwks_cache_ttl_seconds,
            jwks_failure_retry_seconds,
        )

    async def authenticate(self, token: str) -> UserIdentity:
        """Validate an OIDC token and return the authenticated identity."""
        jwks = await self._validator.ensure_jwks()
        payload = self._validator.decode_token(token, jwks)

        try:
            sub = payload["sub"]
        except KeyError as exc:
            raise AuthenticationError("Missing required 'sub' claim in token") from exc

        return UserIdentity(
            user_id=sub,
            # preferred_username is optional — fall back to sub if absent,
            # null, or empty.
            username=payload.get("preferred_username") or sub,
        )

    async def get_user_info(self, token: str) -> UserProfile:
        """Decode the OIDC token and extract profile claims."""
        jwks = await self._validator.ensure_jwks()
        payload = self._validator.decode_token(token, jwks)

        try:
            sub = payload["sub"]
        except KeyError as exc:
            raise AuthenticationError("Missing required 'sub' claim in token") from exc

        raw_groups = payload.get("groups")
        if raw_groups is None:
            groups: list[str] = []
        elif isinstance(raw_groups, list):
            # Coerce group IDs to str — IdPs may send integers (e.g. Entra
            # group object IDs). This is intentional Tier 3 coercion.
            groups = [str(g) for g in raw_groups]
        else:
            raise AuthenticationError(
                f"Unexpected type for 'groups' claim: {type(raw_groups).__name__} (expected list) — check IdP token configuration"
            )

        return UserProfile(
            user_id=sub,
            # preferred_username is optional — fall back to sub if absent,
            # null, or empty. IdPs may send null for this optional claim.
            username=payload.get("preferred_username") or sub,
            display_name=payload.get("name") or payload.get("preferred_username"),
            email=payload.get("email"),
            groups=tuple(groups),
        )
