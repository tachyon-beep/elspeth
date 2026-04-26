"""Session-scoped composer progress snapshots.

The progress surface is a UI status channel, not a reasoning transcript.
Snapshots summarize visible composer lifecycle boundaries and tool categories;
they must never carry raw tool arguments, tool results, secrets, or provider
chain-of-thought.
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

COMPOSER_PROGRESS_MAX_EVIDENCE = 4
_MAX_PROGRESS_TEXT_CHARS = 180

type ComposerProgressPhase = Literal[
    "idle",
    "starting",
    "calling_model",
    "using_tools",
    "validating",
    "saving",
    "complete",
    "failed",
]
type ComposerProgressSink = Callable[["ComposerProgressEvent"], Awaitable[None]]


class _StrictProgressModel(BaseModel):
    """Strict model for system-owned progress snapshots."""

    model_config = ConfigDict(strict=True, extra="forbid")


class ComposerProgressEvent(_StrictProgressModel):
    """Provider-safe progress event emitted by the composer path."""

    phase: ComposerProgressPhase
    headline: str
    evidence: tuple[str, ...] = ()
    likely_next: str | None = None

    @field_validator("headline")
    @classmethod
    def _validate_headline(cls, value: str) -> str:
        return _clean_required_text(value, field_name="headline")

    @field_validator("likely_next")
    @classmethod
    def _validate_likely_next(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_required_text(value, field_name="likely_next")

    @field_validator("evidence")
    @classmethod
    def _bound_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bounded: list[str] = []
        for item in value:
            cleaned = _clean_required_text(item, field_name="evidence")
            bounded.append(cleaned)
            if len(bounded) == COMPOSER_PROGRESS_MAX_EVIDENCE:
                break
        return tuple(bounded)


class ComposerProgressSnapshot(ComposerProgressEvent):
    """Latest composer progress snapshot for one session."""

    session_id: str
    request_id: str | None
    updated_at: datetime


class ComposerProgressRegistry:
    """In-memory latest-progress registry keyed by session id.

    The registry intentionally stores one bounded snapshot per session, not an
    append-only log. The immutable session/chat tables remain the source of
    truth for persisted conversation history.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, ComposerProgressSnapshot] = {}
        self._lock = threading.Lock()

    async def publish(
        self,
        *,
        session_id: str,
        request_id: str | None,
        event: ComposerProgressEvent,
    ) -> ComposerProgressSnapshot:
        """Store and return the latest progress snapshot for a session."""
        with self._lock:
            updated_at = self._next_timestamp(session_id)
            snapshot = ComposerProgressSnapshot(
                session_id=session_id,
                request_id=request_id,
                phase=event.phase,
                headline=event.headline,
                evidence=event.evidence,
                likely_next=event.likely_next,
                updated_at=updated_at,
            )
            self._snapshots[session_id] = snapshot
            return snapshot

    async def get_latest(self, session_id: str) -> ComposerProgressSnapshot:
        """Return latest progress or a neutral idle snapshot."""
        with self._lock:
            if session_id in self._snapshots:
                return self._snapshots[session_id]
            return _idle_snapshot(session_id)

    async def clear(self, session_id: str) -> None:
        """Remove a session snapshot."""
        with self._lock:
            if session_id in self._snapshots:
                self._snapshots.pop(session_id)

    def _next_timestamp(self, session_id: str) -> datetime:
        now = datetime.now(UTC)
        if session_id in self._snapshots:
            previous = self._snapshots[session_id].updated_at
            if now <= previous:
                return previous + timedelta(microseconds=1)
        return now


def _idle_snapshot(session_id: str) -> ComposerProgressSnapshot:
    return ComposerProgressSnapshot(
        session_id=session_id,
        request_id=None,
        phase="idle",
        headline="No active composer work.",
        evidence=(),
        likely_next=None,
        updated_at=datetime.now(UTC),
    )


def _clean_required_text(value: str, *, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"composer progress {field_name} must contain visible text")
    if len(cleaned) > _MAX_PROGRESS_TEXT_CHARS:
        return cleaned[: _MAX_PROGRESS_TEXT_CHARS - 1].rstrip() + "."
    return cleaned
