"""REST API routes for session-scoped blob management.

All endpoints require authentication and verify session ownership.
Blob ownership is enforced via the session boundary — a blob must
belong to the authenticated user's session.
"""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from elspeth.web.auth.middleware import get_current_user
from elspeth.web.auth.models import UserIdentity
from elspeth.web.blobs.protocol import (
    ALLOWED_MIME_TYPES,
    BlobActiveRunError,
    BlobNotFoundError,
    BlobQuotaExceededError,
    BlobRecord,
)
from elspeth.web.blobs.schemas import BlobMetadataResponse, CreateInlineBlobRequest
from elspeth.web.blobs.service import BlobServiceImpl
from elspeth.web.blobs.sniff import detect_mime_type


def _blob_response(record: BlobRecord) -> BlobMetadataResponse:
    """Convert a BlobRecord to a response model (excludes storage_path)."""
    return BlobMetadataResponse(
        id=str(record.id),
        session_id=str(record.session_id),
        filename=record.filename,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        content_hash=record.content_hash,
        created_at=record.created_at,
        created_by=record.created_by,
        source_description=record.source_description,
        status=record.status,
    )


async def _verify_session_and_get_blob_service(
    session_id: UUID,
    user: UserIdentity,
    request: Request,
) -> BlobServiceImpl:
    """Verify session ownership and return the blob service.

    Returns 404 (not 403) for ownership failures to preserve the
    anti-IDOR pattern from the session routes.
    """
    session_service = request.app.state.session_service
    try:
        session = await session_service.get_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session not found") from None

    settings = request.app.state.settings
    if session.user_id != user.user_id or session.auth_provider_type != settings.auth_provider:
        raise HTTPException(status_code=404, detail="Session not found")

    blob_service: BlobServiceImpl = request.app.state.blob_service
    return blob_service


async def _get_owned_blob(
    blob_service: BlobServiceImpl,
    session_id: UUID,
    blob_id: UUID,
) -> BlobRecord:
    """Fetch a blob and verify it belongs to the given session.

    Returns 404 for missing blobs or session mismatches.
    """
    try:
        blob = await blob_service.get_blob(blob_id)
    except BlobNotFoundError:
        raise HTTPException(status_code=404, detail="Blob not found") from None

    if blob.session_id != session_id:
        raise HTTPException(status_code=404, detail="Blob not found")

    return blob


def create_blobs_router() -> APIRouter:
    """Create the blob management router."""
    router = APIRouter(
        prefix="/api/sessions/{session_id}/blobs",
        tags=["blobs"],
    )

    @router.post("", status_code=201, response_model=BlobMetadataResponse)
    async def create_blob_upload(
        session_id: UUID,
        request: Request,
        file: UploadFile = File(...),  # noqa: B008
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> BlobMetadataResponse:
        """Create a blob from a multipart file upload."""
        blob_service = await _verify_session_and_get_blob_service(session_id, user, request)
        settings = request.app.state.settings

        # Validate MIME type
        mime_type = file.content_type or "application/octet-stream"
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported content type: {mime_type}. Allowed types: CSV, JSON, JSONL, plain text.",
            )

        # Read content with size enforcement
        original_filename = file.filename or "upload"
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

        # Server-side MIME detection — reject if declared type doesn't
        # match detected content (defense-in-depth, client MIME is untrusted)
        detected = detect_mime_type(content)
        if detected is not None and detected != mime_type and detected not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Detected content type '{detected}' does not match declared '{mime_type}' and is not in the allowed set.",
            )
        # Use detected type if available — record the truth, not the claim
        effective_mime = detected if detected is not None else mime_type
        if effective_mime not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Detected content type '{effective_mime}' is not in the allowed set.",
            )

        try:
            record = await blob_service.create_blob(
                session_id=session_id,
                filename=original_filename,
                content=content,
                mime_type=effective_mime,
                created_by="user",
                source_description="uploaded",
            )
        except BlobQuotaExceededError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from None
        return _blob_response(record)

    @router.post("/inline", status_code=201, response_model=BlobMetadataResponse)
    async def create_blob_inline(
        session_id: UUID,
        body: CreateInlineBlobRequest,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> BlobMetadataResponse:
        """Create a blob from inline text/JSON content."""
        blob_service = await _verify_session_and_get_blob_service(session_id, user, request)

        if body.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported content type: {body.content_type}.",
            )

        settings = request.app.state.settings
        content_bytes = body.content.encode("utf-8")
        if len(content_bytes) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Content exceeds maximum size of {settings.max_upload_bytes} bytes",
            )

        try:
            record = await blob_service.create_blob(
                session_id=session_id,
                filename=body.filename,
                content=content_bytes,
                mime_type=body.content_type,
                created_by="assistant",
                source_description="created inline",
            )
        except BlobQuotaExceededError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from None
        return _blob_response(record)

    @router.get("", response_model=list[BlobMetadataResponse])
    async def list_blobs(
        session_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> list[BlobMetadataResponse]:
        """List blobs for a session."""
        blob_service = await _verify_session_and_get_blob_service(session_id, user, request)
        records = await blob_service.list_blobs(session_id)
        return [_blob_response(r) for r in records]

    @router.get("/{blob_id}", response_model=BlobMetadataResponse)
    async def get_blob_metadata(
        session_id: UUID,
        blob_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> BlobMetadataResponse:
        """Get blob metadata."""
        blob_service = await _verify_session_and_get_blob_service(session_id, user, request)
        blob = await _get_owned_blob(blob_service, session_id, blob_id)
        return _blob_response(blob)

    @router.get("/{blob_id}/content")
    async def download_blob_content(
        session_id: UUID,
        blob_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> Response:
        """Download blob content."""
        blob_service = await _verify_session_and_get_blob_service(session_id, user, request)
        blob = await _get_owned_blob(blob_service, session_id, blob_id)

        try:
            content = await blob_service.read_blob_content(blob_id)
        except BlobNotFoundError:
            raise HTTPException(status_code=404, detail="Blob content not found") from None

        return Response(
            content=content,
            media_type=blob.mime_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(blob.filename, safe='')}"},
        )

    @router.delete("/{blob_id}", status_code=204)
    async def delete_blob(
        session_id: UUID,
        blob_id: UUID,
        request: Request,
        user: UserIdentity = Depends(get_current_user),  # noqa: B008
    ) -> None:
        """Delete a blob and its backing file."""
        blob_service = await _verify_session_and_get_blob_service(session_id, user, request)
        await _get_owned_blob(blob_service, session_id, blob_id)

        try:
            await blob_service.delete_blob(blob_id)
        except BlobNotFoundError:
            raise HTTPException(status_code=404, detail="Blob not found") from None
        except BlobActiveRunError as exc:
            raise HTTPException(
                status_code=409,
                detail=str(exc),
            ) from None

    return router
