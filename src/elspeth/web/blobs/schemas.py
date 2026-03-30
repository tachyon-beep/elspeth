"""Pydantic request/response models for blob API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BlobMetadataResponse(BaseModel):
    """Response for blob metadata endpoints.

    storage_path is never included — it's an internal implementation detail.
    """

    id: str
    session_id: str
    filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    created_at: datetime
    created_by: str
    source_description: str | None = None
    schema_info: dict[str, Any] | None = None
    status: str


class CreateInlineBlobRequest(BaseModel):
    """Request body for creating a blob from inline content (JSON body)."""

    filename: str
    content: str
    content_type: str = "text/plain"
