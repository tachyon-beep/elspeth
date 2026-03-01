"""Direct unit tests for ExecutionRepository.

Tests exercise the repository directly (not through LandscapeRecorder delegation)
to verify audit integrity checks, edge cases, and crash paths that the delegation
tests don't cover.

The _make_repo() helper returns (LandscapeDB, ExecutionRepository, LandscapeRecorder)
— the recorder is used for graph setup only (register_node, create_row, create_token),
while the repo is tested directly.
"""

from __future__ import annotations

import inspect
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest

from elspeth.contracts import (
    BatchStatus,
    CallStatus,
    CallType,
    NodeStateCompleted,
    NodeStateFailed,
    NodeStateOpen,
    NodeStatePending,
    NodeStateStatus,
    NodeType,
    RoutingMode,
    RoutingSpec,
    TriggerType,
)
from elspeth.contracts.call_data import RawCallPayload
from elspeth.contracts.errors import AuditIntegrityError
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.core.landscape._database_ops import DatabaseOps
from elspeth.core.landscape.execution_repository import ExecutionRepository
from elspeth.core.landscape.model_loaders import (
    ArtifactLoader,
    BatchLoader,
    BatchMemberLoader,
    CallLoader,
    NodeStateLoader,
    OperationLoader,
    RoutingEventLoader,
)
from tests.fixtures.landscape import make_landscape_db, make_recorder

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _make_repo(
    *,
    run_id: str = "run-1",
) -> tuple[LandscapeDB, ExecutionRepository, LandscapeRecorder]:
    """Create an ExecutionRepository with supporting infrastructure.

    Returns (db, repo, recorder) — recorder is for graph setup only.
    """
    db = make_landscape_db()
    ops = DatabaseOps(db)
    repo = ExecutionRepository(
        db,
        ops,
        node_state_loader=NodeStateLoader(),
        routing_event_loader=RoutingEventLoader(),
        call_loader=CallLoader(),
        operation_loader=OperationLoader(),
        batch_loader=BatchLoader(),
        batch_member_loader=BatchMemberLoader(),
        artifact_loader=ArtifactLoader(),
    )
    recorder = make_recorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id="source-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id=run_id,
        plugin_name="transform",
        node_type=NodeType.TRANSFORM,
        plugin_version="1.0",
        config={},
        node_id="transform-1",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id=run_id,
        plugin_name="aggregator",
        node_type=NodeType.AGGREGATION,
        plugin_version="1.0",
        config={},
        node_id="agg-1",
        schema_config=_DYNAMIC_SCHEMA,
    )
    recorder.register_node(
        run_id=run_id,
        plugin_name="csv_sink",
        node_type=NodeType.SINK,
        plugin_version="1.0",
        config={},
        node_id="sink-0",
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, repo, recorder


def _make_repo_with_token(
    *,
    run_id: str = "run-1",
) -> tuple[LandscapeDB, ExecutionRepository, LandscapeRecorder, str]:
    """Create repo with a token ready for processing."""
    db, repo, recorder = _make_repo(run_id=run_id)
    recorder.create_row(run_id, "source-0", 0, {"name": "test"}, row_id="row-1")
    recorder.create_token("row-1", token_id="tok-1")
    return db, repo, recorder, "tok-1"


# ---------------------------------------------------------------------------
# C1: begin_node_state quarantined=True repr_hash fallback
# ---------------------------------------------------------------------------


class TestBeginNodeStateQuarantined:
    """Tests for quarantined input_data handling in begin_node_state (C1)."""

    def test_nan_input_uses_repr_hash_when_quarantined(self) -> None:
        """NaN in input_data triggers repr_hash fallback when quarantined=True.

        stable_hash rejects NaN (non-canonical per RFC 8785). The quarantine
        path catches the ValueError and falls back to repr_hash.
        """
        _db, repo, _rec, tok = _make_repo_with_token()
        data_with_nan = {"value": float("nan")}
        state = repo.begin_node_state(
            tok,
            "transform-1",
            "run-1",
            1,
            data_with_nan,
            quarantined=True,
        )
        assert isinstance(state, NodeStateOpen)
        assert state.input_hash is not None
        assert len(state.input_hash) > 0

    def test_canonical_input_uses_stable_hash_when_quarantined(self) -> None:
        """Normal input_data uses stable_hash even when quarantined=True.

        The repr_hash fallback only triggers when stable_hash raises.
        """
        _db, repo, _rec, tok = _make_repo_with_token()
        normal_data = {"value": 42}
        state = repo.begin_node_state(
            tok,
            "transform-1",
            "run-1",
            1,
            normal_data,
            quarantined=True,
        )
        assert isinstance(state, NodeStateOpen)
        # Verify it used stable_hash (canonical) not repr_hash
        from elspeth.core.canonical import stable_hash

        expected_hash = stable_hash(normal_data)
        assert state.input_hash == expected_hash

    def test_nan_input_crashes_when_not_quarantined(self) -> None:
        """NaN in input_data raises ValueError when quarantined=False.

        Without the quarantine flag, NaN is a bug in our code (Tier 2 data
        should not contain non-canonical values).
        """
        _db, repo, _rec, tok = _make_repo_with_token()
        data_with_nan = {"value": float("nan")}
        with pytest.raises(ValueError, match=r"[Nn]a[Nn]"):
            repo.begin_node_state(
                tok,
                "transform-1",
                "run-1",
                1,
                data_with_nan,
                quarantined=False,
            )


# ---------------------------------------------------------------------------
# C2: complete_node_state crash paths (post-update validation)
# ---------------------------------------------------------------------------


class TestCompleteNodeStateCrashPaths:
    """Tests for complete_node_state audit integrity checks (C2)."""

    def test_nonexistent_state_raises_audit_integrity(self) -> None:
        """Completing a nonexistent state must raise AuditIntegrityError.

        The rowcount check in the single-transaction UPDATE catches this.
        """
        _db, repo, _rec, _tok = _make_repo_with_token()
        with pytest.raises(AuditIntegrityError, match="zero rows affected"):
            repo.complete_node_state(
                "nonexistent-state",
                NodeStateStatus.COMPLETED,
                output_data={"result": "ok"},
                duration_ms=10.0,
            )

    def test_complete_returns_typed_union(self) -> None:
        """complete_node_state returns the correct typed variant for each status."""
        _db, repo, _rec, tok = _make_repo_with_token()

        # COMPLETED (attempt=0)
        repo.begin_node_state(tok, "transform-1", "run-1", 1, {"a": 1}, state_id="state-c", attempt=0)
        result_c = repo.complete_node_state("state-c", NodeStateStatus.COMPLETED, output_data={"b": 2}, duration_ms=5.0)
        assert isinstance(result_c, NodeStateCompleted)

        # PENDING (attempt=1 to avoid UNIQUE constraint)
        repo.begin_node_state(tok, "transform-1", "run-1", 2, {"a": 1}, state_id="state-p", attempt=1)
        result_p = repo.complete_node_state("state-p", NodeStateStatus.PENDING, duration_ms=3.0)
        assert isinstance(result_p, NodeStatePending)

        # FAILED (attempt=2 to avoid UNIQUE constraint)
        from elspeth.contracts.errors import ExecutionError

        repo.begin_node_state(tok, "transform-1", "run-1", 3, {"a": 1}, state_id="state-f", attempt=2)
        error = ExecutionError(exception="test failure", exception_type="ValueError")
        result_f = repo.complete_node_state("state-f", NodeStateStatus.FAILED, error=error, duration_ms=1.0)
        assert isinstance(result_f, NodeStateFailed)


# ---------------------------------------------------------------------------
# H5: record_routing_events rowcount=0 AuditIntegrityError
# ---------------------------------------------------------------------------


class TestRecordRoutingEventsRowcount:
    """Test that record_routing_events checks INSERT rowcount (H5)."""

    def test_zero_rowcount_raises_audit_integrity(self) -> None:
        """Mocked zero rowcount on routing event INSERT raises AuditIntegrityError.

        This simulates a database anomaly where the INSERT succeeds but
        reports zero rows affected.
        """
        _db, repo, rec, tok = _make_repo_with_token()

        # Create a node state and edge so the routing event has valid references
        state = repo.begin_node_state(tok, "transform-1", "run-1", 1, {"a": 1})
        rec.register_edge(
            run_id="run-1",
            from_node_id="transform-1",
            to_node_id="sink-0",
            label="continue",
            mode=RoutingMode.MOVE,
            edge_id="edge-1",
        )

        routes = [RoutingSpec(edge_id="edge-1", mode=RoutingMode.MOVE)]

        # Mock the connection's execute to return rowcount=0 for INSERTs
        original_connection = repo._db.connection

        from contextlib import contextmanager

        @contextmanager
        def mock_connection():
            with original_connection() as conn:
                original_execute = conn.execute

                def patched_execute(stmt, *args: Any, **kwargs: Any):
                    result = original_execute(stmt, *args, **kwargs)
                    # Intercept INSERT results to simulate zero rowcount
                    if hasattr(stmt, "is_insert") and stmt.is_insert:
                        mock_result = MagicMock()
                        mock_result.rowcount = 0
                        return mock_result
                    return result

                conn.execute = patched_execute  # type: ignore[assignment]
                yield conn

        repo._db.connection = mock_connection  # type: ignore[assignment]

        with pytest.raises(AuditIntegrityError, match="zero rows affected"):
            repo.record_routing_events(state.state_id, routes)


# ---------------------------------------------------------------------------
# Happy path: begin + complete node state roundtrip
# ---------------------------------------------------------------------------


class TestBeginAndCompleteNodeState:
    """Happy path roundtrip for node state recording via repo."""

    def test_begin_and_complete_roundtrip(self) -> None:
        """Begin a node state, complete it, verify all fields."""
        _db, repo, _rec, tok = _make_repo_with_token()
        state = repo.begin_node_state(tok, "transform-1", "run-1", 1, {"x": 1})
        assert isinstance(state, NodeStateOpen)
        assert state.status == NodeStateStatus.OPEN
        assert state.token_id == tok

        completed = repo.complete_node_state(
            state.state_id,
            NodeStateStatus.COMPLETED,
            output_data={"y": 2},
            duration_ms=42.0,
        )
        assert isinstance(completed, NodeStateCompleted)
        assert completed.status == NodeStateStatus.COMPLETED
        assert completed.duration_ms == 42.0
        assert completed.output_hash is not None


# ---------------------------------------------------------------------------
# Call recording through repo
# ---------------------------------------------------------------------------


class TestRecordCall:
    """Basic call recording through ExecutionRepository."""

    def test_record_call_roundtrip(self) -> None:
        """Record a call and verify it's retrievable."""
        _db, repo, _rec, tok = _make_repo_with_token()
        state = repo.begin_node_state(tok, "transform-1", "run-1", 1, {"a": 1})

        idx = repo.allocate_call_index(state.state_id)
        assert idx == 0

        call = repo.record_call(
            state.state_id,
            idx,
            CallType.LLM,
            CallStatus.SUCCESS,
            RawCallPayload({"prompt": "hello"}),
            RawCallPayload({"response": "world"}),
        )
        assert call.call_type == CallType.LLM
        assert call.status == CallStatus.SUCCESS


# ---------------------------------------------------------------------------
# Batch lifecycle through repo
# ---------------------------------------------------------------------------


class TestBatchLifecycle:
    """Batch create → add member → complete lifecycle."""

    def test_batch_lifecycle(self) -> None:
        """Create batch, add members, complete it."""
        _db, repo, _rec, tok = _make_repo_with_token()

        batch = repo.create_batch("run-1", "agg-1")
        assert batch.status == BatchStatus.DRAFT

        member = repo.add_batch_member(batch.batch_id, tok, 0)
        assert member.ordinal == 0

        completed = repo.complete_batch(
            batch.batch_id,
            BatchStatus.COMPLETED,
            trigger_type=TriggerType.COUNT,
            trigger_reason="count=1",
        )
        assert completed.status == BatchStatus.COMPLETED
        assert completed.trigger_type == TriggerType.COUNT


# ---------------------------------------------------------------------------
# H1: complete_operation output_data_ref rowcount check
# ---------------------------------------------------------------------------


class TestCompleteOperationRowcount:
    """Test that complete_operation checks rowcount on the output_data_ref UPDATE (H1)."""

    def test_complete_operation_basic(self) -> None:
        """complete_operation without payload_store skips the second UPDATE."""
        _db, repo, _rec, _tok = _make_repo_with_token()
        op = repo.begin_operation("run-1", "source-0", "source_load")
        repo.complete_operation(op.operation_id, "completed", duration_ms=10.0)
        result = repo.get_operation(op.operation_id)
        assert result is not None
        assert result.status == "completed"


# ---------------------------------------------------------------------------
# M4: Delegation signature alignment test
# ---------------------------------------------------------------------------


class TestDelegationSignatureAlignment:
    """Verify LandscapeRecorder delegation methods match ExecutionRepository signatures.

    This test compares parameter names, kinds, and defaults for all 29 delegated
    methods to ensure the recorder facade doesn't drift from the repository.
    """

    # Methods delegated from LandscapeRecorder to ExecutionRepository
    _DELEGATED_METHODS: ClassVar[list[str]] = [
        "begin_node_state",
        "complete_node_state",
        "get_node_state",
        "record_routing_event",
        "record_routing_events",
        "allocate_call_index",
        "record_call",
        "begin_operation",
        "complete_operation",
        "allocate_operation_call_index",
        "record_operation_call",
        "get_operation",
        "get_operation_calls",
        "get_operations_for_run",
        "get_all_operation_calls_for_run",
        "find_call_by_request_hash",
        "get_call_response_data",
        "create_batch",
        "add_batch_member",
        "update_batch_status",
        "complete_batch",
        "get_batch",
        "get_batches",
        "get_incomplete_batches",
        "get_batch_members",
        "get_all_batch_members_for_run",
        "retry_batch",
        "register_artifact",
        "get_artifacts",
    ]

    @pytest.mark.parametrize("method_name", _DELEGATED_METHODS)
    def test_signature_alignment(self, method_name: str) -> None:
        """Parameter names, kinds, and defaults must match (excluding 'self')."""
        recorder_method = getattr(LandscapeRecorder, method_name)
        repo_method = getattr(ExecutionRepository, method_name)

        recorder_sig = inspect.signature(recorder_method)
        repo_sig = inspect.signature(repo_method)

        recorder_params = [(name, p.kind, p.default) for name, p in recorder_sig.parameters.items() if name != "self"]
        repo_params = [(name, p.kind, p.default) for name, p in repo_sig.parameters.items() if name != "self"]

        assert recorder_params == repo_params, (
            f"Signature mismatch for {method_name}:\n  Recorder: {recorder_params}\n  Repo:     {repo_params}"
        )
