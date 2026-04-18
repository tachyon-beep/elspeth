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
        jwks_failure_retry_seconds: int = 300,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._jwks_cache_ttl_seconds = jwks_cache_ttl_seconds
        # 300s default (5 min): JWKS keys rotate on the order of hours
        # to days, so serving stale keys for up to 5 minutes is safer
        # than forcing concurrent auth requests through a blocked
        # httpx.get to a dead IdP. Lower values amplify the per-retry
        # partial DoS described in elspeth-32982f17cf.
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

        Followers short-circuit when a refresh is already in flight:
        if stale cache is populated and the refresh lock is held, return
        stale immediately rather than queue behind a blocked ``httpx.get``.
        Only the single lock-holder pays the network cost per retry
        window — see elspeth-32982f17cf for the partial-DoS this
        prevents.
        """
        now = time.time()
        if self._jwks is not None and now < self._next_refresh_at:
            return self._jwks

        # Lock-decoupled stale-serve: if another coroutine is already
        # attempting a refresh and we have a cached (possibly stale) JWKS,
        # return it without waiting on the lock. This prevents concurrent
        # auth requests from serializing behind a dead IdP fetch (up to
        # the httpx 15s timeout worst case). The ``locked()`` check is
        # best-effort: if the lock is released between the check and our
        # acquire call, we fall through to the normal double-checked
        # locking path and the re-check inside the lock is authoritative.
        if self._jwks is not None and self._jwks_lock.locked():
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
                # Shape-validation failure — advance the refresh horizon
                # by ``_jwks_failure_retry_seconds`` (the same throttle the
                # network-failure branch below applies) BEFORE re-raising.
                #
                # Why throttle here too: without the horizon advance, a
                # malformed-JSON outage at the IdP causes every concurrent
                # auth request in the critical section to re-hit the IdP —
                # the partial-DoS vector elspeth-32982f17cf closed for
                # network errors.  Shape-failure is functionally
                # indistinguishable at this layer (reachable IdP, bad
                # payload); the thundering herd is identical.
                #
                # Why we still re-raise (no stale-cache return on this
                # path): the CURRENT caller — who triggered the validator
                # — gets a clean 401 so an unrecoverable misconfiguration
                # (IdP rotated its document schema, corrupt reverse proxy,
                # etc.) surfaces as an auth failure rather than a silent
                # fallback.  Subsequent callers within the throttle window
                # short-circuit at the top of ``ensure_jwks`` via the
                # ``self._jwks is not None and now < self._next_refresh_at``
                # gate and receive the previously-validated cached keys —
                # symmetric with the network-failure branch's stale-serve
                # semantics, where only the first caller per window pays
                # the cost of discovering the outage.  If cache is empty
                # (shape failure during bootstrap), the top-of-function
                # gate does not trigger and the window only throttles the
                # single-caller path; every caller still gets 401 until
                # the IdP returns valid JSON.
                if stale_jwks is not None:
                    self._next_refresh_at = now + self._jwks_failure_retry_seconds
                    slog.debug(
                        "JWKS shape validation failed; throttling refresh",
                        issuer=self._issuer,
                        next_refresh_in_seconds=self._jwks_failure_retry_seconds,
                    )
                raise
            except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
                # Narrowed from the historical (HTTPError, KeyError, ValueError,
                # TypeError, AttributeError) catch so that programmer-bug
                # exceptions no longer launder into a stale-cache fallback.
                #
                # After the shape validators (_validate_discovery_document,
                # _validate_jwks_document) were added, IdP payload access at
                # this Tier 3 boundary cannot produce KeyError / TypeError /
                # AttributeError on the happy path — those shapes are
                # rejected upstream as AuthenticationError. Anything in
                # those classes reaching this catch would therefore be a
                # bug in the surrounding try block, and suppressing it to
                # serve stale keys would produce a confident-but-wrong
                # auth decision (CLAUDE.md's "silent wrong result is worse
                # than a crash" rule).
                #
                # The remaining catches preserve the legitimate Tier 3
                # failure modes that must serve stale cache:
                #   - httpx.HTTPError: connect/read timeouts, HTTP 5xx from
                #     the IdP, transport errors. Base class of
                #     RequestError / TransportError / ConnectError /
                #     TimeoutException / HTTPStatusError (raised by
                #     response.raise_for_status()).
                #   - httpx.InvalidURL: explicitly named because it sits
                #     OUTSIDE the HTTPError hierarchy (direct Exception
                #     subclass). Fires when jwks_uri is a non-empty string
                #     but not a parseable URL — the shape validator only
                #     checks the string-ness, not URL syntax, so the IdP
                #     can still feed us junk here.
                #   - ValueError: covers json.JSONDecodeError and
                #     UnicodeDecodeError from response.json() when the
                #     IdP returns non-JSON or mis-encoded bytes.
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
        jwks_failure_retry_seconds: int = 300,
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
