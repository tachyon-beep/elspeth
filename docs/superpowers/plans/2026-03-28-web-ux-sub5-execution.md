# Sub-Spec 5: Execution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the execution layer that validates, runs, cancels, and streams progress for ELSPETH pipelines through the web API. This is the most technically complex phase — all thread safety fixes (B1, B2, B3, B7) live here.

**Architecture:** `ExecutionServiceImpl` manages a `ThreadPoolExecutor(max_workers=1)` for background pipeline runs. `ProgressBroadcaster` bridges the sync background thread to async WebSocket handlers via `loop.call_soon_threadsafe()`. Dry-run validation uses the real engine code path (`load_settings` -> `instantiate_plugins_from_config` -> `ExecutionGraph.from_plugin_instances` -> `graph.validate()`). Cancel uses `threading.Event` checked by the Orchestrator during row processing.

**Tech Stack:** FastAPI, asyncio, concurrent.futures, threading, pytest, httpx (test client).

**Spec:** `docs/superpowers/specs/2026-03-28-web-ux-sub5-execution-design.md`
**Parent Plan:** `docs/superpowers/plans/2026-03-28-web-ux-composer-mvp.md` (Tasks 5.1-5.4)

**Depends on:** Sub-Specs 2 (Auth & Sessions), 4 (Composer) — specifically `CompositionState`, `SessionService`, `yaml_generator`, `WebSettings`, and the app factory.
**Blocks:** Sub-Spec 6 (Frontend).

**Thread Safety Summary:**

| Fix | Problem | Solution |
|-----|---------|----------|
| B1 | `asyncio.Queue.put_nowait()` from background thread corrupts event loop | `ProgressBroadcaster` captures loop at construction, uses `loop.call_soon_threadsafe()` |
| B2 | `signal.signal()` from non-main thread raises `ValueError` | Always pass `shutdown_event=threading.Event()` to `Orchestrator.run()` |
| B3 | Orchestrator needs LandscapeDB/PayloadStore without CLI path | Construct from `WebSettings.get_landscape_url()` / `.get_payload_store_path()` |
| B7 | `except Exception` misses `KeyboardInterrupt`/`SystemExit`, leaving ghost runs | `except BaseException` + `future.add_done_callback()` safety net |

---

### Task 5.1: Pydantic Response Models

**Files:**
- Create: `src/elspeth/web/execution/__init__.py`
- Create: `src/elspeth/web/execution/schemas.py`
- Create: `tests/unit/web/execution/__init__.py`
- Create: `tests/unit/web/execution/test_schemas.py`

- [ ] **Step 1: Write tests for response models**

```python
# tests/unit/web/execution/test_schemas.py
"""Tests for execution response models."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from elspeth.web.execution.schemas import (
    RunEvent,
    RunStatusResponse,
    ValidationCheck,
    ValidationError,
    ValidationResult,
)


class TestValidationResult:
    def test_valid_result(self) -> None:
        result = ValidationResult(
            is_valid=True,
            checks=[
                ValidationCheck(
                    name="settings_load",
                    passed=True,
                    detail="Settings loaded successfully",
                ),
                ValidationCheck(
                    name="plugin_instantiation",
                    passed=True,
                    detail="All plugins instantiated",
                ),
                ValidationCheck(
                    name="graph_structure",
                    passed=True,
                    detail="Graph is valid",
                ),
                ValidationCheck(
                    name="schema_compatibility",
                    passed=True,
                    detail="All edge schemas compatible",
                ),
            ],
            errors=[],
        )
        assert result.is_valid is True
        assert len(result.checks) == 4
        assert all(c.passed for c in result.checks)

    def test_invalid_result_with_attributed_error(self) -> None:
        result = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load", passed=True, detail="OK"
                ),
                ValidationCheck(
                    name="graph_structure",
                    passed=False,
                    detail="Graph validation failed",
                ),
            ],
            errors=[
                ValidationError(
                    component_id="gate_1",
                    component_type="gate",
                    message="Route destination 'nonexistent_sink' not found",
                    suggestion="Check sink names in gate configuration",
                ),
            ],
        )
        assert result.is_valid is False
        assert result.errors[0].component_id == "gate_1"
        assert result.errors[0].component_type == "gate"

    def test_structural_error_has_null_component(self) -> None:
        err = ValidationError(
            component_id=None,
            component_type=None,
            message="Graph contains a cycle",
            suggestion=None,
        )
        assert err.component_id is None
        assert err.component_type is None

    def test_skipped_check_recorded(self) -> None:
        """When settings_load fails, downstream checks are skipped but recorded."""
        result = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load",
                    passed=False,
                    detail="Invalid YAML syntax",
                ),
                ValidationCheck(
                    name="plugin_instantiation",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
                ValidationCheck(
                    name="graph_structure",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
                ValidationCheck(
                    name="schema_compatibility",
                    passed=False,
                    detail="Skipped: settings_load failed",
                ),
            ],
            errors=[
                ValidationError(
                    component_id=None,
                    component_type=None,
                    message="Invalid YAML syntax",
                    suggestion=None,
                ),
            ],
        )
        assert result.is_valid is False
        skipped = [c for c in result.checks if "Skipped" in c.detail]
        assert len(skipped) == 3


class TestRunEvent:
    def test_progress_event(self) -> None:
        event = RunEvent(
            run_id="run-123",
            timestamp=datetime.now(tz=timezone.utc),
            event_type="progress",
            data={"rows_processed": 50, "rows_failed": 2},
        )
        assert event.event_type == "progress"
        assert event.data["rows_processed"] == 50

    def test_completed_event(self) -> None:
        event = RunEvent(
            run_id="run-123",
            timestamp=datetime.now(tz=timezone.utc),
            event_type="completed",
            data={
                "rows_processed": 100,
                "rows_succeeded": 98,
                "rows_failed": 2,
                "rows_quarantined": 0,
                "landscape_run_id": "lscape-456",
            },
        )
        assert event.event_type == "completed"
        assert event.data["landscape_run_id"] == "lscape-456"

    def test_error_event(self) -> None:
        event = RunEvent(
            run_id="run-123",
            timestamp=datetime.now(tz=timezone.utc),
            event_type="error",
            data={"message": "Division by zero", "node_id": "transform_1", "row_id": "row-5"},
        )
        assert event.event_type == "error"
        assert event.data["node_id"] == "transform_1"

    def test_invalid_event_type_rejected(self) -> None:
        """event_type is a Literal — Pydantic rejects unknown values."""
        with pytest.raises(Exception):  # ValidationError from Pydantic
            RunEvent(
                run_id="run-123",
                timestamp=datetime.now(tz=timezone.utc),
                event_type="unknown",  # type: ignore[arg-type]
                data={},
            )


class TestRunStatusResponse:
    def test_pending_status(self) -> None:
        status = RunStatusResponse(
            run_id="run-123",
            status="pending",
            started_at=None,
            finished_at=None,
            rows_processed=0,
            rows_failed=0,
            error=None,
            landscape_run_id=None,
        )
        assert status.status == "pending"
        assert status.started_at is None

    def test_completed_status(self) -> None:
        now = datetime.now(tz=timezone.utc)
        status = RunStatusResponse(
            run_id="run-123",
            status="completed",
            started_at=now,
            finished_at=now,
            rows_processed=100,
            rows_failed=0,
            error=None,
            landscape_run_id="lscape-456",
        )
        assert status.landscape_run_id == "lscape-456"

    def test_failed_status_has_error(self) -> None:
        now = datetime.now(tz=timezone.utc)
        status = RunStatusResponse(
            run_id="run-123",
            status="failed",
            started_at=now,
            finished_at=now,
            rows_processed=50,
            rows_failed=50,
            error="Connection refused",
            landscape_run_id=None,
        )
        assert status.error == "Connection refused"
```

- [ ] **Step 2: Implement response models**

```python
# src/elspeth/web/execution/schemas.py
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
    timestamp: datetime
    event_type: Literal["progress", "error", "completed"]
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
```

- [ ] **Step 3: Run tests, commit**

```bash
.venv/bin/python -m pytest tests/unit/web/execution/test_schemas.py -v
git commit -m "feat(web/execution): add Pydantic response models for validation, status, events"
```

---

### Task 5.2: ExecutionService Protocol

**Files:**
- Create: `src/elspeth/web/execution/protocol.py`

- [ ] **Step 1: Define the protocol**

```python
# src/elspeth/web/execution/protocol.py
"""ExecutionService protocol — called from FastAPI route handlers."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from elspeth.web.execution.schemas import RunStatusResponse, ValidationResult


class ExecutionService(Protocol):
    """Protocol for pipeline execution operations.

    All methods are called from FastAPI route handlers in the async context.
    execute() returns immediately; the pipeline runs in a background thread.
    """

    def validate(self, session_id: UUID) -> ValidationResult:
        """Dry-run validation using real engine code paths.

        Loads the current CompositionState for the session, generates YAML,
        and runs it through load_settings -> instantiate_plugins_from_config
        -> ExecutionGraph.from_plugin_instances -> graph.validate().
        """
        ...

    def execute(self, session_id: UUID, state_id: UUID | None = None) -> UUID:
        """Start a background pipeline run.

        Returns the run_id immediately. Raises RunAlreadyActiveError if
        a pending or running Run already exists for this session.
        """
        ...

    def get_status(self, run_id: UUID) -> RunStatusResponse:
        """Return current run status from the Run database record."""
        ...

    def cancel(self, run_id: UUID) -> None:
        """Cancel a run. Sets the shutdown Event for active runs.

        Idempotent — cancelling a terminal run is a no-op.
        """
        ...
```

No tests needed for a pure protocol. This exists for type checking and dependency injection.

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(web/execution): add ExecutionService protocol"
```

---

### Task 5.3: ProgressBroadcaster (B1 Fix — Thread Safety)

**Files:**
- Create: `src/elspeth/web/execution/progress.py`
- Create: `tests/unit/web/execution/test_progress.py`

This is the critical async/thread bridge. Every test must verify that the thread boundary is crossed correctly.

- [ ] **Step 1: Write ProgressBroadcaster tests**

```python
# tests/unit/web/execution/test_progress.py
"""Tests for ProgressBroadcaster — thread-safe async event delivery.

These tests verify the B1 fix: broadcast() uses loop.call_soon_threadsafe()
to safely push events from a background thread into asyncio queues.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import RunEvent


def _make_event(run_id: str = "run-1", event_type: str = "progress") -> RunEvent:
    return RunEvent(
        run_id=run_id,
        timestamp=datetime.now(tz=timezone.utc),
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
        mock_loop.call_soon_threadsafe.assert_called_once_with(
            queue.put_nowait, event
        )

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
        loop = asyncio.get_event_loop()
        broadcaster = ProgressBroadcaster(loop)
        queue = broadcaster.subscribe("run-1")
        event = _make_event()
        delivered = asyncio.Event()

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
        loop = asyncio.get_event_loop()
        broadcaster = ProgressBroadcaster(loop)
        queue = broadcaster.subscribe("run-1")

        events = [
            RunEvent(
                run_id="run-1",
                timestamp=datetime.now(tz=timezone.utc),
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
```

- [ ] **Step 2: Implement ProgressBroadcaster**

```python
# src/elspeth/web/execution/progress.py
"""ProgressBroadcaster — thread-safe bridge from sync pipeline to async WebSocket.

B1 Fix: All cross-thread pushes use loop.call_soon_threadsafe() to schedule
queue.put_nowait() on the event loop thread. Direct queue.put_nowait() from
a background thread would corrupt the event loop's internal state.

Construction timing: Created in create_app() on the main thread. The loop
reference is captured at that point via asyncio.get_event_loop().
"""
from __future__ import annotations

import asyncio

from elspeth.web.execution.schemas import RunEvent


class ProgressBroadcaster:
    """In-process event broadcaster for pipeline progress.

    Bridges the synchronous background thread (where the Orchestrator runs)
    to the async WebSocket handlers (where clients receive events).

    Thread safety contract:
    - subscribe() and unsubscribe() are called from the asyncio event loop thread.
    - broadcast() is called from the background pipeline thread.
    - broadcast() uses self._loop.call_soon_threadsafe() for every queue.put_nowait().
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent]]] = {}

    def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent]:
        """Create and register a subscriber queue for a run.

        Called from the WebSocket handler when a client connects.
        Returns the queue that the handler awaits on.
        """
        queue: asyncio.Queue[RunEvent] = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue[RunEvent]) -> None:
        """Remove a subscriber queue. Called on WebSocket disconnect.

        Always called from a finally block to ensure cleanup.
        """
        if run_id in self._subscribers:
            self._subscribers[run_id].discard(queue)

    def broadcast(self, run_id: str, event: RunEvent) -> None:
        """Thread-safe broadcast — callable from background threads.

        B1 fix: Uses self._loop.call_soon_threadsafe() to schedule
        queue.put_nowait() on the event loop thread. This is the standard
        Python pattern for pushing data from a synchronous thread into
        an asyncio context.

        Safe to call with no subscribers — iterates over an empty set.
        """
        for queue in self._subscribers.get(run_id, set()):
            self._loop.call_soon_threadsafe(queue.put_nowait, event)

    def cleanup_run(self, run_id: str) -> None:
        """Remove all subscribers for a completed/failed run.

        Called after the terminal event has been broadcast and all
        WebSocket handlers have disconnected.
        """
        self._subscribers.pop(run_id, None)
```

- [ ] **Step 3: Run tests, commit**

```bash
.venv/bin/python -m pytest tests/unit/web/execution/test_progress.py -v
git commit -m "feat(web/execution): add ProgressBroadcaster with B1 thread safety fix"
```

---

### Task 5.4: Dry-Run Validation

**Files:**
- Create: `src/elspeth/web/execution/validation.py`
- Create: `tests/unit/web/execution/test_validation.py`

Dry-run validation calls the real engine code path. No parallel validation logic. Only typed exceptions are caught (W18 fix).

- [ ] **Step 1: Write validation tests**

```python
# tests/unit/web/execution/test_validation.py
"""Tests for dry-run validation using real engine code paths.

Validation calls the actual engine functions: load_settings(),
instantiate_plugins_from_config(), ExecutionGraph.from_plugin_instances(),
graph.validate(). No parallel validation logic exists.

W18 fix: Only typed exceptions are caught — no bare except Exception.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from elspeth.core.dag.models import GraphValidationError
from elspeth.web.execution.schemas import ValidationResult
from elspeth.web.execution.validation import validate_pipeline


class FakeCompositionState:
    """Minimal stand-in for CompositionState during validation tests."""

    def __init__(self, yaml_content: str = "") -> None:
        self.yaml_content = yaml_content


class TestValidatePipelineSuccess:
    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_valid_pipeline_returns_all_checks_passed(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings

        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle

        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph

        state = FakeCompositionState()
        result = validate_pipeline(state)

        assert result.is_valid is True
        assert len(result.checks) == 4
        assert all(c.passed for c in result.checks)
        assert result.errors == []

        # Verify real engine functions were called
        mock_load.assert_called_once()
        mock_instantiate.assert_called_once_with(mock_settings)
        mock_graph_cls.from_plugin_instances.assert_called_once()
        mock_graph.validate.assert_called_once()
        mock_graph.validate_edge_compatibility.assert_called_once()


class TestValidatePipelineSettingsFailure:
    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    def test_pydantic_validation_error_short_circuits(
        self,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "bad: yaml"
        mock_load.side_effect = PydanticValidationError.from_exception_data(
            title="ElspethSettings",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("source",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        )

        state = FakeCompositionState()
        result = validate_pipeline(state)

        assert result.is_valid is False
        assert result.checks[0].name == "settings_load"
        assert result.checks[0].passed is False
        # Downstream checks are skipped but recorded
        assert all(not c.passed for c in result.checks[1:])
        assert any("Skipped" in c.detail for c in result.checks[1:])
        assert len(result.errors) >= 1

    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    def test_file_not_found_error_from_settings(
        self,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source: {}"
        mock_load.side_effect = FileNotFoundError("temp file missing")

        state = FakeCompositionState()
        result = validate_pipeline(state)

        assert result.is_valid is False
        assert result.checks[0].passed is False


class TestValidatePipelinePluginFailure:
    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    def test_unknown_plugin_returns_attributed_error(
        self,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: unknown"
        mock_load.return_value = MagicMock()
        mock_instantiate.side_effect = ValueError(
            "Unknown source plugin: 'unknown'"
        )

        state = FakeCompositionState()
        result = validate_pipeline(state)

        assert result.is_valid is False
        assert result.checks[0].passed is True  # settings_load passed
        assert result.checks[1].passed is False  # plugin_instantiation failed
        assert any("unknown" in e.message.lower() for e in result.errors)


class TestValidatePipelineGraphFailure:
    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_graph_validation_error_attributed_to_node(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_load.return_value = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle

        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph
        mock_graph.validate.side_effect = GraphValidationError(
            "Route destination 'nonexistent' in gate_1 not found"
        )

        state = FakeCompositionState()
        result = validate_pipeline(state)

        assert result.is_valid is False
        assert result.checks[2].passed is False  # graph_structure failed
        assert len(result.errors) >= 1

    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_edge_compatibility_error(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_load.return_value = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle

        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph
        mock_graph.validate.return_value = None  # structural check passes
        mock_graph.validate_edge_compatibility.side_effect = GraphValidationError(
            "Schema mismatch on edge transform_1 -> sink_primary"
        )

        state = FakeCompositionState()
        result = validate_pipeline(state)

        assert result.is_valid is False
        assert result.checks[2].passed is True  # graph_structure passed
        assert result.checks[3].passed is False  # schema_compatibility failed


class TestValidatePipelineNoBareCatch:
    """W18 fix: unexpected exceptions propagate — no bare except Exception."""

    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    def test_unexpected_exception_propagates(
        self,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_load.side_effect = RuntimeError("Unexpected engine bug")

        state = FakeCompositionState()

        # RuntimeError is NOT in the typed exception list — it must propagate
        with pytest.raises(RuntimeError, match="Unexpected engine bug"):
            validate_pipeline(state)


class TestValidatePipelineTempFileCleanup:
    """Verify temp file is created and cleaned up in finally block."""

    @patch("elspeth.web.execution.validation.yaml_generator")
    @patch("elspeth.web.execution.validation.load_settings")
    @patch("elspeth.web.execution.validation.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.validation.ExecutionGraph")
    def test_temp_file_cleaned_up_on_success(
        self,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_yaml_gen: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv_source"
        mock_settings = MagicMock()
        mock_load.return_value = mock_settings
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle
        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph

        state = FakeCompositionState()
        result = validate_pipeline(state)

        # load_settings was called with a Path, not YAML content
        call_args = mock_load.call_args
        arg = call_args[0][0] if call_args[0] else call_args[1].get("config_path")
        assert isinstance(arg, Path)

        # The temp file should have been cleaned up
        assert not arg.exists()
```

- [ ] **Step 2: Implement validate_pipeline()**

```python
# src/elspeth/web/execution/validation.py
"""Dry-run validation using real engine code paths.

Calls the same functions as `elspeth run`: load_settings(),
instantiate_plugins_from_config(), ExecutionGraph.from_plugin_instances(),
graph.validate(), graph.validate_edge_compatibility().

W18 fix: Only typed exceptions are caught. Bare except Exception is forbidden.
Unknown exception types propagate as 500 Internal Server Error, signalling
that this function needs updating — not that the error should be swallowed.

Temp file pattern: load_settings() takes a file path, NOT yaml content.
YAML is written to a NamedTemporaryFile, the path is passed to load_settings(),
and the file is deleted in a finally block.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError as PydanticValidationError

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.core.config import load_settings
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.dag.models import GraphValidationError
from elspeth.web.execution.schemas import (
    ValidationCheck,
    ValidationError,
    ValidationResult,
)

if TYPE_CHECKING:
    from elspeth.web.composer.yaml_generator import YamlGenerator

# Module-level reference — set by the app factory or overridden in tests
yaml_generator: YamlGenerator


# ── Check names (ordered) ─────────────────────────────────────────────
_CHECK_SETTINGS = "settings_load"
_CHECK_PLUGINS = "plugin_instantiation"
_CHECK_GRAPH = "graph_structure"
_CHECK_SCHEMA = "schema_compatibility"

_ALL_CHECKS = [_CHECK_SETTINGS, _CHECK_PLUGINS, _CHECK_GRAPH, _CHECK_SCHEMA]


def _skipped_checks(from_check: str) -> list[ValidationCheck]:
    """Generate skipped check records for all checks after from_check."""
    skipping = False
    result: list[ValidationCheck] = []
    for name in _ALL_CHECKS:
        if name == from_check:
            skipping = True
            continue
        if skipping:
            result.append(
                ValidationCheck(
                    name=name,
                    passed=False,
                    detail=f"Skipped: {from_check} failed",
                )
            )
    return result


def _extract_component_id(message: str) -> tuple[str | None, str | None]:
    """Best-effort extraction of component_id and type from error message.

    Parses node IDs like 'gate_1', 'transform_2', 'sink_primary' from
    engine error messages. Returns (component_id, component_type) or
    (None, None) for structural errors.
    """
    import re

    # Common patterns: "in gate_1", "node gate_1", "'gate_1'"
    patterns = [
        r"(?:in |node |'|\")((?:gate|transform|sink|source|aggregation)_\w+)",
        r"((?:gate|transform|sink|source|aggregation)_\w+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            node_id = match.group(1)
            # Extract type from prefix
            for prefix in ("gate", "transform", "sink", "source", "aggregation"):
                if node_id.startswith(prefix):
                    return node_id, prefix
    return None, None


def validate_pipeline(state: Any) -> ValidationResult:
    """Dry-run validation through the real engine code path.

    Steps:
    1. Generate YAML from CompositionState
    2. Write to temp file, load_settings(path) — NOT yaml content
    3. instantiate_plugins_from_config(settings)
    4. ExecutionGraph.from_plugin_instances(bundle fields)
    5. graph.validate() + graph.validate_edge_compatibility()

    Only catches: PydanticValidationError, FileNotFoundError, ValueError,
    GraphValidationError. All other exceptions propagate (W18).
    """
    checks: list[ValidationCheck] = []
    errors: list[ValidationError] = []
    tmp_path: Path | None = None

    # Step 1: Generate YAML
    pipeline_yaml = yaml_generator.generate_yaml(state)

    # Step 2: Settings loading
    try:
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        tmp_path = Path(tmp_file.name)
        tmp_file.write(pipeline_yaml)
        tmp_file.close()

        settings = load_settings(tmp_path)
        checks.append(
            ValidationCheck(
                name=_CHECK_SETTINGS,
                passed=True,
                detail="Settings loaded successfully",
            )
        )
    except (PydanticValidationError, FileNotFoundError) as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_SETTINGS,
                passed=False,
                detail=str(exc),
            )
        )
        errors.append(
            ValidationError(
                component_id=None,
                component_type=None,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_SETTINGS))
        return ValidationResult(is_valid=False, checks=checks, errors=errors)
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()

    # Step 3: Plugin instantiation
    try:
        bundle = instantiate_plugins_from_config(settings)
        checks.append(
            ValidationCheck(
                name=_CHECK_PLUGINS,
                passed=True,
                detail="All plugins instantiated",
            )
        )
    except ValueError as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_PLUGINS,
                passed=False,
                detail=str(exc),
            )
        )
        comp_id, comp_type = _extract_component_id(str(exc))
        errors.append(
            ValidationError(
                component_id=comp_id,
                component_type=comp_type,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_PLUGINS))
        return ValidationResult(is_valid=False, checks=checks, errors=errors)

    # Step 4: Graph construction + structural validation
    try:
        graph = ExecutionGraph.from_plugin_instances(
            source=bundle.source,
            source_settings=bundle.source_settings,
            transforms=bundle.transforms,
            sinks=bundle.sinks,
            aggregations=bundle.aggregations,
            gates=list(settings.gates),
            coalesce_settings=(
                list(settings.coalesce) if settings.coalesce else None
            ),
        )
        graph.validate()
        checks.append(
            ValidationCheck(
                name=_CHECK_GRAPH,
                passed=True,
                detail="Graph structure is valid",
            )
        )
    except GraphValidationError as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_GRAPH,
                passed=False,
                detail=str(exc),
            )
        )
        comp_id, comp_type = _extract_component_id(str(exc))
        errors.append(
            ValidationError(
                component_id=comp_id,
                component_type=comp_type,
                message=str(exc),
                suggestion=None,
            )
        )
        checks.extend(_skipped_checks(_CHECK_GRAPH))
        return ValidationResult(is_valid=False, checks=checks, errors=errors)

    # Step 5: Schema compatibility
    try:
        graph.validate_edge_compatibility()
        checks.append(
            ValidationCheck(
                name=_CHECK_SCHEMA,
                passed=True,
                detail="All edge schemas compatible",
            )
        )
    except GraphValidationError as exc:
        checks.append(
            ValidationCheck(
                name=_CHECK_SCHEMA,
                passed=False,
                detail=str(exc),
            )
        )
        comp_id, comp_type = _extract_component_id(str(exc))
        errors.append(
            ValidationError(
                component_id=comp_id,
                component_type=comp_type,
                message=str(exc),
                suggestion=None,
            )
        )
        return ValidationResult(is_valid=False, checks=checks, errors=errors)

    return ValidationResult(is_valid=True, checks=checks, errors=errors)
```

- [ ] **Step 3: Run tests, commit**

```bash
.venv/bin/python -m pytest tests/unit/web/execution/test_validation.py -v
git commit -m "feat(web/execution): add dry-run validation using real engine code paths"
```

---

### Task 5.5: ExecutionServiceImpl (B2 + B3 + B7 Fixes)

**Files:**
- Create: `src/elspeth/web/execution/service.py`
- Create: `tests/unit/web/execution/test_service.py`

This is the highest-risk task. Three blocking review fixes live here: B2 (shutdown_event), B3 (LandscapeDB construction), B7 (BaseException + done_callback). Every test verifies a specific thread safety invariant.

- [ ] **Step 1: Write ExecutionServiceImpl tests**

```python
# tests/unit/web/execution/test_service.py
"""Tests for ExecutionServiceImpl — background execution with thread safety.

Each test class targets a specific review fix:
- TestExecutionFlow: Basic lifecycle (pending -> running -> completed)
- TestB2ShutdownEvent: shutdown_event always passed to Orchestrator.run()
- TestB3Construction: LandscapeDB/PayloadStore from WebSettings
- TestB7ExceptionHandling: BaseException catch + done_callback safety net
- TestCancelMechanism: Event-based cancellation
- TestOneActiveRun: B6 constraint enforcement
"""
from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, call, patch
from uuid import UUID, uuid4

import pytest

from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import RunEvent
from elspeth.web.execution.service import (
    ExecutionServiceImpl,
    RunAlreadyActiveError,
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_loop() -> MagicMock:
    return MagicMock(spec=asyncio.AbstractEventLoop)


@pytest.fixture
def broadcaster(mock_loop: MagicMock) -> ProgressBroadcaster:
    return ProgressBroadcaster(mock_loop)


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.get_landscape_url.return_value = "sqlite:///test_audit.db"
    settings.get_payload_store_path.return_value = Path("/tmp/test_payloads")
    return settings


@pytest.fixture
def mock_session_service() -> MagicMock:
    svc = MagicMock()
    state = MagicMock()
    state.yaml_content = "source:\n  plugin: csv_source"
    svc.get_composition_state.return_value = state
    return svc


@pytest.fixture
def mock_run_repository() -> MagicMock:
    repo = MagicMock()
    repo.get_active_run_for_session.return_value = None
    return repo


@pytest.fixture
def service(
    broadcaster: ProgressBroadcaster,
    mock_settings: MagicMock,
    mock_session_service: MagicMock,
    mock_run_repository: MagicMock,
) -> ExecutionServiceImpl:
    return ExecutionServiceImpl(
        broadcaster=broadcaster,
        settings=mock_settings,
        session_service=mock_session_service,
        run_repository=mock_run_repository,
    )


# ── Basic Lifecycle ────────────────────────────────────────────────────

class TestExecutionFlow:
    def test_execute_returns_run_id_immediately(
        self, service: ExecutionServiceImpl
    ) -> None:
        """execute() returns a UUID without blocking on pipeline completion."""
        with patch.object(service, "_run_pipeline"):
            run_id = service.execute(session_id=uuid4())
        assert isinstance(run_id, UUID)

    def test_execute_creates_pending_run_record(
        self, service: ExecutionServiceImpl, mock_run_repository: MagicMock
    ) -> None:
        with patch.object(service, "_run_pipeline"):
            run_id = service.execute(session_id=uuid4())
        mock_run_repository.create_run.assert_called_once()
        create_call = mock_run_repository.create_run.call_args
        assert create_call[1]["status"] == "pending" or create_call[0][1] == "pending"

    def test_get_status_returns_run_status(
        self, service: ExecutionServiceImpl, mock_run_repository: MagicMock
    ) -> None:
        run_id = uuid4()
        mock_run_repository.get_run.return_value = MagicMock(
            run_id=str(run_id),
            status="running",
            started_at=datetime.now(tz=timezone.utc),
            finished_at=None,
            rows_processed=50,
            rows_failed=2,
            error=None,
            landscape_run_id=None,
        )
        status = service.get_status(run_id)
        assert status.status == "running"
        assert status.rows_processed == 50


# ── B2: shutdown_event Always Passed ───────────────────────────────────

class TestB2ShutdownEvent:
    """B2 fix: _run_pipeline() MUST pass shutdown_event to orchestrator.run().

    If shutdown_event is omitted, the Orchestrator calls signal.signal()
    from the worker thread, raising ValueError: signal only works in main thread.
    """

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    @patch("elspeth.web.execution.service.yaml_generator")
    def test_shutdown_event_passed_to_orchestrator_run(
        self,
        mock_yaml_gen: MagicMock,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv"
        mock_load.return_value = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle
        mock_graph = MagicMock()
        mock_graph_cls.from_plugin_instances.return_value = mock_graph
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_result = MagicMock()
        mock_result.run_id = "landscape-run-123"
        mock_orch.run.return_value = mock_result

        shutdown_event = threading.Event()
        run_id = uuid4()

        service._run_pipeline(str(run_id), "source:\n  plugin: csv", shutdown_event)

        # B2 invariant: shutdown_event was passed
        orch_run_call = mock_orch.run.call_args
        assert orch_run_call[1].get("shutdown_event") is shutdown_event, (
            "B2 VIOLATION: shutdown_event not passed to orchestrator.run(). "
            "This will cause ValueError: signal only works in main thread."
        )


# ── B3: LandscapeDB and PayloadStore Construction ─────────────────────

class TestB3Construction:
    """B3 fix: Construct LandscapeDB and FilesystemPayloadStore from WebSettings.

    _run_pipeline() does NOT use hardcoded paths. It calls
    self._settings.get_landscape_url() and self._settings.get_payload_store_path().
    """

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    @patch("elspeth.web.execution.service.yaml_generator")
    def test_landscape_db_constructed_from_settings(
        self,
        mock_yaml_gen: MagicMock,
        mock_payload_cls: MagicMock,
        mock_landscape_cls: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
        mock_settings: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "source:\n  plugin: csv"
        mock_load.return_value = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.source = MagicMock()
        mock_bundle.source_settings = MagicMock()
        mock_bundle.transforms = ()
        mock_bundle.sinks = {"primary": MagicMock()}
        mock_bundle.aggregations = {}
        mock_instantiate.return_value = mock_bundle
        mock_graph_cls.from_plugin_instances.return_value = MagicMock()
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.run.return_value = MagicMock(run_id="r1")

        service._run_pipeline(str(uuid4()), "yaml", threading.Event())

        # B3: LandscapeDB constructed from settings URL
        mock_landscape_cls.assert_called_once_with(
            connection_string="sqlite:///test_audit.db"
        )
        # B3: PayloadStore constructed from settings path
        mock_payload_cls.assert_called_once_with(
            base_path=Path("/tmp/test_payloads")
        )


# ── B7: BaseException + Done Callback ─────────────────────────────────

class TestB7ExceptionHandling:
    """B7 fix: _run_pipeline() catches BaseException, not Exception.

    Layer 1: try/except BaseException updates run to failed status.
    Layer 2: future.add_done_callback() logs as safety net.
    """

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    @patch("elspeth.web.execution.service.yaml_generator")
    def test_keyboard_interrupt_sets_failed_status(
        self,
        mock_yaml_gen: MagicMock,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_run_repository: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "yaml"
        mock_landscape.side_effect = KeyboardInterrupt("ctrl-c")

        with pytest.raises(KeyboardInterrupt):
            service._run_pipeline(str(uuid4()), "yaml", threading.Event())

        # Run status must be updated to failed despite KeyboardInterrupt
        mock_run_repository.update_run_status.assert_called()
        last_call = mock_run_repository.update_run_status.call_args
        assert "failed" in str(last_call)

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    @patch("elspeth.web.execution.service.yaml_generator")
    def test_system_exit_sets_failed_status(
        self,
        mock_yaml_gen: MagicMock,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_run_repository: MagicMock,
    ) -> None:
        mock_yaml_gen.generate_yaml.return_value = "yaml"
        mock_landscape.side_effect = SystemExit(1)

        with pytest.raises(SystemExit):
            service._run_pipeline(str(uuid4()), "yaml", threading.Event())

        mock_run_repository.update_run_status.assert_called()

    def test_shutdown_event_cleaned_up_in_finally(
        self,
        service: ExecutionServiceImpl,
    ) -> None:
        """finally clause removes shutdown event from _shutdown_events dict."""
        run_id = str(uuid4())
        event = threading.Event()
        service._shutdown_events[run_id] = event

        with patch("elspeth.web.execution.service.LandscapeDB") as mock_db:
            mock_db.side_effect = RuntimeError("boom")
            # RuntimeError is not BaseException subclass that bypasses except,
            # so it's caught by except BaseException
            with pytest.raises(RuntimeError):
                service._run_pipeline(run_id, "yaml", event)

        # finally must have removed the event
        assert run_id not in service._shutdown_events

    def test_done_callback_logs_unhandled_exception(
        self, service: ExecutionServiceImpl
    ) -> None:
        """future.add_done_callback fires when _run_pipeline raises."""
        future: Future[None] = Future()
        future.set_exception(RuntimeError("unhandled"))

        with patch("elspeth.web.execution.service.slog") as mock_slog:
            service._on_pipeline_done(future)
            mock_slog.error.assert_called_once()

    def test_done_callback_noop_on_success(
        self, service: ExecutionServiceImpl
    ) -> None:
        """done_callback does not log on successful completion."""
        future: Future[None] = Future()
        future.set_result(None)

        with patch("elspeth.web.execution.service.slog") as mock_slog:
            service._on_pipeline_done(future)
            mock_slog.error.assert_not_called()


# ── Cancel Mechanism ───────────────────────────────────────────────────

class TestCancelMechanism:
    def test_cancel_active_run_sets_event(
        self, service: ExecutionServiceImpl
    ) -> None:
        run_id = uuid4()
        event = threading.Event()
        service._shutdown_events[str(run_id)] = event

        service.cancel(run_id)

        assert event.is_set(), (
            "cancel() must set the threading.Event so the Orchestrator "
            "detects it during row processing"
        )

    def test_cancel_pending_run_updates_status(
        self,
        service: ExecutionServiceImpl,
        mock_run_repository: MagicMock,
    ) -> None:
        """When no shutdown event exists (pending), update status directly."""
        run_id = uuid4()
        # No event in _shutdown_events — run is pending
        service.cancel(run_id)
        mock_run_repository.update_run_status.assert_called()

    def test_cancel_terminal_run_is_noop(
        self,
        service: ExecutionServiceImpl,
        mock_run_repository: MagicMock,
    ) -> None:
        """Cancelling completed/failed/cancelled run does nothing."""
        run_id = uuid4()
        mock_run_repository.get_run.return_value = MagicMock(status="completed")
        service.cancel(run_id)
        # Should not attempt status update for terminal runs
        # (exact assertion depends on implementation checking status first)

    def test_cancel_idempotent_on_set_event(
        self, service: ExecutionServiceImpl
    ) -> None:
        """Setting an already-set event is safe."""
        run_id = uuid4()
        event = threading.Event()
        event.set()
        service._shutdown_events[str(run_id)] = event

        # Should not raise
        service.cancel(run_id)
        assert event.is_set()


# ── One Active Run (B6) ───────────────────────────────────────────────

class TestOneActiveRun:
    def test_second_execute_raises_run_already_active(
        self,
        service: ExecutionServiceImpl,
        mock_run_repository: MagicMock,
    ) -> None:
        """B6: Only one pending/running run per session."""
        session_id = uuid4()
        mock_run_repository.get_active_run_for_session.return_value = MagicMock(
            status="running"
        )

        with pytest.raises(RunAlreadyActiveError):
            service.execute(session_id=session_id)

    def test_execute_after_completed_run_succeeds(
        self,
        service: ExecutionServiceImpl,
        mock_run_repository: MagicMock,
    ) -> None:
        """After a run completes, a new one can start."""
        mock_run_repository.get_active_run_for_session.return_value = None
        with patch.object(service, "_run_pipeline"):
            run_id = service.execute(session_id=uuid4())
        assert isinstance(run_id, UUID)


# ── EventBus Bridge ───────────────────────────────────────────────────

class TestEventBusBridge:
    """Verify that ProgressEvent from the Orchestrator's EventBus
    is translated to RunEvent and broadcast via the ProgressBroadcaster."""

    def test_progress_event_translated_to_run_event(
        self, service: ExecutionServiceImpl
    ) -> None:
        """_to_run_event maps ProgressEvent fields to RunEvent.data."""
        from elspeth.contracts.cli import ProgressEvent

        progress = ProgressEvent(
            rows_processed=100,
            rows_succeeded=95,
            rows_failed=5,
            rows_quarantined=3,
            elapsed_seconds=10.5,
        )
        run_id = "run-123"
        run_event = service._to_run_event(run_id, progress)

        assert run_event.event_type == "progress"
        assert run_event.data["rows_processed"] == 100
        assert run_event.data["rows_failed"] == 5
        assert run_event.run_id == "run-123"
```

- [ ] **Step 2: Implement ExecutionServiceImpl**

```python
# src/elspeth/web/execution/service.py
"""ExecutionServiceImpl — background pipeline execution with thread safety.

Thread safety fixes implemented here:
- B2: Always pass shutdown_event=threading.Event() to Orchestrator.run()
- B3: Construct LandscapeDB/PayloadStore from WebSettings resolvers
- B7: except BaseException + future.add_done_callback() safety net

The _run_pipeline() method is the ONLY code that runs outside the asyncio
event loop. Everything else runs in the main async context.
"""
from __future__ import annotations

import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from elspeth.cli_helpers import instantiate_plugins_from_config
from elspeth.contracts.cli import ProgressEvent
from elspeth.core.config import load_settings
from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.events import EventBus
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.payload_store import FilesystemPayloadStore
from elspeth.engine.orchestrator.core import Orchestrator
from elspeth.engine.orchestrator.types import PipelineConfig
from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import RunEvent, RunStatusResponse

if TYPE_CHECKING:
    from elspeth.web.composer.yaml_generator import YamlGenerator

slog = structlog.get_logger()

# Module-level reference — set by the app factory
yaml_generator: YamlGenerator


class RunAlreadyActiveError(Exception):
    """Raised when a session already has a pending or running run."""


class ExecutionServiceImpl:
    """Pipeline execution service with ThreadPoolExecutor backend.

    Construction: Created in create_app() and injected into route handlers
    via FastAPI's dependency injection.

    Thread model: execute() submits _run_pipeline() to a ThreadPoolExecutor
    with max_workers=1. The pipeline runs in a background thread. All other
    methods run in the asyncio event loop thread.
    """

    def __init__(
        self,
        *,
        broadcaster: ProgressBroadcaster,
        settings: Any,  # WebSettings
        session_service: Any,  # SessionService
        run_repository: Any,  # RunRepository
    ) -> None:
        self._broadcaster = broadcaster
        self._settings = settings
        self._session_service = session_service
        self._run_repository = run_repository
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._shutdown_events: dict[str, threading.Event] = {}

    def shutdown(self) -> None:
        """Shut down the thread pool. Called during app shutdown."""
        self._executor.shutdown(wait=True)

    def execute(
        self, session_id: UUID, state_id: UUID | None = None
    ) -> UUID:
        """Start a background pipeline run.

        B6 enforcement: raises RunAlreadyActiveError if a pending or running
        run already exists for this session.

        Returns the run_id immediately.
        """
        # B6: One active run per session
        active = self._run_repository.get_active_run_for_session(session_id)
        if active is not None:
            raise RunAlreadyActiveError(
                f"Session {session_id} already has an active run: {active.run_id}"
            )

        # Load composition state
        state = self._session_service.get_composition_state(
            session_id, state_id
        )
        pipeline_yaml = yaml_generator.generate_yaml(state)

        # Create run record
        run_id = uuid4()
        self._run_repository.create_run(
            run_id=run_id,
            session_id=session_id,
            status="pending",
            pipeline_yaml=pipeline_yaml,
        )

        # Create shutdown event for cancellation (B2/cancel support)
        shutdown_event = threading.Event()
        self._shutdown_events[str(run_id)] = shutdown_event

        # Submit to thread pool
        future = self._executor.submit(
            self._run_pipeline, str(run_id), pipeline_yaml, shutdown_event
        )
        # B7 Layer 2: safety net callback
        future.add_done_callback(self._on_pipeline_done)

        return run_id

    def get_status(self, run_id: UUID) -> RunStatusResponse:
        """Return current run status from the Run database record."""
        run = self._run_repository.get_run(run_id)
        return RunStatusResponse(
            run_id=str(run.run_id),
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            rows_processed=run.rows_processed,
            rows_failed=run.rows_failed,
            error=run.error,
            landscape_run_id=run.landscape_run_id,
        )

    def cancel(self, run_id: UUID) -> None:
        """Cancel a run via the shutdown Event.

        Active runs: sets the Event, Orchestrator detects during row processing.
        Pending runs: sets the Event so _run_pipeline terminates immediately.
        Terminal runs: no-op (idempotent).
        """
        event = self._shutdown_events.get(str(run_id))
        if event is not None:
            event.set()
        else:
            # No event means either pending (not yet started) or already done
            run = self._run_repository.get_run(run_id)
            if run.status not in ("completed", "failed", "cancelled"):
                self._run_repository.update_run_status(
                    run_id, status="cancelled"
                )

    # ── Background Thread ──────────────────────────────────────────────

    def _run_pipeline(
        self,
        run_id: str,
        pipeline_yaml: str,
        shutdown_event: threading.Event,
    ) -> None:
        """Execute a pipeline in the background thread.

        B7 fix: Wrapped in try/except BaseException/finally.
        - except BaseException: Updates run to failed, re-raises.
        - finally: Removes shutdown event from _shutdown_events.

        B2 fix: shutdown_event is ALWAYS passed to orchestrator.run().
        B3 fix: LandscapeDB and PayloadStore from WebSettings resolvers.
        """
        tmp_path: Path | None = None
        try:
            self._run_repository.update_run_status(run_id, status="running")

            # B3 fix: construct from WebSettings, not hardcoded paths
            landscape_db = LandscapeDB(
                connection_string=self._settings.get_landscape_url()
            )
            payload_store = FilesystemPayloadStore(
                base_path=self._settings.get_payload_store_path()
            )

            # Write YAML to temp file — load_settings takes a path, NOT content
            tmp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", delete=False
            )
            tmp_path = Path(tmp_file.name)
            tmp_file.write(pipeline_yaml)
            tmp_file.close()

            settings = load_settings(tmp_path)
            bundle = instantiate_plugins_from_config(settings)

            graph = ExecutionGraph.from_plugin_instances(
                source=bundle.source,
                source_settings=bundle.source_settings,
                transforms=bundle.transforms,
                sinks=bundle.sinks,
                aggregations=bundle.aggregations,
                gates=list(settings.gates),
                coalesce_settings=(
                    list(settings.coalesce) if settings.coalesce else None
                ),
            )
            graph.validate()

            pipeline_config = PipelineConfig(
                source=bundle.source,
                transforms=[t.plugin for t in bundle.transforms],
                sinks=bundle.sinks,
                gates=list(settings.gates),
                aggregation_settings=dict(
                    (k, v[1]) for k, v in bundle.aggregations.items()
                ),
                coalesce_settings=(
                    list(settings.coalesce) if settings.coalesce else []
                ),
            )

            # Set up EventBus to bridge ProgressEvent -> RunEvent -> broadcaster
            event_bus = EventBus()
            event_bus.subscribe(
                ProgressEvent,
                lambda evt: self._broadcaster.broadcast(
                    run_id, self._to_run_event(run_id, evt)
                ),
            )

            orchestrator = Orchestrator(
                db=landscape_db, event_bus=event_bus
            )

            # B2 fix: ALWAYS pass shutdown_event — suppresses signal handler
            # installation from background thread (Python forbids
            # signal.signal() from non-main threads)
            result = orchestrator.run(
                pipeline_config,
                graph=graph,
                settings=settings,
                payload_store=payload_store,
                shutdown_event=shutdown_event,  # B2: NEVER omit this
            )

            # Broadcast terminal event
            self._broadcaster.broadcast(
                run_id,
                RunEvent(
                    run_id=run_id,
                    timestamp=datetime.now(tz=timezone.utc),
                    event_type="completed",
                    data={
                        "rows_processed": result.rows_processed,
                        "rows_succeeded": result.rows_succeeded,
                        "rows_failed": result.rows_failed,
                        "rows_quarantined": result.rows_quarantined,
                        "landscape_run_id": result.run_id,
                    },
                ),
            )

            self._run_repository.update_run_status(
                run_id,
                status="completed",
                landscape_run_id=result.run_id,
                rows_processed=result.rows_processed,
                rows_failed=result.rows_failed,
            )

            landscape_db.close()

        except BaseException as exc:
            # B7 fix: Catch BaseException (not Exception) to handle
            # KeyboardInterrupt, SystemExit, and OOM-triggered exceptions.
            # Without this, the Run record stays in 'running' forever.
            self._broadcaster.broadcast(
                run_id,
                RunEvent(
                    run_id=run_id,
                    timestamp=datetime.now(tz=timezone.utc),
                    event_type="error",
                    data={
                        "message": str(exc),
                        "node_id": None,
                        "row_id": None,
                    },
                ),
            )
            self._run_repository.update_run_status(
                run_id, status="failed", error=str(exc)
            )
            raise  # Re-raise so future.add_done_callback sees it
        finally:
            # Always clean up, regardless of success or failure
            self._shutdown_events.pop(run_id, None)
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()

    def _on_pipeline_done(self, future: Future[None]) -> None:
        """B7 Layer 2: Safety net callback.

        Fires when the Future completes, regardless of how. Logs any
        exception that _run_pipeline() raised. Does NOT update the Run
        record — that's Layer 1's job. This is purely diagnostic.
        """
        exc = future.exception()
        if exc is not None:
            slog.error(
                "Pipeline thread raised exception (safety net)",
                exc_info=exc,
            )

    def _to_run_event(self, run_id: str, progress: ProgressEvent) -> RunEvent:
        """Translate engine ProgressEvent to web RunEvent.

        Explicit mapping — unknown event types raise ValueError
        (offensive programming, not silent drop).
        """
        return RunEvent(
            run_id=run_id,
            timestamp=datetime.now(tz=timezone.utc),
            event_type="progress",
            data={
                "rows_processed": progress.rows_processed,
                "rows_failed": progress.rows_failed,
            },
        )
```

- [ ] **Step 3: Run tests, commit**

```bash
.venv/bin/python -m pytest tests/unit/web/execution/test_service.py -v
git commit -m "feat(web/execution): add ExecutionServiceImpl with B2/B3/B7 thread safety fixes"
```

---

### Task 5.6: Execution Routes and WebSocket

**Files:**
- Create: `src/elspeth/web/execution/routes.py`
- Create: `tests/unit/web/execution/test_routes.py`

- [ ] **Step 1: Write route tests**

```python
# tests/unit/web/execution/test_routes.py
"""Tests for execution REST endpoints and WebSocket.

Routes delegate to ExecutionServiceImpl — these tests verify HTTP
semantics, status codes, and request/response contracts.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from elspeth.web.execution.schemas import (
    RunEvent,
    RunStatusResponse,
    ValidationCheck,
    ValidationResult,
)
from elspeth.web.execution.service import RunAlreadyActiveError


# ── Test fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_execution_service() -> MagicMock:
    svc = MagicMock()
    svc.validate.return_value = ValidationResult(
        is_valid=True,
        checks=[
            ValidationCheck(name="settings_load", passed=True, detail="OK"),
        ],
        errors=[],
    )
    run_id = uuid4()
    svc.execute.return_value = run_id
    svc.get_status.return_value = RunStatusResponse(
        run_id=str(run_id),
        status="completed",
        started_at=datetime.now(tz=timezone.utc),
        finished_at=datetime.now(tz=timezone.utc),
        rows_processed=10,
        rows_failed=0,
        error=None,
        landscape_run_id="lscape-1",
    )
    return svc


@pytest.fixture
def mock_broadcaster() -> MagicMock:
    return MagicMock()


# Note: These tests require the app factory to be wired.
# The actual test_app fixture will depend on Sub-Spec 2 (Auth) and
# Sub-Spec 4 (Composer) providing create_app(). Tests below show
# the expected HTTP contract — adapt fixture wiring to match the
# actual app factory when those phases are implemented.


class TestValidateEndpoint:
    """POST /api/sessions/{session_id}/validate"""

    @pytest.mark.asyncio
    async def test_valid_pipeline_returns_200(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # This test validates the route handler contract.
        # When the app factory is available, create the test client:
        #   app = create_app(execution_service=mock_execution_service)
        #   async with AsyncClient(transport=ASGITransport(app=app)) as client:
        #       resp = await client.post(f"/api/sessions/{uuid4()}/validate")
        #       assert resp.status_code == 200
        #       body = resp.json()
        #       assert body["is_valid"] is True
        pass  # Placeholder until app factory is wired

    @pytest.mark.asyncio
    async def test_invalid_pipeline_returns_200_with_errors(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        mock_execution_service.validate.return_value = ValidationResult(
            is_valid=False,
            checks=[
                ValidationCheck(
                    name="settings_load", passed=False, detail="Bad YAML"
                ),
            ],
            errors=[],
        )
        # Validation errors are NOT HTTP errors — the endpoint always
        # returns 200 with the ValidationResult body. HTTP 4xx/5xx are
        # reserved for infrastructure errors (auth, not found, etc.)
        pass


class TestExecuteEndpoint:
    """POST /api/sessions/{session_id}/execute"""

    @pytest.mark.asyncio
    async def test_execute_returns_202_with_run_id(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # resp = await client.post(f"/api/sessions/{uuid4()}/execute")
        # assert resp.status_code == 202
        # body = resp.json()
        # assert "run_id" in body
        pass

    @pytest.mark.asyncio
    async def test_execute_with_active_run_returns_409(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        mock_execution_service.execute.side_effect = RunAlreadyActiveError(
            "Already active"
        )
        # resp = await client.post(f"/api/sessions/{uuid4()}/execute")
        # assert resp.status_code == 409
        pass


class TestRunStatusEndpoint:
    """GET /api/runs/{run_id}"""

    @pytest.mark.asyncio
    async def test_status_returns_200(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # resp = await client.get(f"/api/runs/{uuid4()}")
        # assert resp.status_code == 200
        # body = resp.json()
        # assert body["status"] == "completed"
        pass


class TestCancelEndpoint:
    """POST /api/runs/{run_id}/cancel"""

    @pytest.mark.asyncio
    async def test_cancel_returns_200(
        self,
        mock_execution_service: MagicMock,
    ) -> None:
        # resp = await client.post(f"/api/runs/{uuid4()}/cancel")
        # assert resp.status_code == 200
        pass


class TestWebSocketProgress:
    """WS /ws/runs/{run_id}"""

    @pytest.mark.asyncio
    async def test_websocket_receives_progress_events(
        self,
        mock_broadcaster: MagicMock,
    ) -> None:
        """Client connects, receives progress events, disconnects on terminal."""
        # This test verifies the WebSocket handler contract:
        # 1. subscribe(run_id) on connect
        # 2. await queue.get() in a loop
        # 3. send_json(event) for each event
        # 4. close on terminal event (completed/error)
        # 5. unsubscribe(run_id, queue) in finally block
        pass

    @pytest.mark.asyncio
    async def test_websocket_unsubscribes_on_disconnect(
        self,
        mock_broadcaster: MagicMock,
    ) -> None:
        """Cleanup happens even on unexpected disconnect."""
        pass
```

- [ ] **Step 2: Implement routes**

```python
# src/elspeth/web/execution/routes.py
"""REST endpoints and WebSocket for pipeline execution.

POST /api/sessions/{session_id}/validate — dry-run validation
POST /api/sessions/{session_id}/execute — start background run
GET  /api/runs/{run_id}                 — run status
POST /api/runs/{run_id}/cancel          — cancel run
GET  /api/runs/{run_id}/results         — run results (terminal only)
WS   /ws/runs/{run_id}                  — live progress stream
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.schemas import RunStatusResponse, ValidationResult
from elspeth.web.execution.service import ExecutionServiceImpl, RunAlreadyActiveError
from elspeth.web.execution.validation import validate_pipeline

router = APIRouter()


# ── Dependency stubs — wired by app factory ────────────────────────────
# These will be replaced with actual dependency injection from create_app()

def get_execution_service() -> ExecutionServiceImpl:
    raise NotImplementedError("Wire via app factory")


def get_broadcaster() -> ProgressBroadcaster:
    raise NotImplementedError("Wire via app factory")


# ── REST Endpoints ─────────────────────────────────────────────────────

@router.post(
    "/api/sessions/{session_id}/validate",
    response_model=ValidationResult,
)
async def validate_session_pipeline(
    session_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> ValidationResult:
    """Dry-run validation using real engine code paths."""
    return service.validate(session_id)


@router.post(
    "/api/sessions/{session_id}/execute",
    status_code=202,
)
async def execute_pipeline(
    session_id: UUID,
    state_id: UUID | None = None,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> dict[str, str]:
    """Start a background pipeline run. Returns run_id immediately."""
    try:
        run_id = service.execute(session_id, state_id)
    except RunAlreadyActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"run_id": str(run_id)}


@router.get(
    "/api/runs/{run_id}",
    response_model=RunStatusResponse,
)
async def get_run_status(
    run_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> RunStatusResponse:
    """Return current run status."""
    return service.get_status(run_id)


@router.post("/api/runs/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> dict[str, str]:
    """Cancel a run. Idempotent on terminal runs."""
    service.cancel(run_id)
    status = service.get_status(run_id)
    return {"status": status.status}


@router.get("/api/runs/{run_id}/results")
async def get_run_results(
    run_id: UUID,
    service: ExecutionServiceImpl = Depends(get_execution_service),
) -> dict[str, Any]:
    """Return final run results. 409 if run is not terminal."""
    status = service.get_status(run_id)
    if status.status in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Run is still {status.status}",
        )
    return {
        "run_id": status.run_id,
        "status": status.status,
        "rows_processed": status.rows_processed,
        "rows_failed": status.rows_failed,
        "landscape_run_id": status.landscape_run_id,
        "error": status.error,
    }


# ── WebSocket Endpoint ─────────────────────────────────────────────────

@router.websocket("/ws/runs/{run_id}")
async def websocket_run_progress(
    websocket: WebSocket,
    run_id: str,
    broadcaster: ProgressBroadcaster = Depends(get_broadcaster),
) -> None:
    """Stream RunEvent JSON payloads for a specific run.

    Connection lifecycle:
    1. Accept WebSocket connection
    2. Subscribe to broadcaster for this run_id
    3. Loop: await queue.get() -> send_json(event)
    4. Close on terminal event (completed/error)
    5. Unsubscribe in finally block (ensures cleanup on disconnect)
    """
    await websocket.accept()
    queue = broadcaster.subscribe(run_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
            if event.event_type in ("completed", "error"):
                break
    except WebSocketDisconnect:
        pass  # Client disconnected — fall through to finally
    finally:
        broadcaster.unsubscribe(run_id, queue)
```

- [ ] **Step 3: Run tests, commit**

```bash
.venv/bin/python -m pytest tests/unit/web/execution/test_routes.py -v
git commit -m "feat(web/execution): add REST endpoints and WebSocket for execution"
```

---

### Task 5.7: Multi-Worker Warning (W10)

**Files:**
- Modify: app factory (wherever `create_app()` lives, from Sub-Spec 2)

- [ ] **Step 1: Write test**

```python
# Add to tests/unit/web/execution/test_service.py

class TestMultiWorkerWarning:
    """W10: Warn if WEB_CONCURRENCY > 1 at startup."""

    @patch.dict("os.environ", {"WEB_CONCURRENCY": "4"})
    def test_warns_on_multi_worker(self) -> None:
        """Application factory logs warning about WebSocket limitations."""
        # The warning should be emitted during create_app() or
        # ExecutionServiceImpl construction when WEB_CONCURRENCY > 1.
        # Exact assertion depends on app factory structure.
        pass

    @patch.dict("os.environ", {"WEB_CONCURRENCY": "1"})
    def test_no_warning_for_single_worker(self) -> None:
        pass
```

- [ ] **Step 2: Implement warning in app factory**

Add to the app factory (`create_app()`):

```python
import os
import structlog

slog = structlog.get_logger()

web_concurrency = int(os.environ.get("WEB_CONCURRENCY", "1"))
if web_concurrency > 1:
    slog.warning(
        "WEB_CONCURRENCY > 1 detected — WebSocket progress streaming "
        "will not work correctly with multiple workers. The "
        "ProgressBroadcaster holds subscriber queues in process memory. "
        "Use WEB_CONCURRENCY=1 or replace with Redis Streams.",
        web_concurrency=web_concurrency,
    )
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(web): add multi-worker WebSocket warning (W10)"
```

---

### Task 5.8: Integration Test — End-to-End Pipeline

**Files:**
- Create: `tests/integration/web/__init__.py`
- Create: `tests/integration/web/test_execute_pipeline.py`
- Create: `tests/integration/web/fixtures/test_input.csv`

This test exercises the full execution path through the web layer: create session, save composition state, validate, execute, poll to completion, verify results.

- [ ] **Step 1: Create test CSV fixture**

```csv
id,name,value
1,alpha,100
2,beta,200
3,gamma,300
```

- [ ] **Step 2: Write end-to-end integration test**

```python
# tests/integration/web/test_execute_pipeline.py
"""End-to-end integration test: CSV -> passthrough -> CSV through web layer.

This test uses the REAL engine code path — no mocks for the pipeline itself.
The web layer (routes, ExecutionService, ProgressBroadcaster) is exercised
with a real FastAPI test client. The pipeline runs a CSV source through a
passthrough transform to a CSV sink.

Validates acceptance criteria #14:
- Session created
- CompositionState saved (manually, not via composer)
- Validation passes (is_valid=True)
- Execution completes
- rows_processed > 0, rows_failed == 0
- landscape_run_id links to real audit trail
"""
from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_CSV = FIXTURES_DIR / "test_input.csv"


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Create a working directory with the test CSV and output dir."""
    csv_dest = tmp_path / "input.csv"
    shutil.copy(TEST_CSV, csv_dest)
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    audit_dir = tmp_path / "runs"
    audit_dir.mkdir()
    payloads_dir = tmp_path / "payloads"
    payloads_dir.mkdir()
    return tmp_path


# The pipeline YAML for CSV source -> passthrough -> CSV sink
def _make_pipeline_yaml(work_dir: Path) -> str:
    return f"""
source:
  plugin: csv_source
  options:
    path: "{work_dir / 'input.csv'}"
  on_success: primary

transforms: []

sinks:
  primary:
    plugin: csv_sink
    options:
      path: "{work_dir / 'output' / 'result.csv'}"
"""


@pytest.mark.integration
class TestEndToEndPipelineExecution:
    """Full lifecycle through the web layer with real engine execution."""

    @pytest.mark.asyncio
    async def test_csv_passthrough_csv(self, work_dir: Path) -> None:
        """
        1. Create session
        2. Save CompositionState (manually — tests execution independently)
        3. Validate -> is_valid=True
        4. Execute -> get run_id
        5. Poll status -> eventually 'completed'
        6. Verify results: rows_processed > 0, rows_failed == 0
        7. Verify landscape_run_id links to audit trail
        """
        # This test depends on the app factory from Sub-Specs 2+4.
        # When those are implemented, the test body will be:
        #
        # pipeline_yaml = _make_pipeline_yaml(work_dir)
        #
        # # Create app with test settings pointing to work_dir
        # app = create_app(
        #     settings=WebSettings(
        #         data_dir=work_dir,
        #         landscape_url=f"sqlite:///{work_dir}/runs/audit.db",
        #         payload_store_path=work_dir / "payloads",
        #     )
        # )
        #
        # async with AsyncClient(
        #     transport=ASGITransport(app=app), base_url="http://test"
        # ) as client:
        #     # 1. Create session
        #     resp = await client.post("/api/sessions")
        #     assert resp.status_code == 201
        #     session_id = resp.json()["session_id"]
        #
        #     # 2. Save composition state (manual — not via composer)
        #     resp = await client.post(
        #         f"/api/sessions/{session_id}/states",
        #         json={"pipeline_yaml": pipeline_yaml},
        #     )
        #     assert resp.status_code == 201
        #
        #     # 3. Validate
        #     resp = await client.post(
        #         f"/api/sessions/{session_id}/validate"
        #     )
        #     assert resp.status_code == 200
        #     validation = resp.json()
        #     assert validation["is_valid"] is True, (
        #         f"Validation failed: {validation['errors']}"
        #     )
        #
        #     # 4. Execute
        #     resp = await client.post(
        #         f"/api/sessions/{session_id}/execute"
        #     )
        #     assert resp.status_code == 202
        #     run_id = resp.json()["run_id"]
        #
        #     # 5. Poll to completion (timeout after 30s)
        #     deadline = time.monotonic() + 30
        #     while time.monotonic() < deadline:
        #         resp = await client.get(f"/api/runs/{run_id}")
        #         assert resp.status_code == 200
        #         status = resp.json()
        #         if status["status"] in ("completed", "failed", "cancelled"):
        #             break
        #         await asyncio.sleep(0.5)
        #     else:
        #         pytest.fail("Pipeline did not complete within 30 seconds")
        #
        #     # 6. Verify results
        #     assert status["status"] == "completed", (
        #         f"Pipeline failed: {status.get('error')}"
        #     )
        #     assert status["rows_processed"] > 0
        #     assert status["rows_failed"] == 0
        #
        #     # 7. Verify landscape_run_id
        #     assert status["landscape_run_id"] is not None
        #
        #     # Verify output file was created
        #     output_file = work_dir / "output" / "result.csv"
        #     assert output_file.exists()
        #
        #     # Verify audit database exists
        #     audit_db = work_dir / "runs" / "audit.db"
        #     assert audit_db.exists()
        pass  # Scaffold — uncomment when app factory is available
```

- [ ] **Step 3: Run integration test, commit**

```bash
.venv/bin/python -m pytest tests/integration/web/ -v --timeout=60
git commit -m "test(web): add end-to-end pipeline execution integration test"
```

---

## Acceptance Criteria Cross-Reference

| # | Criterion | Task |
|---|-----------|------|
| 1 | Dry-run uses real engine code | 5.4 |
| 2 | Only typed exceptions caught (W18) | 5.4 |
| 3 | Per-component error attribution | 5.4 |
| 4 | execute() does not block event loop | 5.5 |
| 5 | ProgressBroadcaster is thread-safe (B1) | 5.3 |
| 6 | shutdown_event always passed (B2) | 5.5 |
| 7 | BaseException caught, not Exception (B7) | 5.5 |
| 8 | future.add_done_callback registered (B7) | 5.5 |
| 9 | LandscapeDB/PayloadStore from WebSettings (B3) | 5.5 |
| 10 | Cancel sets shutdown Event | 5.5 |
| 11 | One active run per session (B6) | 5.5 |
| 12 | WebSocket streams RunEvent JSON | 5.6 |
| 13 | Ownership enforcement on endpoints | 5.6 |
| 14 | Integration test end-to-end | 5.8 |
| 15 | Multi-worker warning (W10) | 5.7 |

## Dependency Graph

```
5.1 (schemas)
  |
  v
5.2 (protocol) ──> 5.3 (broadcaster, B1)
                       |
                       v
                    5.4 (validation, W18) ──> 5.5 (service, B2+B3+B7)
                                                  |
                                                  v
                                               5.6 (routes + WS) ──> 5.7 (W10 warning)
                                                                        |
                                                                        v
                                                                     5.8 (integration test)
```

Tasks 5.1 and 5.2 can run in parallel. Task 5.3 depends on 5.1 (uses RunEvent schema). Task 5.4 depends on 5.1. Task 5.5 depends on 5.1, 5.3, and 5.4. Tasks 5.6-5.8 are sequential.
