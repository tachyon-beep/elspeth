"""Tests for ExecutionServiceImpl — background execution with thread safety.

Each test class targets a specific review fix:
- TestExecutionFlow: Basic lifecycle (pending -> running -> completed)
- TestB2ShutdownEvent: shutdown_event always passed to Orchestrator.run()
- TestB3Construction: LandscapeDB/PayloadStore from WebSettings
- TestB7ExceptionHandling: BaseException catch + done_callback safety net
- TestB8AsyncBridging: _call_async() bridges sync thread to async event loop
- TestCancelMechanism: Event-based cancellation
- TestOneActiveRun: B6 constraint enforcement
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from collections.abc import Coroutine
from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from elspeth.web.execution.progress import ProgressBroadcaster
from elspeth.web.execution.service import ExecutionServiceImpl
from elspeth.web.sessions.protocol import RunAlreadyActiveError

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
    settings.landscape_passphrase = None
    return settings


@pytest.fixture
def mock_session_service() -> MagicMock:
    svc = MagicMock()
    state = MagicMock()
    state.yaml_content = "source:\n  plugin: csv_source"
    # SessionService methods are async — use AsyncMock for awaitable returns
    # state_record needs fields that state_from_record() accesses
    state.id = uuid4()
    state.session_id = uuid4()
    state.version = 1
    state.source = None  # No source → path allowlist check skips
    state.nodes = None
    state.edges = None
    state.outputs = None
    state.metadata_ = {"name": "Test", "description": ""}
    svc.get_state = AsyncMock(return_value=state)
    svc.get_current_state = AsyncMock(return_value=state)
    svc.get_active_run = AsyncMock(return_value=None)
    svc.create_run = AsyncMock(return_value=MagicMock(id=uuid4()))
    svc.get_run = AsyncMock(return_value=MagicMock(status="pending"))
    svc.update_run_status = AsyncMock()
    return svc


@pytest.fixture
def service(
    mock_loop: MagicMock,
    broadcaster: ProgressBroadcaster,
    mock_settings: MagicMock,
    mock_session_service: MagicMock,
) -> ExecutionServiceImpl:
    # AC #17: All Run CRUD goes through SessionService — no direct DB access.
    svc = ExecutionServiceImpl(
        loop=mock_loop,
        broadcaster=broadcaster,
        settings=mock_settings,
        session_service=mock_session_service,
        yaml_generator=MagicMock(),
    )
    # Patch _call_async for tests that call _run_pipeline directly (sync).
    # The real _call_async uses asyncio.run_coroutine_threadsafe which needs
    # a running event loop. In unit tests, we bridge by running the coroutine
    # synchronously via asyncio.get_event_loop().run_until_complete().
    # TestB8AsyncBridging tests _call_async itself with its own mocking.
    _real_loop = asyncio.new_event_loop()

    def _mock_call_async(coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            return _real_loop.run_until_complete(coro)
        except RuntimeError:
            # If no event loop is available, just close the coroutine
            coro.close()
            return None

    cast(Any, svc)._call_async = _mock_call_async
    return svc


# ── Basic Lifecycle ────────────────────────────────────────────────────


class TestExecutionFlow:
    @pytest.mark.asyncio
    async def test_execute_returns_run_id_immediately(self, service: ExecutionServiceImpl) -> None:
        """execute() returns a UUID without blocking on pipeline completion."""
        with patch.object(service, "_run_pipeline"):
            run_id = await service.execute(session_id=uuid4())
        assert isinstance(run_id, UUID)

    @pytest.mark.asyncio
    async def test_execute_creates_run_via_session_service(self, service: ExecutionServiceImpl, mock_session_service: MagicMock) -> None:
        """AC #17: Run creation delegates to session_service.create_run()
        with R6 expanded params (session_id, state_id, pipeline_yaml)."""
        with patch.object(service, "_run_pipeline"):
            await service.execute(session_id=uuid4())
        mock_session_service.create_run.assert_called_once()
        create_call = mock_session_service.create_run.call_args
        assert "session_id" in create_call[1] or len(create_call[0]) >= 1
        assert "pipeline_yaml" in create_call[1] or len(create_call[0]) >= 2

    @pytest.mark.asyncio
    async def test_get_status_returns_run_status(self, service: ExecutionServiceImpl, mock_session_service: MagicMock) -> None:
        run_id = uuid4()
        mock_session_service.get_run.return_value = MagicMock(
            id=run_id,  # B7: RunRecord uses `id`, not `run_id`
            status="running",
            started_at=datetime.now(tz=UTC),
            finished_at=None,
            rows_processed=50,
            rows_failed=2,
            error=None,
            landscape_run_id=None,
        )
        status = await service.get_status(run_id)
        assert status.status == "running"
        assert status.rows_processed == 50


# ── B2: shutdown_event Always Passed ───────────────────────────────────


class TestB2ShutdownEvent:
    """B2 fix: _run_pipeline() MUST pass shutdown_event to orchestrator.run().

    If shutdown_event is omitted, the Orchestrator calls signal.signal()
    from the worker thread, raising ValueError: signal only works in main thread.
    """

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_shutdown_event_passed_to_orchestrator_run(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
    ) -> None:
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
            "B2 VIOLATION: shutdown_event not passed to orchestrator.run(). This will cause ValueError: signal only works in main thread."
        )


# ── B3: LandscapeDB and PayloadStore Construction ─────────────────────


class TestB3Construction:
    """B3 fix: Construct LandscapeDB and FilesystemPayloadStore from WebSettings.

    _run_pipeline() does NOT use hardcoded paths. It calls
    self._settings.get_landscape_url() and self._settings.get_payload_store_path().
    """

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_landscape_db_constructed_from_settings(
        self,
        mock_payload_cls: MagicMock,
        mock_landscape_cls: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
        mock_settings: MagicMock,
    ) -> None:
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
        mock_landscape_cls.assert_called_once_with(connection_string="sqlite:///test_audit.db", passphrase=None)
        # B3: PayloadStore constructed from settings path
        mock_payload_cls.assert_called_once_with(base_path=Path("/tmp/test_payloads"))


# ── B7: BaseException + Done Callback ─────────────────────────────────


class TestB7ExceptionHandling:
    """B7 fix: _run_pipeline() catches BaseException, not Exception.

    Layer 1: try/except BaseException updates run to failed status.
    Layer 2: future.add_done_callback() logs as safety net.
    """

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_keyboard_interrupt_skips_failed_status_update(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """R6 fix: KeyboardInterrupt skips _call_async for the 'failed' update.

        The initial 'running' update succeeds (before LandscapeDB raises).
        The except block skips the 'failed' update — orphan cleanup handles it.
        """
        mock_landscape.side_effect = KeyboardInterrupt("ctrl-c")

        with pytest.raises(KeyboardInterrupt):
            service._run_pipeline(str(uuid4()), "yaml", threading.Event())

        # R6: The 'running' update went through, but the 'failed' update was skipped
        calls = mock_session_service.update_run_status.call_args_list
        assert len(calls) == 1  # Only the initial "running" call
        assert calls[0][1].get("status") == "running"

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_system_exit_skips_failed_status_update(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """R6 fix: SystemExit skips _call_async for the 'failed' update."""
        mock_landscape.side_effect = SystemExit(1)

        with pytest.raises(SystemExit):
            service._run_pipeline(str(uuid4()), "yaml", threading.Event())

        # R6: The 'running' update went through, but the 'failed' update was skipped
        calls = mock_session_service.update_run_status.call_args_list
        assert len(calls) == 1  # Only the initial "running" call
        assert calls[0][1].get("status") == "running"

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
            with pytest.raises(RuntimeError):
                service._run_pipeline(run_id, "yaml", event)

        # finally must have removed the event
        assert run_id not in service._shutdown_events

    def test_done_callback_logs_unhandled_exception(self, service: ExecutionServiceImpl) -> None:
        """future.add_done_callback fires when _run_pipeline raises."""
        future: Future[None] = Future()
        future.set_exception(RuntimeError("unhandled"))

        with patch("elspeth.web.execution.service.slog") as mock_slog:
            service._on_pipeline_done(future)
            mock_slog.error.assert_called_once()

    def test_done_callback_noop_on_success(self, service: ExecutionServiceImpl) -> None:
        """done_callback does not log on successful completion."""
        future: Future[None] = Future()
        future.set_result(None)

        with patch("elspeth.web.execution.service.slog") as mock_slog:
            service._on_pipeline_done(future)
            mock_slog.error.assert_not_called()


# ── Cancel Mechanism ───────────────────────────────────────────────────


class TestCancelMechanism:
    @pytest.mark.asyncio
    async def test_cancel_active_run_sets_event(self, service: ExecutionServiceImpl) -> None:
        run_id = uuid4()
        event = threading.Event()
        service._shutdown_events[str(run_id)] = event

        await service.cancel(run_id)

        assert event.is_set(), "cancel() must set the threading.Event so the Orchestrator detects it during row processing"

    @pytest.mark.asyncio
    async def test_cancel_pending_run_updates_status(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """When no shutdown event exists (pending), update status directly."""
        run_id = uuid4()
        # No event in _shutdown_events — run is pending
        await service.cancel(run_id)
        mock_session_service.update_run_status.assert_called()

    @pytest.mark.asyncio
    async def test_cancel_terminal_run_is_noop(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Cancelling completed/failed/cancelled run does nothing."""
        run_id = uuid4()
        mock_session_service.get_run.return_value = MagicMock(status="completed")
        await service.cancel(run_id)
        mock_session_service.update_run_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_idempotent_on_set_event(self, service: ExecutionServiceImpl) -> None:
        """Setting an already-set event is safe."""
        run_id = uuid4()
        event = threading.Event()
        event.set()
        service._shutdown_events[str(run_id)] = event

        # Should not raise
        await service.cancel(run_id)
        assert event.is_set()

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_cancelled_run_broadcasts_cancelled_event(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """When orchestrator raises GracefulShutdownError, _run_pipeline
        broadcasts 'cancelled' and updates status accordingly."""
        from elspeth.contracts.errors import GracefulShutdownError

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
        # Orchestrator raises GracefulShutdownError on actual cancellation
        mock_orch.run.side_effect = GracefulShutdownError(
            rows_processed=50,
            run_id="test-run-001",
            rows_failed=2,
        )

        shutdown_event = threading.Event()
        shutdown_event.set()
        run_id = str(uuid4())

        service._run_pipeline(run_id, "source:\n  plugin: csv", shutdown_event)

        # Verify status updated to "cancelled" (not "completed" or "failed")
        status_calls = mock_session_service.update_run_status.call_args_list
        final_status_call = status_calls[-1]
        assert "cancelled" in str(final_status_call), f"Expected 'cancelled' status update, got: {final_status_call}"

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_completed_run_not_misclassified_when_event_set_late(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Race guard: if shutdown_event is set AFTER orchestrator completes
        (returns normally), the run must still be classified as 'completed',
        not 'cancelled'."""
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
        mock_result = MagicMock()
        mock_result.rows_processed = 50
        mock_result.rows_failed = 2
        mock_orch.run.return_value = mock_result

        # Event is set (simulating late cancel() call) but orchestrator
        # returned normally — run completed before cancel was processed.
        shutdown_event = threading.Event()
        shutdown_event.set()
        run_id = str(uuid4())

        service._run_pipeline(run_id, "source:\n  plugin: csv", shutdown_event)

        # Must be "completed", NOT "cancelled"
        status_calls = mock_session_service.update_run_status.call_args_list
        final_status_call = status_calls[-1]
        assert "completed" in str(final_status_call), f"Expected 'completed' status update, got: {final_status_call}"

    # ── Race condition: cancel() before _run_pipeline starts ──────────

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_run_pipeline_exits_gracefully_when_already_cancelled(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Race fix: if cancel() set DB to 'cancelled' before _run_pipeline
        starts, the pending→running transition fails. _run_pipeline must
        detect this and exit cleanly — no Orchestrator, no crash."""
        run_id = str(uuid4())

        # Simulate: update_run_status("running") raises because status is "cancelled"
        mock_session_service.update_run_status.side_effect = ValueError("Illegal run transition: 'cancelled' → 'running'. Allowed: []")
        mock_session_service.get_run.return_value = MagicMock(status="cancelled")

        # Should NOT raise — graceful exit
        service._run_pipeline(run_id, "yaml", threading.Event())

        # No Orchestrator or LandscapeDB instantiated (early return)
        mock_landscape.assert_not_called()
        mock_payload.assert_not_called()

        # Only the one failed "running" attempt — no "failed" status update
        assert mock_session_service.update_run_status.call_count == 1

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_run_pipeline_reraises_valueerror_when_not_cancelled(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """If update_run_status raises ValueError for a reason other than
        'already cancelled', _run_pipeline must re-raise (offensive programming)."""
        run_id = str(uuid4())

        mock_session_service.update_run_status.side_effect = ValueError("Illegal run transition: 'completed' → 'running'. Allowed: []")
        mock_session_service.get_run.return_value = MagicMock(status="completed")

        with pytest.raises(ValueError, match="completed"):
            service._run_pipeline(run_id, "yaml", threading.Event())

    @pytest.mark.asyncio
    async def test_shutdown_event_registered_before_blob_linkage(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Race fix part 2: _shutdown_events registration must happen before
        blob linkage, so cancel() finds the event during the blob window."""
        session_id = uuid4()
        run_id = uuid4()
        blob_ref = str(uuid4())
        mock_session_service.create_run.return_value = MagicMock(id=run_id)

        blob_service = MagicMock()
        blob_service.get_blob = AsyncMock(return_value=MagicMock(session_id=session_id))

        async def tracking_link(*args: Any, **kwargs: Any) -> None:
            # At the time blob linkage runs, the event MUST already exist
            assert str(run_id) in service._shutdown_events, "RACE: _shutdown_events not registered before blob linkage"

        blob_service.link_blob_to_run = AsyncMock(side_effect=tracking_link)
        cast(Any, service)._blob_service = blob_service

        # Set up state record with a source containing a blob_ref.
        # Use a real dict so state_from_record → deep_thaw works correctly.
        state = mock_session_service.get_current_state.return_value
        state.source = {
            "plugin": "csv",
            "on_success": "continue",
            "options": {"blob_ref": blob_ref},
            "on_validation_failure": "quarantine",
        }

        with patch.object(service, "_run_pipeline"):
            await service.execute(session_id=session_id)

    @pytest.mark.asyncio
    async def test_shutdown_event_cleaned_up_on_blob_linkage_failure(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """If blob linkage raises after event registration, the event must
        be cleaned up to avoid leaking into _shutdown_events."""
        session_id = uuid4()
        run_id = uuid4()
        blob_ref = str(uuid4())
        mock_session_service.create_run.return_value = MagicMock(id=run_id)

        blob_service = MagicMock()
        blob_service.get_blob = AsyncMock(return_value=MagicMock(session_id=session_id))
        blob_service.link_blob_to_run = AsyncMock(side_effect=RuntimeError("blob storage unavailable"))
        cast(Any, service)._blob_service = blob_service

        # Use a real dict so state_from_record → deep_thaw works correctly.
        state = mock_session_service.get_current_state.return_value
        state.source = {
            "plugin": "csv",
            "on_success": "continue",
            "options": {"blob_ref": blob_ref},
            "on_validation_failure": "quarantine",
        }

        with pytest.raises(RuntimeError, match="blob storage unavailable"):
            await service.execute(session_id=session_id)

        assert str(run_id) not in service._shutdown_events


# ── Blob Ref Pre-Validation ───────────────────────────────────────────


class TestBlobRefPreValidation:
    """Malformed blob_ref must raise BEFORE create_run() to avoid
    orphaning a pending run that blocks future executions."""

    @pytest.mark.asyncio
    async def test_malformed_blob_ref_raises_before_run_creation(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """A non-UUID blob_ref raises ValueError before create_run()
        is called, so no pending run is orphaned."""
        state = mock_session_service.get_current_state.return_value
        state.source = {
            "plugin": "csv",
            "on_success": "continue",
            "options": {"blob_ref": "not-a-uuid"},
            "on_validation_failure": "quarantine",
        }

        blob_service = MagicMock()
        cast(Any, service)._blob_service = blob_service

        with pytest.raises(ValueError):
            await service.execute(session_id=uuid4())

        # The critical invariant: create_run() was never called,
        # so no stale pending run exists.
        mock_session_service.create_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_blob_ref_still_links_correctly(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Valid UUID blob_ref is parsed early and passed to link_blob_to_run."""
        session_id = uuid4()
        run_id = uuid4()
        blob_ref = str(uuid4())
        mock_session_service.create_run.return_value = MagicMock(id=run_id)

        blob_service = MagicMock()
        blob_service.link_blob_to_run = AsyncMock()
        # get_blob returns a record matching the executing session
        blob_service.get_blob = AsyncMock(return_value=MagicMock(session_id=session_id))
        cast(Any, service)._blob_service = blob_service

        state = mock_session_service.get_current_state.return_value
        state.source = {
            "plugin": "csv",
            "on_success": "continue",
            "options": {"blob_ref": blob_ref},
            "on_validation_failure": "quarantine",
        }

        with patch.object(service, "_run_pipeline"):
            await service.execute(session_id=session_id)

        blob_service.link_blob_to_run.assert_called_once_with(
            blob_id=UUID(blob_ref),
            run_id=run_id,
            direction="input",
        )


# ── Blob Ownership (Cross-Session IDOR) ──────────────────────────────


class TestBlobOwnership:
    """P2 defense-in-depth: blob_ref must belong to the executing session.

    Without this, a crafted composition state could reference another
    session's blob path — the shared-root path allowlist would pass it.
    """

    @pytest.mark.asyncio
    async def test_cross_session_blob_ref_rejected(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Blob belonging to a different session is rejected."""
        executing_session_id = uuid4()
        other_session_id = uuid4()
        blob_ref = str(uuid4())

        blob_service = MagicMock()
        # Blob belongs to other_session_id, not executing_session_id
        blob_service.get_blob = AsyncMock(return_value=MagicMock(session_id=other_session_id))
        cast(Any, service)._blob_service = blob_service

        state = mock_session_service.get_current_state.return_value
        state.source = {
            "plugin": "csv",
            "on_success": "continue",
            "options": {"blob_ref": blob_ref},
            "on_validation_failure": "quarantine",
        }

        with pytest.raises(ValueError, match="does not belong to session"):
            await service.execute(session_id=executing_session_id)

        # Critical: create_run was never called (rejected before run creation)
        mock_session_service.create_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_same_session_blob_ref_accepted(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """Blob belonging to the same session passes ownership check."""
        session_id = uuid4()
        blob_ref = str(uuid4())

        blob_service = MagicMock()
        blob_service.get_blob = AsyncMock(return_value=MagicMock(session_id=session_id))
        blob_service.link_blob_to_run = AsyncMock()
        cast(Any, service)._blob_service = blob_service

        state = mock_session_service.get_current_state.return_value
        state.source = {
            "plugin": "csv",
            "on_success": "continue",
            "options": {"blob_ref": blob_ref},
            "on_validation_failure": "quarantine",
        }

        with patch.object(service, "_run_pipeline"):
            run_id = await service.execute(session_id=session_id)
        assert isinstance(run_id, UUID)


# ── One Active Run (B6) ───────────────────────────────────────────────


class TestOneActiveRun:
    @pytest.mark.asyncio
    async def test_second_execute_raises_run_already_active(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """B6: Only one pending/running run per session."""
        session_id = uuid4()
        mock_session_service.get_active_run.return_value = MagicMock(status="running")

        with pytest.raises(RunAlreadyActiveError):
            await service.execute(session_id=session_id)

    @pytest.mark.asyncio
    async def test_execute_after_completed_run_succeeds(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """After a run completes, a new one can start."""
        mock_session_service.get_active_run.return_value = None
        with patch.object(service, "_run_pipeline"):
            run_id = await service.execute(session_id=uuid4())
        assert isinstance(run_id, UUID)


# ── EventBus Bridge ───────────────────────────────────────────────────


class TestEventBusBridge:
    """Verify that ProgressEvent from the Orchestrator's EventBus
    is translated to RunEvent and broadcast via the ProgressBroadcaster."""

    def test_progress_event_translated_to_run_event(self, service: ExecutionServiceImpl) -> None:
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


# ── B10: _call_async() Bridge Tests ──────────────────────────────────


class TestB8AsyncBridging:
    """B8/C1 fix: _call_async() bridges sync thread to async event loop.

    These tests need the REAL _call_async (not the test fixture's mock),
    so they construct a fresh service with a mock loop whose
    run_coroutine_threadsafe is controlled.
    """

    def test_call_async_returns_coroutine_result(
        self,
        broadcaster: ProgressBroadcaster,
        mock_settings: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """_call_async() schedules coroutine and returns its result."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        svc = ExecutionServiceImpl(
            loop=mock_loop,
            broadcaster=broadcaster,
            settings=mock_settings,
            session_service=mock_session_service,
            yaml_generator=MagicMock(),
        )
        mock_future = MagicMock()
        mock_future.result.return_value = "test_result"

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):

            async def dummy_coro() -> str:
                return "test_result"

            result = svc._call_async(dummy_coro())
        assert result == "test_result"
        mock_future.result.assert_called_once_with(timeout=30.0)

    def test_call_async_propagates_coroutine_exception(
        self,
        broadcaster: ProgressBroadcaster,
        mock_settings: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """If the coroutine raises, _call_async re-raises from future.result()."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        svc = ExecutionServiceImpl(
            loop=mock_loop,
            broadcaster=broadcaster,
            settings=mock_settings,
            session_service=mock_session_service,
            yaml_generator=MagicMock(),
        )
        mock_future = MagicMock()
        mock_future.result.side_effect = ValueError("db error")

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):

            async def failing_coro() -> None:
                raise ValueError("db error")

            with pytest.raises(ValueError, match="db error"):
                svc._call_async(failing_coro())

    def test_call_async_raises_timeout_error(
        self,
        broadcaster: ProgressBroadcaster,
        mock_settings: MagicMock,
        mock_session_service: MagicMock,
    ) -> None:
        """R6 fix: _call_async raises TimeoutError after 30s, preventing deadlock."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        svc = ExecutionServiceImpl(
            loop=mock_loop,
            broadcaster=broadcaster,
            settings=mock_settings,
            session_service=mock_session_service,
            yaml_generator=MagicMock(),
        )
        mock_future = MagicMock()
        mock_future.result.side_effect = concurrent.futures.TimeoutError()

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):

            async def hanging_coro() -> None:
                pass

            with pytest.raises(concurrent.futures.TimeoutError):
                svc._call_async(hanging_coro())


# ── W15: Running Status Failure Path ─────────────────────────────────


class TestRunningStatusFailure:
    """W15: What happens when the initial status update to 'running' fails."""

    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_running_status_failure_marks_run_failed(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
    ) -> None:
        """If update_run_status('running') fails, the except BaseException
        block attempts to set 'failed'. Run stays 'pending' if both fail."""
        # Make the first _call_async raise (simulating event loop issues)
        original_call_async = service._call_async
        call_count = 0

        def failing_call_async(coro: Coroutine[Any, Any, Any]) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First call = update to "running"
                raise ConnectionError("DB connection lost")
            return original_call_async(coro)

        cast(Any, service)._call_async = failing_call_async

        with pytest.raises(ConnectionError):
            service._run_pipeline(str(uuid4()), "yaml", threading.Event())

        # The except block tried to set "failed" via the second _call_async call
        assert call_count >= 2


# ── IDOR Protection: verify_run_ownership ─────────────────────────────


class TestVerifyRunOwnership:
    """IDOR protection — verify_run_ownership checks user_id + auth_provider.

    Criticality 9/10: This is the gate between "attacker can watch other
    users' pipeline progress via WebSocket" and "access denied."
    """

    @pytest.fixture
    def idor_service(
        self,
        mock_loop: MagicMock,
        broadcaster: ProgressBroadcaster,
    ) -> tuple[ExecutionServiceImpl, MagicMock]:
        """ExecutionServiceImpl with controllable session service."""
        session_svc = MagicMock()
        settings = MagicMock()
        settings.auth_provider = "local"
        settings.get_landscape_url.return_value = "sqlite:///test.db"
        settings.get_payload_store_path.return_value = Path("/tmp/test")

        svc = ExecutionServiceImpl(
            loop=mock_loop,
            broadcaster=broadcaster,
            settings=settings,
            session_service=session_svc,
            yaml_generator=MagicMock(),
        )
        return svc, session_svc

    @pytest.mark.asyncio
    async def test_owner_match_returns_true(self, idor_service) -> None:
        """Correct user + correct provider → access granted."""
        svc, session_svc = idor_service
        session_id = uuid4()
        run = MagicMock(session_id=session_id)
        session = MagicMock(user_id="alice", auth_provider_type="local")
        session_svc.get_run = AsyncMock(return_value=run)
        session_svc.get_session = AsyncMock(return_value=session)

        user = MagicMock(user_id="alice")
        assert await svc.verify_run_ownership(user, str(uuid4())) is True

    @pytest.mark.asyncio
    async def test_wrong_user_returns_false(self, idor_service) -> None:
        """Wrong user_id → access denied."""
        svc, session_svc = idor_service
        run = MagicMock(session_id=uuid4())
        session = MagicMock(user_id="alice", auth_provider_type="local")
        session_svc.get_run = AsyncMock(return_value=run)
        session_svc.get_session = AsyncMock(return_value=session)

        user = MagicMock(user_id="eve")
        assert await svc.verify_run_ownership(user, str(uuid4())) is False

    @pytest.mark.asyncio
    async def test_cross_provider_returns_false(self, idor_service) -> None:
        """Same user_id but different auth provider → access denied.

        This prevents "alice" in local auth from accessing runs belonging
        to "alice" in OIDC. Cross-provider user_id collision is the
        non-obvious IDOR vector.
        """
        svc, session_svc = idor_service
        run = MagicMock(session_id=uuid4())
        # Session was created under OIDC, but server is now configured for "local"
        session = MagicMock(user_id="alice", auth_provider_type="oidc")
        session_svc.get_run = AsyncMock(return_value=run)
        session_svc.get_session = AsyncMock(return_value=session)

        user = MagicMock(user_id="alice")
        assert await svc.verify_run_ownership(user, str(uuid4())) is False

    @pytest.mark.asyncio
    async def test_nonexistent_run_raises(self, idor_service) -> None:
        """Run not found → ValueError propagates (caller handles)."""
        svc, session_svc = idor_service
        session_svc.get_run = AsyncMock(side_effect=ValueError("Run not found"))

        user = MagicMock(user_id="alice")
        with pytest.raises(ValueError, match="Run not found"):
            await svc.verify_run_ownership(user, str(uuid4()))


# ── Sink Path Restriction ─────────────────────────────────────────────


class TestSinkPathRestriction:
    """P1 security fix: Sink output paths must be confined to allowed directories.

    Without this, a client can set sink options.path to an arbitrary absolute
    or ../ path and /execute will write there — turning the executor into an
    arbitrary file-write surface.
    """

    @pytest.mark.asyncio
    async def test_sink_path_outside_allowed_dirs_raises(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Sink with path pointing outside data_dir/outputs must be rejected."""
        mock_settings.data_dir = "/tmp/elspeth_data"
        state = mock_session_service.get_current_state.return_value
        state.source = None
        state.outputs = [
            {
                "name": "primary",
                "plugin": "csv",
                "options": {"path": "/etc/cron.d/backdoor.csv"},
                "on_write_failure": "discard",
            }
        ]
        state.nodes = None
        state.edges = None

        with pytest.raises(ValueError, match="resolves outside allowed output directories"):
            await service.execute(session_id=uuid4())

    @pytest.mark.asyncio
    async def test_sink_path_traversal_rejected(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Sink with ../ traversal in path must be rejected."""
        mock_settings.data_dir = "/tmp/elspeth_data"
        state = mock_session_service.get_current_state.return_value
        state.source = None
        state.outputs = [
            {
                "name": "results",
                "plugin": "json",
                "options": {"path": "/tmp/elspeth_data/outputs/../../etc/passwd"},
                "on_write_failure": "discard",
            }
        ]
        state.nodes = None
        state.edges = None

        with pytest.raises(ValueError, match="resolves outside allowed output directories"):
            await service.execute(session_id=uuid4())

    @pytest.mark.asyncio
    async def test_sink_path_under_outputs_accepted(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Sink with path under data_dir/outputs is allowed."""
        mock_settings.data_dir = "/tmp/elspeth_data"
        state = mock_session_service.get_current_state.return_value
        state.source = None
        state.outputs = [
            {
                "name": "primary",
                "plugin": "csv",
                "options": {"path": "/tmp/elspeth_data/outputs/result.csv"},
                "on_write_failure": "discard",
            }
        ]
        state.nodes = None
        state.edges = None

        with patch.object(service, "_run_pipeline"):
            run_id = await service.execute(session_id=uuid4())
        assert isinstance(run_id, UUID)

    @pytest.mark.asyncio
    async def test_sink_without_path_option_passes(
        self,
        service: ExecutionServiceImpl,
        mock_session_service: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Sink with no path/file options (e.g. database sink) passes check."""
        mock_settings.data_dir = "/tmp/elspeth_data"
        state = mock_session_service.get_current_state.return_value
        state.source = None
        state.outputs = [
            {
                "name": "db_sink",
                "plugin": "database",
                "options": {"connection_string": "sqlite:///out.db"},
                "on_write_failure": "discard",
            }
        ]
        state.nodes = None
        state.edges = None

        with patch.object(service, "_run_pipeline"):
            run_id = await service.execute(session_id=uuid4())
        assert isinstance(run_id, UUID)


# ── Edge Compatibility in _run_pipeline ───────────────────────────────


class TestEdgeCompatibility:
    """P2 fix: _run_pipeline must call validate_edge_compatibility() so that
    schema-incompatible pipelines are rejected before execution begins."""

    @patch("elspeth.web.execution.service.Orchestrator")
    @patch("elspeth.web.execution.service.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_validate_edge_compatibility_called(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        mock_orch_cls: MagicMock,
        service: ExecutionServiceImpl,
    ) -> None:
        """_run_pipeline must call graph.validate_edge_compatibility()
        after graph.validate() to catch schema mismatches."""
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
        mock_orch.run.return_value = MagicMock(run_id="r1")

        service._run_pipeline(str(uuid4()), "source:\n  plugin: csv", threading.Event())

        mock_graph.validate.assert_called_once()
        mock_graph.validate_edge_compatibility.assert_called_once()

    @patch("elspeth.web.execution.service.load_settings_from_yaml_string")
    @patch("elspeth.web.execution.service.instantiate_plugins_from_config")
    @patch("elspeth.web.execution.service.ExecutionGraph")
    @patch("elspeth.web.execution.service.LandscapeDB")
    @patch("elspeth.web.execution.service.FilesystemPayloadStore")
    def test_edge_compatibility_failure_crashes_pipeline(
        self,
        mock_payload: MagicMock,
        mock_landscape: MagicMock,
        mock_graph_cls: MagicMock,
        mock_instantiate: MagicMock,
        mock_load: MagicMock,
        service: ExecutionServiceImpl,
    ) -> None:
        """If edge compatibility fails, the pipeline must not execute."""
        from elspeth.core.dag.models import GraphValidationError

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
        mock_graph.validate_edge_compatibility.side_effect = GraphValidationError(
            "Schema mismatch: source outputs str but transform expects int"
        )

        with pytest.raises(GraphValidationError, match="Schema mismatch"):
            service._run_pipeline(str(uuid4()), "yaml", threading.Event())
