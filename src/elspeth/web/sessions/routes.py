"""Session API routes -- /api/sessions/* with IDOR protection.

All endpoints require authentication via Depends(get_current_user).
Session-scoped endpoints verify ownership before any business logic.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from elspeth.contracts.freeze import deep_thaw
from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.sessions.protocol import (
    CompositionStateRecord,
    SessionRecord,
    SessionServiceProtocol,
)
from elspeth.web.sessions.schemas import (
    ChatMessageResponse,
    CompositionStateResponse,
    CreateSessionRequest,
    MessageWithStateResponse,
    RevertStateRequest,
    SendMessageRequest,
    SessionResponse,
    UploadResponse,
)


def _session_response(session: SessionRecord) -> SessionResponse:
    """Convert a SessionRecord to a SessionResponse."""
    return SessionResponse(
        id=str(session.id),
        user_id=session.user_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _state_response(state: CompositionStateRecord) -> CompositionStateResponse:
    """Convert a CompositionStateRecord to a CompositionStateResponse.

    Unfreezes container fields (MappingProxyType, tuple) so Pydantic
    can serialize them to JSON.
    """
    return CompositionStateResponse(
        id=str(state.id),
        session_id=str(state.session_id),
        version=state.version,
        source=deep_thaw(state.source),
        nodes=deep_thaw(state.nodes),
        edges=deep_thaw(state.edges),
        outputs=deep_thaw(state.outputs),
        metadata=deep_thaw(state.metadata_),
        is_valid=state.is_valid,
        validation_errors=deep_thaw(state.validation_errors),
        derived_from_state_id=str(state.derived_from_state_id) if state.derived_from_state_id is not None else None,
        created_at=state.created_at,
    )


async def _verify_session_ownership(
    session_id: UUID,
    user: UserIdentity,
    request: Request,
) -> SessionRecord:
    """Verify the session exists and belongs to the current user.

    Returns 404 (not 403) to avoid leaking session existence (IDOR, W5).
    """
    service: SessionServiceProtocol = request.app.state.session_service
    try:
        session = await service.get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    settings = request.app.state.settings
    if session.user_id != user.user_id or session.auth_provider_type != settings.auth_provider:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


def create_session_router() -> APIRouter:
    """Create the session router with /api/sessions prefix."""
    router = APIRouter(prefix="/api/sessions", tags=["sessions"])

    @router.post("", status_code=201, response_model=SessionResponse)
    async def create_session(
        body: CreateSessionRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> SessionResponse:
        """Create a new session for the authenticated user."""
        service = request.app.state.session_service
        settings = request.app.state.settings
        session = await service.create_session(
            user.user_id,
            body.title,
            settings.auth_provider,
        )
        return _session_response(session)

    @router.get("", response_model=list[SessionResponse])
    async def list_sessions(
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[SessionResponse]:
        """List sessions for the authenticated user."""
        service = request.app.state.session_service
        settings = request.app.state.settings
        sessions = await service.list_sessions(
            user.user_id,
            settings.auth_provider,
            limit=limit,
            offset=offset,
        )
        return [_session_response(s) for s in sessions]

    @router.get("/{session_id}", response_model=SessionResponse)
    async def get_session(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> SessionResponse:
        """Get a single session. IDOR-protected."""
        session = await _verify_session_ownership(session_id, user, request)
        return _session_response(session)

    @router.delete("/{session_id}", status_code=204)
    async def delete_session(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> None:
        """Archive (delete) a session and all associated data."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        await service.archive_session(session.id)

    @router.post(
        "/{session_id}/messages",
        response_model=MessageWithStateResponse,
    )
    async def send_message(
        session_id: UUID,
        body: SendMessageRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> MessageWithStateResponse:
        """Send a user message. In Phase 2, only persists the message."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        msg = await service.add_message(session.id, "user", body.content)
        return MessageWithStateResponse(
            message=ChatMessageResponse(
                id=str(msg.id),
                session_id=str(msg.session_id),
                role=msg.role,
                content=msg.content,
                tool_calls=msg.tool_calls,
                created_at=msg.created_at,
            ),
            state=None,
        )

    @router.get(
        "/{session_id}/messages",
        response_model=list[ChatMessageResponse],
    )
    async def get_messages(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ) -> list[ChatMessageResponse]:
        """Get conversation history for a session."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        messages = await service.get_messages(session.id, limit=limit, offset=offset)
        return [
            ChatMessageResponse(
                id=str(m.id),
                session_id=str(m.session_id),
                role=m.role,
                content=m.content,
                tool_calls=m.tool_calls,
                created_at=m.created_at,
            )
            for m in messages
        ]

    @router.get("/{session_id}/state")
    async def get_current_state(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> CompositionStateResponse | None:
        """Get the current (highest-version) composition state."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        state = await service.get_current_state(session.id)
        if state is None:
            return None
        return _state_response(state)

    @router.get(
        "/{session_id}/state/versions",
        response_model=list[CompositionStateResponse],
    )
    async def get_state_versions(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> list[CompositionStateResponse]:
        """Get composition state versions for a session."""
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        versions = await service.get_state_versions(session.id, limit=limit, offset=offset)
        return [_state_response(v) for v in versions]

    @router.post(
        "/{session_id}/state/revert",
        response_model=CompositionStateResponse,
    )
    async def revert_state(
        session_id: UUID,
        body: RevertStateRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> CompositionStateResponse:
        """Revert the pipeline to a prior composition state version (R1).

        Creates a new version that is a copy of the specified prior state.
        Injects a system message recording the revert.
        """
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service

        try:
            new_state = await service.set_active_state(
                session.id,
                body.state_id,
            )
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail="State not found",
            ) from None

        # Look up the original version number for the system message
        original_state = await service.get_state(body.state_id)
        await service.add_message(
            session.id,
            role="system",
            content=f"Pipeline reverted to version {original_state.version}.",
        )

        return _state_response(new_state)

    @router.get("/{session_id}/state/yaml")
    async def get_state_yaml(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> dict[str, str]:
        """Get YAML representation of the current composition state (M1).

        Stub endpoint -- returns 501 until Sub-4 implements generate_yaml().
        When Sub-4 lands, replace the 501 with:
            state = await service.get_current_state(session.id)
            yaml_str = generate_yaml(CompositionState.from_dict(state))
            return {"yaml": yaml_str}
        """
        session = await _verify_session_ownership(session_id, user, request)
        service = request.app.state.session_service
        state = await service.get_current_state(session.id)
        if state is None:
            raise HTTPException(status_code=404, detail="No composition state exists")
        # TODO(sub-4): Replace stub with generate_yaml() call
        raise HTTPException(
            status_code=501,
            detail="YAML generation not yet implemented (see Sub-4)",
        )

    @router.post("/{session_id}/upload", response_model=UploadResponse)
    async def upload_file(
        session_id: UUID,
        request: Request,
        file: UploadFile = File(...),  # noqa: B008
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> UploadResponse:
        """Upload a source file to the user's scratch directory.

        Path traversal protection (B5): both user_id and filename are
        sanitized via Path().name to strip directory components.
        """
        await _verify_session_ownership(session_id, user, request)
        settings = request.app.state.settings

        # B5: Sanitize user_id -- strip all directory components
        sanitized_user_id = Path(user.user_id).name
        if not sanitized_user_id or sanitized_user_id in (".", ".."):
            raise HTTPException(
                status_code=400,
                detail="Invalid user ID for file upload",
            )

        # B5: Sanitize filename
        original_filename = file.filename or "upload"
        sanitized_filename = Path(original_filename).name
        if not sanitized_filename or sanitized_filename in (".", ".."):
            raise HTTPException(
                status_code=400,
                detail="Invalid filename",
            )

        # Read in chunks, abort if size exceeds limit
        chunks: list[bytes] = []
        total_size = 0
        while chunk := await file.read(8192):
            total_size += len(chunk)
            if total_size > settings.max_upload_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum size of {settings.max_upload_bytes} bytes",
                )
            chunks.append(chunk)
        content = b"".join(chunks)

        # Create upload directory and save
        upload_dir = Path(settings.data_dir) / "uploads" / sanitized_user_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / sanitized_filename
        await asyncio.to_thread(file_path.write_bytes, content)

        # Return relative path (not absolute) for portability
        relative_path = file_path.relative_to(settings.data_dir)

        return UploadResponse(
            path=str(relative_path),
            filename=original_filename,
            size_bytes=len(content),
        )

    return router
