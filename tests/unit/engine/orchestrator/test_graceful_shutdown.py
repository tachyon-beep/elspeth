# tests/unit/engine/orchestrator/test_graceful_shutdown.py
"""Unit tests for graceful shutdown contracts and signal handler context.

These tests don't need database access — they verify:
- GracefulShutdownError contract
- INTERRUPTED enum values
- Signal handler context manager (install/restore)
"""

from __future__ import annotations

import logging
import signal
import threading
from unittest.mock import Mock, patch

import pytest

from elspeth.contracts import RunStatus
from elspeth.contracts.errors import GracefulShutdownError
from elspeth.contracts.events import RunCompletionStatus


class TestGracefulShutdownError:
    """Tests for GracefulShutdownError contract."""

    def test_error_attributes(self) -> None:
        """Error carries rows_processed and run_id."""
        err = GracefulShutdownError(rows_processed=42, run_id="run-abc")
        assert err.rows_processed == 42
        assert err.run_id == "run-abc"
        assert "42" in str(err)
        assert "run-abc" in str(err)

    def test_error_message_includes_resume_hint(self) -> None:
        """Error message includes resume command."""
        err = GracefulShutdownError(rows_processed=10, run_id="run-xyz")
        assert "elspeth resume run-xyz --execute" in str(err)

    def test_error_is_exception(self) -> None:
        """GracefulShutdownError is an Exception subclass."""
        err = GracefulShutdownError(rows_processed=0, run_id="run-0")
        assert isinstance(err, Exception)

    def test_error_carries_outcome_counters(self) -> None:
        """GracefulShutdownError carries real outcome counters for RunSummary.

        Regression: The graceful-shutdown handler hard-coded succeeded/failed/
        quarantined/routed to 0 in RunSummary because GracefulShutdownError
        only carried rows_processed. Now it must carry full counters.
        """
        err = GracefulShutdownError(
            rows_processed=100,
            run_id="run-abc",
            rows_succeeded=80,
            rows_failed=10,
            rows_quarantined=5,
            rows_routed=5,
            routed_destinations={"archive": 3, "review": 2},
        )
        assert err.rows_succeeded == 80
        assert err.rows_failed == 10
        assert err.rows_quarantined == 5
        assert err.rows_routed == 5
        assert err.routed_destinations == {"archive": 3, "review": 2}

    def test_error_counters_default_to_zero(self) -> None:
        """Backwards-compatible: omitting counters defaults to zero."""
        err = GracefulShutdownError(rows_processed=42, run_id="run-xyz")
        assert err.rows_succeeded == 0
        assert err.rows_failed == 0
        assert err.rows_quarantined == 0
        assert err.rows_routed == 0
        assert err.routed_destinations == {}


class TestRunStatusInterrupted:
    """Tests for INTERRUPTED enum values."""

    def test_run_status_has_interrupted(self) -> None:
        assert RunStatus.INTERRUPTED == RunStatus.INTERRUPTED
        assert RunStatus.INTERRUPTED.value == "interrupted"

    def test_run_completion_status_has_interrupted(self) -> None:
        assert RunCompletionStatus.INTERRUPTED == RunCompletionStatus.INTERRUPTED
        assert RunCompletionStatus.INTERRUPTED.value == "interrupted"


class TestShutdownHandlerContext:
    """Tests for _shutdown_handler_context() signal handler management."""

    def test_handler_restores_original_signals(self) -> None:
        """After context exits, signal handlers are restored."""
        from elspeth.engine.orchestrator import Orchestrator
        from tests.fixtures.landscape import make_landscape_db

        db = make_landscape_db()
        try:
            orchestrator = Orchestrator(db=db)

            original_sigint = signal.getsignal(signal.SIGINT)
            original_sigterm = signal.getsignal(signal.SIGTERM)

            with orchestrator._shutdown_handler_context() as event:
                # Inside: handlers should be different from original
                current_sigint = signal.getsignal(signal.SIGINT)
                assert current_sigint != original_sigint
                assert not event.is_set()

            # After: handlers should be restored
            assert signal.getsignal(signal.SIGINT) == original_sigint
            assert signal.getsignal(signal.SIGTERM) == original_sigterm
        finally:
            db.close()

    def test_context_yields_unset_event(self) -> None:
        """Context manager yields a threading.Event that starts unset."""
        from elspeth.engine.orchestrator import Orchestrator
        from tests.fixtures.landscape import make_landscape_db

        db = make_landscape_db()
        try:
            orchestrator = Orchestrator(db=db)
            with orchestrator._shutdown_handler_context() as event:
                assert isinstance(event, threading.Event)
                assert not event.is_set()
        finally:
            db.close()

    def test_handler_sets_event_on_signal(self) -> None:
        """Signal handler sets the event when invoked."""
        from elspeth.engine.orchestrator import Orchestrator
        from tests.fixtures.landscape import make_landscape_db

        db = make_landscape_db()
        try:
            orchestrator = Orchestrator(db=db)
            with orchestrator._shutdown_handler_context() as event:
                assert not event.is_set()
                # Simulate signal by calling the handler directly
                handler = signal.getsignal(signal.SIGINT)
                assert callable(handler)
                handler(signal.SIGINT, None)
                assert event.is_set()
        finally:
            db.close()

    def test_second_signal_restores_default_handler(self) -> None:
        """After first signal, SIGINT handler is restored to default (force-kill)."""
        from elspeth.engine.orchestrator import Orchestrator
        from tests.fixtures.landscape import make_landscape_db

        db = make_landscape_db()
        try:
            orchestrator = Orchestrator(db=db)
            with orchestrator._shutdown_handler_context():
                handler = signal.getsignal(signal.SIGINT)
                assert callable(handler)
                handler(signal.SIGINT, None)

                # After first signal, SIGINT should now be default_int_handler
                assert signal.getsignal(signal.SIGINT) == signal.default_int_handler
        finally:
            db.close()


class TestCheckpointInterruptedProgress:
    """Tests for _checkpoint_interrupted_progress warning when no checkpoint is possible."""

    def test_logs_warning_when_no_token_available(
        self,
        capsys: pytest.CaptureFixture[str],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Shutdown checkpoint skip must emit a structured warning, not silently return."""
        from elspeth.contracts.types import NodeID
        from elspeth.engine.orchestrator import Orchestrator
        from tests.fixtures.landscape import make_landscape_db

        db = make_landscape_db()
        try:
            orchestrator = Orchestrator(db=db)
            # Enable checkpointing so the method doesn't early-return on config check
            orchestrator._checkpoint_config = Mock()
            orchestrator._checkpoint_config.enabled = True
            orchestrator._checkpoint_manager = Mock()
            orchestrator._current_graph = Mock()
            orchestrator._sequence_number = 0

            # Build a LoopContext where all token resolution paths return None:
            # - no aggregation nodes
            # - no coalesce pending entries
            # - no pending sink tokens
            # - last_token_id is None
            mock_processor = Mock()
            mock_agg_state = Mock()
            mock_agg_state.nodes = {}  # Empty — no aggregation buffers
            mock_processor.get_aggregation_checkpoint_state.return_value = mock_agg_state
            mock_processor.get_coalesce_checkpoint_state.return_value = None

            loop_ctx = Mock()
            loop_ctx.processor = mock_processor
            loop_ctx.pending_tokens = {"default": []}  # No pending tokens
            loop_ctx.last_token_id = None

            with caplog.at_level(logging.WARNING):
                orchestrator._checkpoint_interrupted_progress(
                    run_id="run-test-123",
                    loop_ctx=loop_ctx,
                    sink_id_map={},
                    source_id=NodeID("source_0"),
                )

            # Verify NO checkpoint was created
            orchestrator._checkpoint_manager.create_checkpoint.assert_not_called()

            # Verify warning was emitted (structlog can route to stdout or stdlib)
            stdout_has_it = "shutdown_checkpoint_skipped" in capsys.readouterr().out
            caplog_has_it = any(
                "shutdown_checkpoint_skipped" in r.getMessage()
                for r in caplog.records
            )
            assert stdout_has_it or caplog_has_it, (
                "Expected 'shutdown_checkpoint_skipped' warning in log output"
            )
        finally:
            db.close()

    def test_creates_checkpoint_when_last_token_available(self) -> None:
        """When last_token_id is set, the fallback path creates a checkpoint."""
        from elspeth.contracts.types import NodeID
        from elspeth.engine.orchestrator import Orchestrator
        from tests.fixtures.landscape import make_landscape_db

        db = make_landscape_db()
        try:
            orchestrator = Orchestrator(db=db)
            orchestrator._checkpoint_config = Mock()
            orchestrator._checkpoint_config.enabled = True
            orchestrator._checkpoint_manager = Mock()
            orchestrator._current_graph = Mock()
            orchestrator._sequence_number = 0

            mock_processor = Mock()
            mock_agg_state = Mock()
            mock_agg_state.nodes = {}
            mock_processor.get_aggregation_checkpoint_state.return_value = mock_agg_state
            mock_processor.get_coalesce_checkpoint_state.return_value = None

            loop_ctx = Mock()
            loop_ctx.processor = mock_processor
            loop_ctx.pending_tokens = {"default": []}
            loop_ctx.last_token_id = "token-42"  # Has a last token

            source_id = NodeID("source_0")
            orchestrator._checkpoint_interrupted_progress(
                run_id="run-test-456",
                loop_ctx=loop_ctx,
                sink_id_map={},
                source_id=source_id,
            )

            # Checkpoint SHOULD have been created with the fallback token
            orchestrator._checkpoint_manager.create_checkpoint.assert_called_once()
            call_kwargs = orchestrator._checkpoint_manager.create_checkpoint.call_args
            assert call_kwargs.kwargs["token_id"] == "token-42"
            assert call_kwargs.kwargs["node_id"] == str(source_id)
        finally:
            db.close()
