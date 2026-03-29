"""Pydantic response models for execution endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class ValidationCheck(BaseModel):
    """Individual check result from dry-run validation."""

    name: str
    passed: bool
    detail: str


class ValidationError(BaseModel):
    """Error with per-component attribution."""

    component_id: str | None
    component_type: str | None
    message: str
    suggestion: str | None


class ValidationResult(BaseModel):
    """Result of dry-run validation against real engine code."""

    is_valid: bool
    checks: list[ValidationCheck]
    errors: list[ValidationError]


class RunEvent(BaseModel):
    """WebSocket event payload for live progress streaming."""

    run_id: str
    timestamp: datetime  # NOTE: Fast pipelines may produce identical timestamps.
    # Event ordering is guaranteed by the asyncio.Queue FIFO, not by timestamp.
    # Frontend must NOT sort by timestamp — use arrival order instead.
    event_type: Literal["progress", "error", "completed", "cancelled", "failed"]
    data: dict[str, Any]


class RunStatusResponse(BaseModel):
    """REST response for run status queries."""

    run_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime | None
    finished_at: datetime | None
    rows_processed: int
    rows_failed: int
    error: str | None
    landscape_run_id: str | None


class RunResultsResponse(BaseModel):
    """REST response for terminal run results."""

    run_id: str
    status: Literal["completed", "failed", "cancelled"]
    rows_processed: int
    rows_failed: int
    landscape_run_id: str | None
    error: str | None
