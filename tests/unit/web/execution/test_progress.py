"""Tests for ProgressBroadcaster — thread-safe async event delivery.

These tests verify the B1 fix: broadcast() uses loop.call_soon_threadsafe()
to safely push events from a background thread into asyncio queues.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import RunEvent


def _make_event(run_id: str = "run-1", event_type: str = "progress") -> RunEvent:
    return RunEvent(
        run_id=run_id,
        timestamp=datetime.now(tz=UTC),
        event_type=event_type,  # type: ignore[arg-type]
        data={"rows_processed": 10, "rows_failed": 0},
    )


class TestProgressBroadcasterSubscription:
    def test_subscribe_returns_queue(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            broadcaster = ProgressBroadcaster(loop)
            queue = broadcaster.subscribe("run-1")
            assert isinstance(queue, asyncio.Queue)
        finally:
            loop.close()

    def test_unsubscribe_removes_queue(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            broadcaster = ProgressBroadcaster(loop)
            queue = broadcaster.subscribe("run-1")
            broadcaster.unsubscribe("run-1", queue)
            # Verify subscriber set is empty after unsubscribe
            assert len(broadcaster._subscribers.get("run-1", set())) == 0
        finally:
            loop.close()

    def test_unsubscribe_unknown_run_is_noop(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            broadcaster = ProgressBroadcaster(loop)
            queue: asyncio.Queue[RunEvent] = asyncio.Queue()
            # Should not raise
            broadcaster.unsubscribe("nonexistent", queue)
        finally:
            loop.close()

    def test_multiple_subscribers_for_same_run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            broadcaster = ProgressBroadcaster(loop)
            q1 = broadcaster.subscribe("run-1")
            q2 = broadcaster.subscribe("run-1")
            assert q1 is not q2
            assert len(broadcaster._subscribers["run-1"]) == 2
        finally:
            loop.close()


class TestProgressBroadcasterThreadSafety:
    """Verify B1 fix: broadcast() uses loop.call_soon_threadsafe()."""

    def test_broadcast_uses_call_soon_threadsafe(self) -> None:
        """broadcast() MUST use loop.call_soon_threadsafe, not direct put_nowait."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        broadcaster = ProgressBroadcaster(mock_loop)
        queue = broadcaster.subscribe("run-1")
        event = _make_event()

        broadcaster.broadcast("run-1", event)

        # Verify call_soon_threadsafe was called with put_nowait
        mock_loop.call_soon_threadsafe.assert_called_once_with(queue.put_nowait, event)

    def test_broadcast_to_multiple_subscribers(self) -> None:
        """Each subscriber queue gets its own call_soon_threadsafe call."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        broadcaster = ProgressBroadcaster(mock_loop)
        broadcaster.subscribe("run-1")
        broadcaster.subscribe("run-1")
        event = _make_event()

        broadcaster.broadcast("run-1", event)

        assert mock_loop.call_soon_threadsafe.call_count == 2

    def test_broadcast_no_subscribers_is_noop(self) -> None:
        """Broadcasting with no subscribers does not raise."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        broadcaster = ProgressBroadcaster(mock_loop)
        event = _make_event()

        # Should not raise
        broadcaster.broadcast("run-1", event)
        mock_loop.call_soon_threadsafe.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_from_background_thread_delivers_events(self) -> None:
        """End-to-end: background thread broadcasts, async consumer receives.

        This is the actual B1 scenario — _run_pipeline() calls broadcast()
        from a ThreadPoolExecutor worker thread, and the WebSocket handler
        awaits queue.get() on the event loop thread.
        """
        loop = asyncio.get_running_loop()
        broadcaster = ProgressBroadcaster(loop)
        queue = broadcaster.subscribe("run-1")
        event = _make_event()

        def background_broadcast() -> None:
            """Simulate _run_pipeline() calling broadcast from worker thread."""
            broadcaster.broadcast("run-1", event)

        # Run broadcast in a real background thread
        thread = threading.Thread(target=background_broadcast)
        thread.start()
        thread.join(timeout=5.0)

        # The event should be in the queue via call_soon_threadsafe
        received = await asyncio.wait_for(queue.get(), timeout=5.0)
        assert received.run_id == "run-1"
        assert received.event_type == "progress"
        assert received.data["rows_processed"] == 10

    @pytest.mark.asyncio
    async def test_multiple_broadcasts_from_thread_arrive_in_order(self) -> None:
        """Events broadcast from a single thread arrive in FIFO order."""
        loop = asyncio.get_running_loop()
        broadcaster = ProgressBroadcaster(loop)
        queue = broadcaster.subscribe("run-1")

        events = [
            RunEvent(
                run_id="run-1",
                timestamp=datetime.now(tz=UTC),
                event_type="progress",
                data={"rows_processed": i, "rows_failed": 0},
            )
            for i in range(5)
        ]

        def background_broadcast() -> None:
            for event in events:
                broadcaster.broadcast("run-1", event)

        thread = threading.Thread(target=background_broadcast)
        thread.start()
        thread.join(timeout=5.0)

        received = []
        for _ in range(5):
            item = await asyncio.wait_for(queue.get(), timeout=5.0)
            received.append(item.data["rows_processed"])

        assert received == [0, 1, 2, 3, 4]

    def test_broadcast_after_unsubscribe_does_not_deliver(self) -> None:
        """After unsubscribe, broadcast does not target the removed queue."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        broadcaster = ProgressBroadcaster(mock_loop)
        queue = broadcaster.subscribe("run-1")
        broadcaster.unsubscribe("run-1", queue)
        event = _make_event()

        broadcaster.broadcast("run-1", event)

        mock_loop.call_soon_threadsafe.assert_not_called()


class TestProgressBroadcasterCleanup:
    def test_cleanup_run_removes_all_subscribers(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            broadcaster = ProgressBroadcaster(loop)
            broadcaster.subscribe("run-1")
            broadcaster.subscribe("run-1")
            broadcaster.cleanup_run("run-1")
            assert "run-1" not in broadcaster._subscribers
        finally:
            loop.close()

    def test_cleanup_unknown_run_is_noop(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            broadcaster = ProgressBroadcaster(loop)
            broadcaster.cleanup_run("nonexistent")  # Should not raise
        finally:
            loop.close()
