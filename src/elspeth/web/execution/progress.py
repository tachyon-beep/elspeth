"""ProgressBroadcaster — thread-safe bridge from sync pipeline to async WebSocket.

B1 Fix: All cross-thread pushes use loop.call_soon_threadsafe() to schedule
queue.put_nowait() on the event loop thread. Direct queue.put_nowait() from
a background thread would corrupt the event loop's internal state.

Construction timing: Created inside the FastAPI lifespan async context manager,
NOT in the synchronous create_app() factory. The loop reference is captured via
asyncio.get_running_loop() inside the lifespan, which guarantees a running event
loop exists and is Python 3.12+ compatible (asyncio.get_event_loop() emits a
deprecation warning when no running loop exists). The ExecutionServiceImpl is
also constructed inside the lifespan (after ProgressBroadcaster), not in
create_app(), because it depends on the broadcaster instance.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading

import structlog

from elspeth.web.execution.schemas import RunEvent

slog = structlog.get_logger()

# Backpressure: maximum events buffered per WebSocket subscriber.
# A stalled client that cannot drain its queue will have oldest events
# dropped rather than accumulating unboundedly toward OOM.
_SUBSCRIBER_QUEUE_MAXSIZE = 1000


class ProgressBroadcaster:
    """In-process event broadcaster for pipeline progress.

    Bridges the synchronous background thread (where the Orchestrator runs)
    to the async WebSocket handlers (where clients receive events).

    Thread safety contract:
    - subscribe() and unsubscribe() may be called from the asyncio event loop thread.
    - broadcast() is called from the background pipeline thread.
    - broadcast() uses self._loop.call_soon_threadsafe() for every queue.put_nowait().
    - All mutations to and iterations over self._subscribers are protected by
      self._lock (a threading.Lock). This ensures correctness regardless of
      GIL presence (safe under PEP 703 / free-threaded Python).
    """

    _TERMINAL_EVENT_TYPES = frozenset({"completed", "failed", "cancelled"})

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent]]] = {}
        self._terminalized: set[str] = set()

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent]:
        """Create and register a subscriber queue for a run.

        Called from the WebSocket handler when a client connects.
        Returns the queue that the handler awaits on.
        """
        queue: asyncio.Queue[RunEvent] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
        with self._lock:
            self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[RunEvent]) -> None:
        """Remove a subscriber queue. Called on WebSocket disconnect.

        Always called from a finally block to ensure cleanup.
        """
        with self._lock:
            if run_id in self._subscribers:
                self._subscribers[run_id].discard(queue)

    def broadcast(self, run_id: str, event: RunEvent) -> None:
        """Thread-safe broadcast — callable from background threads.

        B1 fix: Uses self._loop.call_soon_threadsafe() to schedule
        queue.put_nowait() on the event loop thread. This is the standard
        Python pattern for pushing data from a synchronous thread into
        an asyncio context.

        B3 fix: Copies the subscriber set under the lock before iterating,
        so concurrent subscribe/unsubscribe cannot cause RuntimeError.
        """
        with self._lock:
            if event.event_type in self._TERMINAL_EVENT_TYPES:
                if run_id in self._terminalized:
                    slog.error(
                        "duplicate_terminal_broadcast_suppressed",
                        run_id=run_id,
                        event_type=event.event_type,
                    )
                    return
                self._terminalized.add(run_id)
            subs = set(self._subscribers.get(run_id, ()))
        for queue in subs:
            self._loop.call_soon_threadsafe(self._safe_put, queue, event, run_id)

    @staticmethod
    def _safe_put(queue: asyncio.Queue[RunEvent], event: RunEvent, run_id: str) -> None:
        """Put an event on the queue, dropping oldest on backpressure.

        Called via call_soon_threadsafe — runs on the event loop thread.

        Terminal events (completed, failed, cancelled) must never be dropped —
        a lost terminal event leaves WebSocket clients hanging forever. For
        terminal events, drain the entire queue if necessary to make room.
        """
        is_terminal = event.event_type in ("completed", "failed", "cancelled")

        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            if is_terminal:
                # Terminal events MUST be delivered. Drain queue to make room.
                drained = 0
                while not queue.empty():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                        drained += 1
                if drained > 0:
                    slog.info("subscriber_queue_drained_for_terminal", run_id=run_id, drained=drained)
                queue.put_nowait(event)  # Queue is empty — this cannot fail
            else:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()  # Drop oldest
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    slog.warning("subscriber_queue_drop", run_id=run_id)

    def cleanup_run(self, run_id: str) -> None:
        """Remove subscriber mapping for a completed/failed/cancelled run.

        Called from _run_pipeline's finally block after the terminal event
        has been scheduled via broadcast(). Does NOT destroy existing queues —
        events already queued will still be drained by connected WS handlers.
        Only prevents new subscribers from being added for this run_id.
        """
        with self._lock:
            self._subscribers.pop(run_id, None)
            self._terminalized.discard(run_id)
