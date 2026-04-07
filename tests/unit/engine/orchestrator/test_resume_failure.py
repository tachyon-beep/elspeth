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
from elspeth.contracts.schema_contract import SchemaContract
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.engine.orchestrator.core import Orchestrator
from elspeth.engine.orchestrator.types import GraphArtifacts, ResumeState
from elspeth.testing import make_field
from tests.fixtures.landscape import make_landscape_db, make_recorder_with_run


def _make_orchestrator(db: LandscapeDB | None = None) -> Orchestrator:
    """Create an Orchestrator with minimal dependencies."""
    if db is None:
        db = make_landscape_db()
    return Orchestrator(db)


def _make_contract() -> SchemaContract:
    """Create a simple test contract."""
    return SchemaContract(
        fields=(
            make_field(
                "value",
                python_type=str,
                original_name="value",
                required=True,
                source="declared",
            ),
        ),
        mode="FLEXIBLE",
        locked=True,
    )


class TestResumeFinalizesAsFailed:
    """Regression test for Phase 0 fix #6: Resume leaves RUNNING.

    Bug: If _process_resumed_rows raised a non-GracefulShutdownError
    exception during resume, the run status stayed as RUNNING permanently.
    This blocked future resume attempts since recovery rejects RUNNING status.

    Fix: Added `except Exception` handler in resume() that calls
    recorder.finalize_run(run_id, status=RunStatus.FAILED).
    """

    def test_resume_failure_persists_failed_status_to_db(self) -> None:
        """When _process_resumed_rows raises, FAILED status is persisted to the audit DB.

        Uses a real LandscapeDB and LandscapeRecorder to verify the Tier 1
        audit boundary: the FAILED state must actually be written to the
        database, not just called on a mock.
        """
        # Set up real DB with a run in RUNNING state
        setup = make_recorder_with_run(run_id="test-run-resume-fail")
        db = setup.db
        recorder = setup.recorder
        run_id = setup.run_id

        # Verify precondition: run is RUNNING
        run_before = recorder.get_run(run_id)
        assert run_before is not None
        assert run_before.status == RunStatus.RUNNING

        # Create orchestrator with the same DB
        orch = _make_orchestrator(db)
        orch._checkpoint_manager = MagicMock()

        # Create resume_point mock
        resume_point = MagicMock()
        resume_point.checkpoint.run_id = run_id
        resume_point.aggregation_state = None
        resume_point.coalesce_state = None
        resume_point.node_id = "node-1"
        resume_point.sequence_number = 0

        config = MagicMock()
        graph = MagicMock()
        payload_store = MagicMock()
        settings = MagicMock()

        # Build a ResumeState that uses the REAL recorder
        resume_state = ResumeState(
            recorder=recorder,
            run_id=run_id,
            restored_aggregation_state={},
            restored_coalesce_state=None,
            unprocessed_rows=[("row-1", 0, {"value": "test"})],
            schema_contract=_make_contract(),
        )

        # Mock _reconstruct_resume_state to return our real-recorder state,
        # and _process_resumed_rows to raise.
        with (
            patch.object(orch, "_reconstruct_resume_state", return_value=resume_state),
            patch.object(orch, "_process_resumed_rows", side_effect=RuntimeError("test failure")),
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

        # Verify: FAILED status is persisted in the actual database
        run_after = recorder.get_run(run_id)
        assert run_after is not None
        assert run_after.status == RunStatus.FAILED, (
            f"Run should be finalized as FAILED in the database when resume fails "
            f"with a non-shutdown exception. Actual status: {run_after.status}"
        )


class TestBuildProcessorCallsCleanupOnFailure:
    """Regression test for Phase 0 fix #7: Plugin cleanup skipped.

    Bug: When _build_processor raised after on_start completed for all
    plugins, _cleanup_plugins was never called. This leaked resources
    (DB connections, file handles, thread pools).

    Fix: Wrapped _build_processor in try/except that calls
    _cleanup_plugins(config, ctx, include_source=True) on failure.
    """

    def test_build_processor_failure_triggers_cleanup(self) -> None:
        """When _build_processor raises in _initialize_run_context, _cleanup_plugins is called.

        Behavioral test: mocks _build_processor to raise, calls
        _initialize_run_context, and verifies _cleanup_plugins is called
        before the exception propagates.
        """
        db = make_landscape_db()
        orch = _make_orchestrator(db)

        # Create minimal config with mock plugins
        config = MagicMock()
        config.source = MagicMock()
        config.source.name = "test_source"
        config.transforms = []
        config.sinks = {}
        config.config = {}
        config.aggregation_settings = None

        # Create minimal graph
        graph = MagicMock()
        graph.get_route_resolution_map.return_value = None

        # Create artifacts with the minimum required structure
        artifacts = GraphArtifacts(
            edge_map={},
            source_id="source_1",
            sink_id_map={},
            transform_id_map={},
            config_gate_id_map={},
            coalesce_id_map={},
        )

        recorder = MagicMock(spec=LandscapeRecorder)
        payload_store = MagicMock()

        with (
            patch.object(orch, "_build_processor", side_effect=RuntimeError("processor build failed")),
            patch.object(orch, "_cleanup_plugins") as mock_cleanup,
            patch.object(orch, "_assign_plugin_node_ids"),
            pytest.raises(RuntimeError, match="processor build failed"),
        ):
            orch._initialize_run_context(
                recorder,
                "test-run",
                config,
                graph,
                None,  # settings
                artifacts,
                None,  # batch_checkpoints
                payload_store,
            )

        # Verify _cleanup_plugins was called with the config
        mock_cleanup.assert_called_once()
        call_args = mock_cleanup.call_args
        assert call_args[0][0] is config  # first positional arg is config

    def test_cleanup_plugins_runs_full_lifecycle(self) -> None:
        """Verify _cleanup_plugins runs on_complete + close for all plugin types."""
        from elspeth.contracts.plugin_context import PluginContext

        db = make_landscape_db()
        orch = _make_orchestrator(db)
        ctx = PluginContext(run_id="test", config={}, landscape=None)

        config = MagicMock()
        tracked_transform = MagicMock()
        tracked_transform.name = "tracked"
        config.transforms = [tracked_transform]
        config.sinks = {}
        config.source = MagicMock()

        # Call _cleanup_plugins directly — verifies it runs the full
        # cleanup path (on_complete + close for transforms, close for source).
        orch._cleanup_plugins(config, ctx)

        tracked_transform.on_complete.assert_called_once()
        tracked_transform.close.assert_called_once()
        config.source.close.assert_called_once()


class TestCleanupPluginsReRaisesSystemExceptions:
    """Regression test: _cleanup_plugins must re-raise FrameworkBugError/AuditIntegrityError.

    Bug: All 6 except handlers in _cleanup_plugins caught Exception broadly
    and downgraded every error to a cleanup warning. FrameworkBugError and
    AuditIntegrityError indicate system-level corruption (Tier 1 violations)
    and must crash immediately, not be silently downgraded.

    Fix: record_cleanup_error() checks isinstance before logging and re-raises
    system-level exceptions.
    """

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
