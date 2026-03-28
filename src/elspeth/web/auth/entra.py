"""Azure Entra ID authentication provider.

Inherits from OIDCAuthProvider, adding Entra-specific tenant validation
and group/role claim extraction. The OIDC issuer is derived from the
tenant_id.
"""

from __future__ import annotations

from typing import Any

from elspeth.web.auth.models import AuthenticationError, UserIdentity, UserProfile
from elspeth.web.auth.oidc import OIDCAuthProvider


class EntraAuthProvider(OIDCAuthProvider):
    """Validates Azure Entra ID tokens with tenant and group claim handling.

    Extends OIDCAuthProvider with:
    - Tenant ID verification (``tid`` claim must match expected tenant)
    - Group claim extraction (``groups`` + ``role:``-prefixed ``roles``)
    """

    def __init__(
        self,
        tenant_id: str,
        audience: str,
        jwks_cache_ttl_seconds: int = 3600,
    ) -> None:
        self._tenant_id = tenant_id
        issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        super().__init__(
            issuer=issuer,
            audience=audience,
            jwks_cache_ttl_seconds=jwks_cache_ttl_seconds,
        )

    def _validate_tenant(self, payload: dict[str, Any]) -> None:
        """Verify the tid claim matches the expected tenant.

        Raises AuthenticationError if ``tid`` is missing or mismatched.
        The ``tid`` claim is required in Entra ID tokens — absence
        indicates a non-Entra token or a configuration error.
        """
        try:
            tid = payload["tid"]
        except KeyError as exc:
            raise AuthenticationError("Missing tenant claim (tid) — token may not be from Entra ID") from exc
        if tid != self._tenant_id:
            raise AuthenticationError("Invalid tenant")

    def _extract_groups(self, payload: dict[str, Any]) -> tuple[str, ...]:
        """Extract group IDs and role-prefixed entries from Entra claims.

        ``groups`` and ``roles`` are optional Entra claims (Tier 3 data
        from the IdP) — ``.get()`` with empty-list default is correct
        here because absence means "no groups/roles assigned."
        """
        groups: list[str] = []

        raw_groups = payload.get("groups", [])
        if isinstance(raw_groups, list):
            groups.extend(str(g) for g in raw_groups)

        raw_roles = payload.get("roles", [])
        if isinstance(raw_roles, list):
            groups.extend(f"role:{r}" for r in raw_roles)

        return tuple(groups)

    async def authenticate(self, token: str) -> UserIdentity:
        """Validate an Entra ID token with tenant verification.

        Performs standard OIDC validation (signature, expiry, issuer,
        audience) via the inherited _decode_token, then checks the
        tenant claim.
        """
        jwks = await self._ensure_jwks()
        payload = self._decode_token(token, jwks)

        self._validate_tenant(payload)

        return UserIdentity(
            user_id=payload["sub"],
            username=payload.get("preferred_username", payload["sub"]),
        )

    async def get_user_info(self, token: str) -> UserProfile:
        """Decode an Entra ID token and extract profile with group claims."""
        jwks = await self._ensure_jwks()
        payload = self._decode_token(token, jwks)

        self._validate_tenant(payload)

        return UserProfile(
            user_id=payload["sub"],
            username=payload.get("preferred_username", payload["sub"]),
            display_name=payload.get("name", payload.get("preferred_username", payload["sub"])),
            email=payload.get("email"),
            groups=self._extract_groups(payload),
        )
