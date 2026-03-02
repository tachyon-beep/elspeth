"""Regression tests for Phase 0 orchestrator fixes.

#6: Resume leaves RUNNING — when _process_resumed_rows raises a non-shutdown
    exception, the run must be finalized as FAILED (not left as RUNNING).

#7: Plugin cleanup skipped — when _build_processor raises after on_start
    completes, _cleanup_plugins must still be called.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from elspeth.contracts import RunStatus
from elspeth.core.landscape.database import LandscapeDB
from elspeth.engine.orchestrator.core import Orchestrator
from tests.fixtures.landscape import make_landscape_db


def _make_orchestrator(db: LandscapeDB | None = None) -> Orchestrator:
    """Create an Orchestrator with minimal dependencies."""
    if db is None:
        db = make_landscape_db()
    return Orchestrator(db)


class TestResumeFinalizesAsFailed:
    """Regression test for Phase 0 fix #6: Resume leaves RUNNING.

    Bug: If _process_resumed_rows raised a non-GracefulShutdownError
    exception during resume, the run status stayed as RUNNING permanently.
    This blocked future resume attempts since recovery rejects RUNNING status.

    Fix: Added `except Exception` handler in resume() that calls
    recorder.finalize_run(run_id, status=RunStatus.FAILED).
    """

    def test_resume_failure_finalizes_run_as_failed(self) -> None:
        """When _process_resumed_rows raises, run status becomes FAILED."""
        db = make_landscape_db()
        orch = _make_orchestrator(db)

        # Mock the checkpoint manager requirement
        orch._checkpoint_manager = MagicMock()

        # Create a mock resume_point
        resume_point = MagicMock()
        resume_point.checkpoint.run_id = "test-run-123"
        resume_point.aggregation_state = None
        resume_point.node_id = "node-1"

        # Create mock config and graph
        config = MagicMock()
        graph = MagicMock()
        payload_store = MagicMock()
        settings = MagicMock()

        # Mock recorder to capture finalize_run calls
        mock_recorder = MagicMock()
        mock_recorder.get_source_schema.return_value = '{"mode": "observed"}'
        mock_recorder.get_run_contract.return_value = MagicMock()

        # Mock RecoveryManager
        mock_recovery = MagicMock()
        mock_recovery.get_unprocessed_row_data.return_value = [
            ("row-1", 0, {"field": "value"}),
        ]

        # Make _process_resumed_rows raise a RuntimeError (non-shutdown)
        with (
            patch.object(orch, "_process_resumed_rows", side_effect=RuntimeError("test failure")),
            patch("elspeth.engine.orchestrator.core.LandscapeRecorder", return_value=mock_recorder),
            patch("elspeth.engine.orchestrator.core.reconstruct_schema_from_json", return_value=MagicMock()),
            patch("elspeth.core.checkpoint.RecoveryManager", return_value=mock_recovery),
            patch.object(orch, "_emit_telemetry"),
            pytest.raises(RuntimeError, match="test failure"),
        ):
            orch.resume(
                resume_point,
                config,
                graph,
                payload_store=payload_store,
                settings=settings,
            )

        # Verify finalize_run was called with FAILED status
        # finalize_run(run_id, status) — status can be positional or keyword
        finalize_calls = mock_recorder.finalize_run.call_args_list
        found_failed = False
        for call in finalize_calls:
            args, kwargs = call
            status = kwargs.get("status", args[1] if len(args) > 1 else None)
            if status == RunStatus.FAILED:
                found_failed = True
                break
        assert found_failed, (
            f"Run should be finalized as FAILED when resume fails with non-shutdown exception. finalize_run calls: {finalize_calls}"
        )


class TestBuildProcessorCallsCleanupOnFailure:
    """Regression test for Phase 0 fix #7: Plugin cleanup skipped.

    Bug: When _build_processor raised after on_start completed for all
    plugins, _cleanup_plugins was never called. This leaked resources
    (DB connections, file handles, thread pools).

    Fix: Wrapped _build_processor in try/except that calls
    _cleanup_plugins(config, ctx, include_source=True) on failure.
    """

    def test_source_code_has_cleanup_in_build_processor_except(self) -> None:
        """Verify the fix is in place: _build_processor failure triggers cleanup.

        This test inspects the source code to confirm the try/except pattern
        exists around _build_processor that calls _cleanup_plugins.
        The full run() path requires too many dependencies for a unit test,
        so we verify the fix structurally.
        """
        import ast
        import inspect

        source = inspect.getsource(Orchestrator)
        tree = ast.parse(source)

        # Find _execute_run method and look for the pattern:
        # try: _build_processor(...) except: _cleanup_plugins(...)
        found_pattern = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                # Check if the try body contains _build_processor call
                try_source = ast.dump(node)
                if "_build_processor" in try_source and "_cleanup_plugins" in try_source:
                    found_pattern = True
                    break

        assert found_pattern, (
            "Expected try/except around _build_processor that calls _cleanup_plugins. "
            "This pattern ensures plugin resources are cleaned up when processor "
            "construction fails after on_start has been called."
        )

    def test_cleanup_plugins_callable(self) -> None:
        """Sanity check: _cleanup_plugins method exists and is callable."""
        db = make_landscape_db()
        orch = _make_orchestrator(db)
        assert callable(orch._cleanup_plugins)


class TestCleanupPluginsReRaisesSystemExceptions:
    """Regression test: _cleanup_plugins must re-raise FrameworkBugError/AuditIntegrityError.

    Bug: All 6 except handlers in _cleanup_plugins caught Exception broadly
    and downgraded every error to a cleanup warning. FrameworkBugError and
    AuditIntegrityError indicate system-level corruption (Tier 1 violations)
    and must crash immediately, not be silently downgraded.

    Fix: record_cleanup_error() checks isinstance before logging and re-raises
    system-level exceptions.
    """

    def test_source_code_has_reraise_guard(self) -> None:
        """Verify record_cleanup_error re-raises FrameworkBugError/AuditIntegrityError.

        Structural test: inspect the source to confirm the isinstance check
        exists inside record_cleanup_error.
        """
        import ast
        import inspect
        import textwrap

        source = inspect.getsource(Orchestrator._cleanup_plugins)
        # Dedent because getsource preserves indentation from the class
        source = textwrap.dedent(source)
        tree = ast.parse(source)

        # Look for isinstance check with FrameworkBugError in the function
        source_text = source
        assert "FrameworkBugError" in source_text, "_cleanup_plugins must check for FrameworkBugError in record_cleanup_error"
        assert "AuditIntegrityError" in source_text, "_cleanup_plugins must check for AuditIntegrityError in record_cleanup_error"

        # Find a Raise inside an If that checks isinstance — the re-raise guard
        found_reraise = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if_source = ast.dump(node)
                if "isinstance" in if_source and "FrameworkBugError" in if_source:
                    # Check that the if body contains a raise
                    for child in ast.walk(node):
                        if isinstance(child, ast.Raise):
                            found_reraise = True
                            break

        assert found_reraise, (
            "Expected isinstance(error, (FrameworkBugError, AuditIntegrityError)) guard with raise inside record_cleanup_error"
        )

    def test_framework_bug_error_propagates_through_cleanup(self) -> None:
        """FrameworkBugError from plugin.on_complete() must propagate, not be swallowed."""
        from elspeth.contracts import FrameworkBugError
        from elspeth.contracts.plugin_context import PluginContext

        db = make_landscape_db()
        orch = _make_orchestrator(db)
        ctx = PluginContext(run_id="test", config={}, landscape=None)

        # Create a mock config with a transform that raises FrameworkBugError
        config = MagicMock()
        bad_transform = MagicMock()
        bad_transform.on_complete.side_effect = FrameworkBugError("internal corruption")
        bad_transform.name = "bad_transform"
        config.transforms = [bad_transform]
        config.sinks = {}
        config.source = MagicMock()

        with pytest.raises(FrameworkBugError, match="internal corruption"):
            orch._cleanup_plugins(config, ctx)

    def test_audit_integrity_error_propagates_through_cleanup(self) -> None:
        """AuditIntegrityError from sink.close() must propagate, not be swallowed."""
        from elspeth.contracts.errors import AuditIntegrityError
        from elspeth.contracts.plugin_context import PluginContext

        db = make_landscape_db()
        orch = _make_orchestrator(db)
        ctx = PluginContext(run_id="test", config={}, landscape=None)

        # Create a mock config with a sink that raises AuditIntegrityError on close
        config = MagicMock()
        config.transforms = []
        bad_sink = MagicMock()
        bad_sink.close.side_effect = AuditIntegrityError("audit DB corrupted")
        bad_sink.name = "bad_sink"
        config.sinks = {"output": bad_sink}
        config.source = MagicMock()

        with pytest.raises(AuditIntegrityError, match="audit DB corrupted"):
            orch._cleanup_plugins(config, ctx)

    def test_regular_exceptions_still_collected_as_cleanup_errors(self) -> None:
        """Non-system exceptions are still collected and reported as RuntimeError."""
        from elspeth.contracts.plugin_context import PluginContext

        db = make_landscape_db()
        orch = _make_orchestrator(db)
        ctx = PluginContext(run_id="test", config={}, landscape=None)

        # Create a mock config with a transform that raises a regular error
        config = MagicMock()
        bad_transform = MagicMock()
        bad_transform.on_complete.side_effect = RuntimeError("connection refused")
        bad_transform.name = "flaky_transform"
        config.transforms = [bad_transform]
        config.sinks = {}
        config.source = MagicMock()

        with pytest.raises(RuntimeError, match="Plugin cleanup failed"):
            orch._cleanup_plugins(config, ctx)
