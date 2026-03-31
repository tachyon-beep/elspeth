"""Pydantic request/response models for all session API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import pydantic
from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/sessions."""

    title: str = "New session"


class SessionResponse(BaseModel):
    """Response for session CRUD operations."""

    id: str
    user_id: str
    title: str
    created_at: datetime
    updated_at: datetime
    forked_from_session_id: str | None = None
    forked_from_message_id: str | None = None


class SendMessageRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/messages."""

    content: str = pydantic.Field(min_length=1)
    state_id: str | None = None


class ChatMessageResponse(BaseModel):
    """Response for a single chat message."""

    id: str
    session_id: str
    role: str
    content: str
    tool_calls: Any | None = None
    created_at: datetime
    composition_state_id: str | None = None


class MessageWithStateResponse(BaseModel):
    """Response for POST /api/sessions/{id}/messages.

    In Phase 2, state is always null. In Phase 4, it will contain
    the updated CompositionState after the ComposerService processes
    the message.
    """

    message: ChatMessageResponse
    state: CompositionStateResponse | None = None


class CompositionStateResponse(BaseModel):
    """Response for composition state endpoints."""

    id: str
    session_id: str
    version: int
    source: Any | None = None
    nodes: list[Any] | None = None
    edges: list[Any] | None = None
    outputs: list[Any] | None = None
    metadata: Any | None = None
    is_valid: bool
    validation_errors: list[str] | None = None
    derived_from_state_id: str | None = None
    created_at: datetime


class ForkSessionRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/fork."""

    from_message_id: UUID
    new_message_content: str


class ForkSessionResponse(BaseModel):
    """Response for POST /api/sessions/{id}/fork."""

    session: SessionResponse
    messages: list[ChatMessageResponse]
    composition_state: CompositionStateResponse | None = None


class RevertStateRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/state/revert."""

    state_id: UUID


class RunResponse(BaseModel):
    """Response for GET /api/sessions/{id}/runs."""

    id: str
    session_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    rows_processed: int
    rows_failed: int
    started_at: datetime
    finished_at: datetime | None = None
    composition_version: int


class UploadResponse(BaseModel):
    """Response for POST /api/sessions/{id}/upload."""

    path: str
    filename: str
    size_bytes: int


# Forward reference resolution
MessageWithStateResponse.model_rebuild()
ForkSessionResponse.model_rebuild()
