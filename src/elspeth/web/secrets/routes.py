"""REST API routes for secret reference management.

All endpoints require authentication.  SECURITY INVARIANT: no route in
this module may ever return a plaintext secret value in any response body.

Endpoints
---------
GET    /api/secrets              -- list visible secret refs (metadata only)
POST   /api/secrets              -- create/update a user-scoped secret (write-only)
DELETE /api/secrets/{name}       -- delete a user-scoped secret
POST   /api/secrets/{name}/validate -- check whether a secret ref is resolvable
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.secrets.schemas import (
    CreateSecretRequest,
    CreateSecretResponse,
    SecretInventoryResponse,
    ValidateSecretResponse,
)
from elspeth.web.secrets.service import WebSecretService


def create_secrets_router() -> APIRouter:
    """Create the secret management router."""
    router = APIRouter(
        prefix="/api/secrets",
        tags=["secrets"],
    )

    def _get_service(request: Request) -> WebSecretService:
        service: WebSecretService = request.app.state.secret_service
        return service

    @router.get("", response_model=list[SecretInventoryResponse])
    async def list_secrets(
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> list[SecretInventoryResponse]:
        """List all visible secret references (user + server scopes).

        SECURITY: returns metadata only -- no values.
        """
        service = _get_service(request)
        items = service.list_refs(user.user_id)
        return [
            SecretInventoryResponse(
                name=item.name,
                scope=item.scope,
                available=item.available,
                source_kind=item.source_kind,
            )
            for item in items
        ]

    @router.post("", status_code=201, response_model=CreateSecretResponse)
    async def create_secret(
        body: CreateSecretRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> CreateSecretResponse:
        """Create or update a user-scoped secret.

        SECURITY: response is write-only acknowledgement -- NEVER includes
        the value.
        """
        service = _get_service(request)
        await asyncio.to_thread(service.set_user_secret, user.user_id, body.name, body.value)
        return CreateSecretResponse(
            name=body.name,
            scope="user",
            available=True,
        )

    @router.delete("/{name}", status_code=204)
    async def delete_secret(
        name: str,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> None:
        """Delete a user-scoped secret.

        Returns 204 on success, 404 if the secret does not exist for this user.
        """
        service = _get_service(request)
        deleted = await asyncio.to_thread(service.delete_user_secret, user.user_id, name)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Secret {name!r} not found")

    @router.post("/{name}/validate", response_model=ValidateSecretResponse)
    async def validate_secret(
        name: str,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> ValidateSecretResponse:
        """Check whether a named secret reference is resolvable.

        SECURITY: does NOT return the value -- only existence.
        """
        service = _get_service(request)
        available = service.has_ref(user.user_id, name)
        return ValidateSecretResponse(name=name, available=available)

    return router
