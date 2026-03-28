"""OIDC authentication provider -- JWKS discovery and JWT validation.

Validates tokens issued by any OIDC-compliant identity provider.
The frontend handles the IdP redirect; this backend only validates
the resulting token.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from jose import JWTError, jwt

from elspeth.web.auth.models import AuthenticationError, UserIdentity, UserProfile


class OIDCAuthProvider:
    """Validates OIDC tokens via JWKS discovery."""

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_cache_ttl_seconds: int = 3600,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_cache_ttl_seconds = jwks_cache_ttl_seconds
        self._jwks: dict[str, Any] | None = None
        self._jwks_fetched_at: float = 0.0

    async def _ensure_jwks(self) -> dict[str, Any]:
        """Fetch and cache JWKS keys from the OIDC discovery endpoint."""
        now = time.time()
        if self._jwks is not None and (now - self._jwks_fetched_at) < self._jwks_cache_ttl_seconds:
            return self._jwks

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as client:
                discovery_url = f"{self._issuer}/.well-known/openid-configuration"
                discovery_resp = await client.get(discovery_url)
                discovery_resp.raise_for_status()
                discovery = discovery_resp.json()

                jwks_uri = discovery["jwks_uri"]
                jwks_resp = await client.get(jwks_uri)
                jwks_resp.raise_for_status()
                self._jwks = jwks_resp.json()
                self._jwks_fetched_at = now
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise AuthenticationError(f"Failed to fetch JWKS: {exc}") from exc

        return self._jwks

    def _decode_token(self, token: str, jwks: dict[str, Any]) -> dict[str, Any]:
        """Decode and validate a JWT using the cached JWKS."""
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except JWTError as exc:
            raise AuthenticationError(f"Invalid token: {exc}") from exc
        return payload

    async def authenticate(self, token: str) -> UserIdentity:
        """Validate an OIDC token and return the authenticated identity."""
        jwks = await self._ensure_jwks()
        payload = self._decode_token(token, jwks)

        return UserIdentity(
            user_id=payload["sub"],
            username=payload.get("preferred_username", payload["sub"]),
        )

    async def get_user_info(self, token: str) -> UserProfile:
        """Decode the OIDC token and extract profile claims."""
        jwks = await self._ensure_jwks()
        payload = self._decode_token(token, jwks)

        raw_groups = payload.get("groups")
        if raw_groups is None:
            groups: list[str] = []
        elif isinstance(raw_groups, list):
            groups = [str(g) for g in raw_groups]
        else:
            raise AuthenticationError(
                f"Unexpected type for 'groups' claim: {type(raw_groups).__name__} (expected list) — check IdP token configuration"
            )

        return UserProfile(
            user_id=payload["sub"],
            username=payload.get("preferred_username", payload["sub"]),
            display_name=payload.get("name") or payload.get("preferred_username", "Unknown"),
            email=payload.get("email"),
            groups=tuple(groups),
        )
