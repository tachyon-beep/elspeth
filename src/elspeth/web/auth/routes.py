"""Auth API routes -- /api/auth/login, /api/auth/token, /api/auth/config, /api/auth/me.

POST /login is only available when auth_provider is "local".
POST /token re-issues a JWT from a valid existing token (local only).
GET /config returns auth configuration for frontend discovery (unauthenticated).
GET /me returns the full UserProfile for any auth provider.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import AuthenticationError, UserIdentity
from elspeth.web.auth.protocol import AuthProvider, CredentialAuthProvider
from elspeth.web.config import WebSettings


class LoginRequest(BaseModel):
    """Request body for POST /api/auth/login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response for login and token refresh."""

    access_token: str
    token_type: str = "bearer"


class UserProfileResponse(BaseModel):
    """Response for GET /api/auth/me."""

    user_id: str
    username: str
    display_name: str
    email: str | None = None
    groups: list[str] = []


class AuthConfigResponse(BaseModel):
    """Response for GET /api/auth/config."""

    provider: str
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    authorization_endpoint: str | None = None


def create_auth_router() -> APIRouter:
    """Create the auth router with /api/auth prefix."""
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.post("/login", response_model=TokenResponse)
    async def login(body: LoginRequest, request: Request) -> TokenResponse:
        """Authenticate with username/password (local auth only).

        login() is synchronous (bcrypt is intentionally slow ~200ms),
        so it is offloaded to a thread to avoid blocking the event loop.

        No CSRF token required — this is a bearer-token-only API (no
        cookies). If cookie-based sessions are added later, CSRF
        protection must be revisited.
        """
        settings: WebSettings = request.app.state.settings
        if settings.auth_provider != "local":
            raise HTTPException(status_code=404, detail="Not found")

        provider: CredentialAuthProvider = request.app.state.auth_provider
        try:
            token = await provider.login(body.username, body.password)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

        return TokenResponse(access_token=token)

    @router.post("/token", response_model=TokenResponse)
    async def refresh_token(
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> TokenResponse:
        """Re-issue a JWT from a valid existing token (local auth only).

        Uses the provider's public refresh() method rather than
        reaching into private attributes.
        """
        settings: WebSettings = request.app.state.settings
        if settings.auth_provider != "local":
            raise HTTPException(status_code=404, detail="Not found")

        provider: CredentialAuthProvider = request.app.state.auth_provider
        new_token = await provider.refresh(user.user_id, user.username)
        return TokenResponse(access_token=new_token)

    @router.get("/config", response_model=AuthConfigResponse)
    async def auth_config(request: Request) -> AuthConfigResponse:
        """Return auth configuration for frontend discovery.

        This endpoint is unauthenticated -- the frontend needs it
        before any login flow.
        """
        settings: WebSettings = request.app.state.settings
        return AuthConfigResponse(
            provider=settings.auth_provider,
            oidc_issuer=settings.oidc_issuer,
            oidc_client_id=settings.oidc_client_id,
            authorization_endpoint=request.app.state.oidc_authorization_endpoint,
        )

    @router.get("/me", response_model=UserProfileResponse)
    async def me(
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> UserProfileResponse:
        """Return the full profile of the authenticated user.

        The raw token was stashed on request.state.auth_token by
        get_current_user, so we don't re-parse the Authorization header.
        """
        # Note: authenticate() already decoded the JWT in get_current_user.
        # get_user_info() decodes it again to extract profile claims.
        # This is intentional — the middleware returns UserIdentity (minimal),
        # while /me needs the full UserProfile with groups/email/display_name.
        token: str = request.state.auth_token
        auth_provider: AuthProvider = request.app.state.auth_provider

        try:
            profile = await auth_provider.get_user_info(token)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=exc.detail) from exc

        return UserProfileResponse(
            user_id=profile.user_id,
            username=profile.username,
            display_name=profile.display_name,
            email=profile.email,
            groups=list(profile.groups),
        )

    return router
