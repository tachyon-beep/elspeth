"""Pydantic request/response models for all session API endpoints.

Response models in this module serialize **system-owned data** (Tier 1 in
the Data Manifesto).  They inherit from ``_StrictResponse`` so that
coercion and unknown fields crash rather than silently passing through —
the Landscape record and the HTTP response must agree exactly.

Request models use plain ``BaseModel`` semantics: client input is Tier 3
and the boundary-layer coercion rules (documented in ``tier-model-deep-dive``)
apply.  Request-side extra-field rejection is considered per-model rather
than globally; see ``web/blobs/schemas.py`` for the companion pattern.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

import pydantic
from pydantic import BaseModel, ConfigDict, JsonValue

from elspeth.web.sessions.protocol import SessionRunStatus


class _StrictResponse(BaseModel):
    """Base model for session response schemas — Tier 1 trust rules.

    ``strict=True`` rejects silent coercion (``"7"`` into an ``int`` field
    crashes instead of becoming ``7``).  ``extra="forbid"`` rejects
    unknown fields instead of dropping them.  Both are required for the
    audit-trail integrity contract: the HTTP response must not contain
    values the backend never emitted, and must not silently hide values
    the backend did emit.
    """

    model_config = ConfigDict(strict=True, extra="forbid")


class CreateSessionRequest(BaseModel):
    """Request body for POST /api/sessions."""

    title: str = "New session"


class SessionResponse(_StrictResponse):
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
    state_id: UUID | None = None


class ChatMessageResponse(_StrictResponse):
    """Response for a single chat message."""

    id: str
    session_id: str
    role: str
    content: str
    tool_calls: Mapping[str, Any] | None = None
    created_at: datetime
    composition_state_id: str | None = None


class MessageWithStateResponse(_StrictResponse):
    """Response for POST /api/sessions/{id}/messages.

    State is null when the composition version is unchanged; populated
    with the updated CompositionState when composition changes occur.
    """

    message: ChatMessageResponse
    state: CompositionStateResponse | None = None


class ValidationEntryResponse(_StrictResponse):
    """Structured validation entry preserving component attribution.

    Mirrors ``ValidationEntry.to_dict()`` from the composer state module.
    """

    component: str
    message: str
    severity: str


type CompositionObject = dict[str, JsonValue]
type CompositionObjectList = list[CompositionObject]


class CompositionStateResponse(_StrictResponse):
    """Response for composition state endpoints."""

    id: str
    session_id: str
    version: int
    source: CompositionObject | None = None
    nodes: CompositionObjectList | None = None
    edges: CompositionObjectList | None = None
    outputs: CompositionObjectList | None = None
    metadata: CompositionObject | None = None
    is_valid: bool
    validation_errors: list[str] | None = None
    validation_warnings: list[ValidationEntryResponse] | None = None
    validation_suggestions: list[ValidationEntryResponse] | None = None
    derived_from_state_id: str | None = None
    created_at: datetime


class ForkSessionRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/fork."""

    from_message_id: UUID
    new_message_content: str


class ForkSessionResponse(_StrictResponse):
    """Response for POST /api/sessions/{id}/fork."""

    session: SessionResponse
    messages: list[ChatMessageResponse]
    composition_state: CompositionStateResponse | None = None


class RevertStateRequest(BaseModel):
    """Request body for POST /api/sessions/{id}/state/revert."""

    state_id: UUID


class RunResponse(_StrictResponse):
    """Response for GET /api/sessions/{id}/runs."""

    id: str
    session_id: str
    status: SessionRunStatus
    rows_processed: int
    rows_failed: int
    started_at: datetime
    finished_at: datetime | None = None
    composition_version: int


# Forward reference resolution
MessageWithStateResponse.model_rebuild()
ForkSessionResponse.model_rebuild()
