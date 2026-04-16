"""Pydantic response models for execution endpoints.

All models in this module serialize **system-owned data** (Tier 1 in the
Data Manifesto).  They use strict validation and forbid extra fields so
that internal type drift crashes loudly instead of silently coercing
values or dropping unknown fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictResponse(BaseModel):
    """Base model for execution response schemas — Tier 1 trust rules.

    strict=True:   No coercion.  ``"7"`` into an ``int`` field crashes
                   instead of silently becoming ``7``.
    extra="forbid": Unexpected fields crash instead of being silently
                    dropped.

    All execution schemas inherit this.  ``RunEvent.timestamp`` uses
    ``Field(strict=False)`` for the WebSocket reconnect JSON round-trip
    (ISO string → datetime), paired with a ``field_validator`` that
    rejects Unix epoch integers.
    """

    model_config = ConfigDict(strict=True, extra="forbid")


class ValidationCheck(_StrictResponse):
    """Individual check result from dry-run validation."""

    name: str
    passed: bool
    detail: str


class ValidationError(_StrictResponse):
    """Error with per-component attribution."""

    component_id: str | None
    component_type: str | None
    message: str
    suggestion: str | None


class ValidationResult(_StrictResponse):
    """Result of dry-run validation against real engine code."""

    is_valid: bool
    checks: list[ValidationCheck]
    errors: list[ValidationError]


# ── Typed event payload models ──────────────────────────────────────────
#
# Each event_type has a dedicated payload model so that the server-side
# schema catches producer drift between service.py, routes.py, and the
# frontend TypeScript types.


class ProgressData(_StrictResponse):
    """Payload for ``progress`` events (non-terminal, streaming)."""

    rows_processed: int = Field(ge=0)
    rows_failed: int = Field(ge=0)


class ErrorData(_StrictResponse):
    """Payload for ``error`` events (non-terminal, per-row).

    Currently no backend producer emits this event type, but the frontend
    has a handler for it and it represents a legitimate future capability.
    """

    message: str = Field(min_length=1)
    node_id: str | None
    row_id: str | None


class CompletedData(_StrictResponse):
    """Payload for ``completed`` events (terminal)."""

    rows_processed: int = Field(ge=0)
    rows_succeeded: int = Field(ge=0)
    rows_failed: int = Field(ge=0)
    rows_quarantined: int = Field(ge=0)
    landscape_run_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_row_decomposition(self) -> Self:
        """Enforce rows_processed == rows_succeeded + rows_failed + rows_quarantined.

        The orchestrator must produce consistent counts.  A mismatch indicates
        a bug in the orchestrator or a corrupt intermediate value — crash at
        event construction rather than propagating wrong numbers to the
        frontend and audit trail.
        """
        expected = self.rows_succeeded + self.rows_failed + self.rows_quarantined
        if self.rows_processed != expected:
            raise ValueError(
                f"Row count decomposition mismatch: rows_processed={self.rows_processed} "
                f"!= rows_succeeded({self.rows_succeeded}) + rows_failed({self.rows_failed}) "
                f"+ rows_quarantined({self.rows_quarantined}) = {expected}"
            )
        return self


class CancelledData(_StrictResponse):
    """Payload for ``cancelled`` events (terminal)."""

    rows_processed: int = Field(ge=0)
    rows_failed: int = Field(ge=0)


class FailedData(_StrictResponse):
    """Payload for ``failed`` events (terminal)."""

    detail: str = Field(min_length=1)
    node_id: str | None


class RunEvent(_StrictResponse):
    """WebSocket event payload for live progress streaming.

    ``data`` is a typed union keyed by ``event_type``.  The model_validator
    enforces the mapping — constructing a RunEvent with mismatched
    event_type/data types crashes immediately (offensive programming).
    """

    run_id: str
    timestamp: datetime = Field(strict=False)
    # NOTE: Fast pipelines may produce identical timestamps.
    # Event ordering is guaranteed by the asyncio.Queue FIFO, not by timestamp.
    # Frontend must NOT sort by timestamp — use arrival order instead.
    event_type: Literal["progress", "error", "completed", "cancelled", "failed"]
    data: ProgressData | ErrorData | CompletedData | CancelledData | FailedData

    @field_validator("timestamp", mode="before")
    @classmethod
    def _reject_epoch_timestamp(cls, v: object) -> object:
        """Reject Unix epoch integers while allowing ISO strings.

        ``Field(strict=False)`` lets Pydantic parse ISO strings back to
        datetime (needed for the WebSocket reconnect JSON round-trip).
        But lax mode also accepts ``int`` (Unix epoch) — which would
        hide a Tier 1 type error.  This before-validator fires first
        and rejects anything that isn't a ``datetime`` or ``str``.
        """
        if isinstance(v, (datetime, str)):
            return v
        raise ValueError(f"timestamp must be a datetime or ISO string, got {type(v).__name__}")

    _EVENT_TYPE_TO_DATA_TYPE: ClassVar[dict[str, type[_StrictResponse]]] = {
        "progress": ProgressData,
        "error": ErrorData,
        "completed": CompletedData,
        "cancelled": CancelledData,
        "failed": FailedData,
    }

    @model_validator(mode="before")
    @classmethod
    def _resolve_data_from_event_type(cls, values: Any) -> Any:
        """Pre-resolve the data union member during JSON deserialization.

        When deserializing from a dict (JSON round-trip), Pydantic's
        smart-union matching sees identical shapes for ProgressData and
        CancelledData and picks the first match. This pre-validator
        uses event_type to construct the correct model before union
        matching runs.
        """
        if isinstance(values, dict):
            event_type = values.get("event_type")
            data = values.get("data")
            if isinstance(data, dict) and event_type in cls._EVENT_TYPE_TO_DATA_TYPE:
                values = {**values, "data": cls._EVENT_TYPE_TO_DATA_TYPE[event_type](**data)}
        return values

    @model_validator(mode="after")
    def _enforce_data_type(self) -> Self:
        """Crash on event_type / data type mismatch.

        Belt-and-suspenders: the before-validator handles JSON round-trips;
        this after-validator catches programmer error when constructing
        RunEvent directly in Python with mismatched event_type/data.
        """
        expected = self._EVENT_TYPE_TO_DATA_TYPE[self.event_type]
        if not isinstance(self.data, expected):
            raise ValueError(f"event_type={self.event_type!r} requires {expected.__name__}, got {type(self.data).__name__}")
        return self


# Import-time sync guard: the mapping keys MUST match the event_type Literal.
# If a developer adds a new event type to the Literal but forgets the mapping
# (or vice versa), this assertion fires at module load — not at runtime when
# a user hits the mismatch.
_event_type_literal = get_args(RunEvent.model_fields["event_type"].annotation)
_mapping_keys = frozenset(RunEvent._EVENT_TYPE_TO_DATA_TYPE.keys())
_literal_values = frozenset(_event_type_literal)
if _mapping_keys != _literal_values:
    raise AssertionError(f"_EVENT_TYPE_TO_DATA_TYPE keys {_mapping_keys} != event_type Literal values {_literal_values}")
del _event_type_literal, _mapping_keys, _literal_values


class RunStatusResponse(_StrictResponse):
    """REST response for run status queries."""

    run_id: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    started_at: datetime | None
    finished_at: datetime | None
    rows_processed: int = Field(ge=0)
    rows_succeeded: int = Field(ge=0)
    rows_failed: int = Field(ge=0)
    rows_quarantined: int = Field(ge=0)
    error: str | None
    landscape_run_id: str | None


class RunResultsResponse(_StrictResponse):
    """REST response for terminal run results."""

    run_id: str
    status: Literal["completed", "failed", "cancelled"]
    rows_processed: int = Field(ge=0)
    rows_succeeded: int = Field(ge=0)
    rows_failed: int = Field(ge=0)
    rows_quarantined: int = Field(ge=0)
    landscape_run_id: str | None
    error: str | None
