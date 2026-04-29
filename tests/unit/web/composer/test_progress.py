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
    convergence_progress_event,
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

    def test_rejects_unknown_reason(self) -> None:
        """Reason codes are a closed Literal so the frontend can branch safely."""
        with pytest.raises(ValidationError):
            ComposerProgressEvent(
                phase="failed",
                headline="The composer could not finish this request.",
                evidence=("Some boundary.",),
                reason=cast(Any, "totally_made_up_reason"),
            )

    def test_failed_phase_requires_reason(self) -> None:
        """phase='failed' MUST carry a stable reason code so UX text drift is impossible."""
        with pytest.raises(ValidationError) as exc_info:
            ComposerProgressEvent(
                phase="failed",
                headline="The composer could not finish this request.",
                evidence=("The bounded composer loop stopped before a final answer.",),
            )
        assert "reason" in str(exc_info.value).lower()

    def test_non_failed_phases_allow_omitted_reason(self) -> None:
        """Non-failed events may omit the reason — they default to None."""
        event = ComposerProgressEvent(
            phase="using_tools",
            headline="The model is updating the pipeline graph.",
            evidence=("A pipeline-editing tool was requested.",),
        )
        assert event.reason is None

    def test_accepts_each_documented_reason_code(self) -> None:
        """Every documented reason value must round-trip through the model."""
        valid_reasons = (
            "convergence_composition_budget",
            "convergence_discovery_budget",
            "convergence_wall_clock_timeout",
            "provider_auth_failed",
            "provider_unavailable",
            "plugin_crash",
            "runtime_preflight_failed",
            "service_setup_failed",
            "composer_idle",
            "composer_complete",
        )
        for reason in valid_reasons:
            event = ComposerProgressEvent(
                phase="failed",
                headline="A safely bounded failure.",
                evidence=("Boundary text.",),
                reason=cast(Any, reason),
            )
            assert event.reason == reason


class TestConvergenceProgressEvent:
    """The discriminator that fixes elspeth-5030f7373d.

    The original symptom was that wall-clock timeout, mutation-turn budget,
    and discovery-turn budget all collapsed into one generic ``phase: failed``
    event. These tests pin the three distinct events the helper must emit,
    so any future refactor that re-collapses them fails immediately.
    """

    def test_wall_clock_timeout_emits_distinct_event(self) -> None:
        event = convergence_progress_event(budget_exhausted="timeout")
        assert event.phase == "failed"
        assert event.reason == "convergence_wall_clock_timeout"
        assert "timed out" in event.headline.lower()
        assert event.likely_next is not None
        assert "wall-clock" in event.likely_next.lower()

    def test_composition_budget_emits_distinct_event(self) -> None:
        event = convergence_progress_event(budget_exhausted="composition")
        assert event.phase == "failed"
        assert event.reason == "convergence_composition_budget"
        assert "mutation turn budget" in event.headline.lower()
        assert event.likely_next is not None
        assert "smaller turns" in event.likely_next.lower()

    def test_discovery_budget_emits_distinct_event(self) -> None:
        event = convergence_progress_event(budget_exhausted="discovery")
        assert event.phase == "failed"
        assert event.reason == "convergence_discovery_budget"
        assert "discovery turn budget" in event.headline.lower()
        assert event.likely_next is not None
        assert "narrow" in event.likely_next.lower()

    def test_three_sub_causes_produce_three_distinct_reason_codes(self) -> None:
        """Regression guard: the three causes must NOT collapse to one code."""
        codes = {
            convergence_progress_event(budget_exhausted="timeout").reason,
            convergence_progress_event(budget_exhausted="composition").reason,
            convergence_progress_event(budget_exhausted="discovery").reason,
        }
        assert len(codes) == 3, (
            "Three convergence sub-causes collapsed back into fewer reason codes — "
            "elspeth-5030f7373d regression. Codes seen: " + repr(codes)
        )


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
        assert snapshot.reason == "composer_idle"

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
                reason="service_setup_failed",
            ),
        )

        await registry.clear("session-1")
        snapshot = await registry.get_latest("session-1")

        assert snapshot.phase == "idle"
        assert snapshot.updated_at <= datetime.now(UTC)
