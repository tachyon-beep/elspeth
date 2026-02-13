# tests/unit/engine/orchestrator/test_graceful_shutdown.py
"""Unit tests for graceful shutdown contracts and signal handler context.

These tests don't need database access — they verify:
- GracefulShutdownError contract
- INTERRUPTED enum values
- Signal handler context manager (install/restore)
"""

from __future__ import annotations

import signal
import threading

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


class TestRunStatusInterrupted:
    """Tests for INTERRUPTED enum values."""

    def test_run_status_has_interrupted(self) -> None:
        assert RunStatus.INTERRUPTED == "interrupted"
        assert RunStatus.INTERRUPTED.value == "interrupted"

    def test_run_completion_status_has_interrupted(self) -> None:
        assert RunCompletionStatus.INTERRUPTED == "interrupted"
        assert RunCompletionStatus.INTERRUPTED.value == "interrupted"


class TestShutdownHandlerContext:
    """Tests for _shutdown_handler_context() signal handler management."""

    def test_handler_restores_original_signals(self) -> None:
        """After context exits, signal handlers are restored."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
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
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        try:
            orchestrator = Orchestrator(db=db)
            with orchestrator._shutdown_handler_context() as event:
                assert isinstance(event, threading.Event)
                assert not event.is_set()
        finally:
            db.close()

    def test_handler_sets_event_on_signal(self) -> None:
        """Signal handler sets the event when invoked."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        try:
            orchestrator = Orchestrator(db=db)
            with orchestrator._shutdown_handler_context() as event:
                assert not event.is_set()
                # Simulate signal by calling the handler directly
                handler = signal.getsignal(signal.SIGINT)
                handler(signal.SIGINT, None)  # type: ignore[operator]
                assert event.is_set()
        finally:
            db.close()

    def test_second_signal_restores_default_handler(self) -> None:
        """After first signal, SIGINT handler is restored to default (force-kill)."""
        from elspeth.core.landscape import LandscapeDB
        from elspeth.engine.orchestrator import Orchestrator

        db = LandscapeDB.in_memory()
        try:
            orchestrator = Orchestrator(db=db)
            with orchestrator._shutdown_handler_context():
                handler = signal.getsignal(signal.SIGINT)
                handler(signal.SIGINT, None)  # type: ignore[operator]

                # After first signal, SIGINT should now be default_int_handler
                assert signal.getsignal(signal.SIGINT) == signal.default_int_handler
        finally:
            db.close()
