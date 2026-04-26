"""Tests for session-scoped composer progress snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest
from pydantic import ValidationError

from elspeth.web.composer.progress import (
    COMPOSER_PROGRESS_MAX_EVIDENCE,
    ComposerProgressEvent,
    ComposerProgressRegistry,
)


class TestComposerProgressEvent:
    def test_rejects_unknown_phase(self) -> None:
        """Progress phases are a closed, typed surface for frontend handling."""
        with pytest.raises(ValidationError):
            ComposerProgressEvent(
                phase=cast(Any, "thinking"),
                headline="Thinking about hidden details",
                evidence=(),
            )

    def test_evidence_is_bounded(self) -> None:
        event = ComposerProgressEvent(
            phase="using_tools",
            headline="Checking available tools",
            evidence=tuple(f"visible boundary {index}" for index in range(COMPOSER_PROGRESS_MAX_EVIDENCE + 3)),
        )

        assert len(event.evidence) == COMPOSER_PROGRESS_MAX_EVIDENCE
        assert event.evidence[-1] == f"visible boundary {COMPOSER_PROGRESS_MAX_EVIDENCE - 1}"


class TestComposerProgressRegistry:
    @pytest.mark.asyncio
    async def test_returns_idle_snapshot_when_session_has_no_progress(self) -> None:
        registry = ComposerProgressRegistry()

        snapshot = await registry.get_latest("session-1")

        assert snapshot.session_id == "session-1"
        assert snapshot.request_id is None
        assert snapshot.phase == "idle"
        assert snapshot.headline == "No active composer work."
        assert snapshot.evidence == ()

    @pytest.mark.asyncio
    async def test_keeps_only_latest_snapshot_per_session(self) -> None:
        registry = ComposerProgressRegistry()

        first = await registry.publish(
            session_id="session-1",
            request_id="message-1",
            event=ComposerProgressEvent(
                phase="starting",
                headline="I'm reading your request and current pipeline.",
                evidence=("The request was accepted.",),
            ),
        )
        second = await registry.publish(
            session_id="session-1",
            request_id="message-1",
            event=ComposerProgressEvent(
                phase="calling_model",
                headline="I'm asking the model to choose the next pipeline change.",
                evidence=("The composer prompt was built.",),
            ),
        )

        latest = await registry.get_latest("session-1")

        assert first.updated_at < second.updated_at
        assert latest == second
        assert latest.phase == "calling_model"

    @pytest.mark.asyncio
    async def test_clear_removes_session_snapshot(self) -> None:
        registry = ComposerProgressRegistry()
        await registry.publish(
            session_id="session-1",
            request_id="message-1",
            event=ComposerProgressEvent(
                phase="failed",
                headline="The composer could not finish this request.",
                evidence=("The safe failure path was reached.",),
            ),
        )

        await registry.clear("session-1")
        snapshot = await registry.get_latest("session-1")

        assert snapshot.phase == "idle"
        assert snapshot.updated_at <= datetime.now(UTC)
