# tests/unit/mcp/test_analyzer_queries.py
"""Tests for MCP analyzer query and diagnostic functions.

Priority coverage:
  1. explain_token — most complex, critical for debugging
  2. get_failure_context — 150+ lines, primary incident debugging tool
  3. get_run_summary — basic summary with real DB data

All tests use in-memory SQLite with pre-populated audit data via the
real RecorderFactory (no mocks for DB interaction).

Bug focus: nodes table has composite PK (node_id, run_id). Queries joining
through nodes must use BOTH keys to avoid cross-run contamination.

Bug found: dataclass_to_dict does not handle tuples, only lists.
LineageResult stores collections as tuples (tuple[RoutingEvent, ...], etc.),
so explain_token crashes with TypeError when iterating routing_events.
Tests for explain_token that hit this path are marked xfail.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from elspeth.contracts import (
    CallStatus,
    CallType,
    NodeStateStatus,
    NodeType,
    RoutingMode,
    RowOutcome,
    RunStatus,
)
from elspeth.contracts.audit import TokenRef
from elspeth.contracts.call_data import RawCallPayload
from elspeth.contracts.errors import AuditIntegrityError, ExecutionError, TransformErrorReason
from elspeth.core.landscape.lineage import explain
from elspeth.core.landscape.schema import nodes_table
from elspeth.mcp.analyzer import LandscapeAnalyzer
from elspeth.mcp.analyzers.diagnostics import get_failure_context
from elspeth.mcp.analyzers.queries import explain_token, list_runs
from elspeth.mcp.analyzers.reports import get_error_analysis, get_run_summary
from elspeth.mcp.types import ErrorResult
from tests.fixtures.landscape import (
    make_recorder_with_run,
    register_test_node,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_linear_pipeline(
    *,
    run_id: str = "run-1",
    source_node_id: str = "source-1",
    transform_node_id: str = "transform-1",
    sink_node_id: str = "sink-1",
    row_data: dict[str, Any] | None = None,
    complete_run: bool = True,
    complete_token: bool = True,
    fail_transform: bool = False,
) -> dict[str, Any]:
    """Build a simple source -> transform -> sink pipeline with one row.

    Returns a dict with db, factory, run_id, and all entity IDs.
    """
    setup = make_recorder_with_run(
        run_id=run_id,
        source_node_id=source_node_id,
    )
    db = setup.db
    factory = setup.factory

    # Register transform and sink nodes
    register_test_node(
        factory.data_flow,
        run_id,
        transform_node_id,
        node_type=NodeType.TRANSFORM,
        plugin_name="field_mapper",
    )
    register_test_node(
        factory.data_flow,
        run_id,
        sink_node_id,
        node_type=NodeType.SINK,
        plugin_name="csv_sink",
    )

    # Register edges
    edge_1 = factory.data_flow.register_edge(run_id, source_node_id, transform_node_id, "continue", RoutingMode.MOVE)
    edge_2 = factory.data_flow.register_edge(run_id, transform_node_id, sink_node_id, "on_success", RoutingMode.MOVE)

    # Create row and token
    data = row_data or {"name": "Alice", "amount": 100}
    row = factory.data_flow.create_row(run_id, source_node_id, row_index=0, data=data)
    token = factory.data_flow.create_token(row.row_id)

    # Process through transform
    ns = factory.execution.begin_node_state(token.token_id, transform_node_id, run_id, step_index=1, input_data=data)

    if fail_transform:
        factory.execution.complete_node_state(
            ns.state_id,
            NodeStateStatus.FAILED,
            duration_ms=50.0,
            error=ExecutionError(exception="deliberately failed", exception_type="TestFailure"),
        )
    else:
        factory.execution.complete_node_state(
            ns.state_id,
            NodeStateStatus.COMPLETED,
            output_data=data,
            duration_ms=50.0,
        )
        # Record routing event for the transform->sink edge
        factory.execution.record_routing_event(
            ns.state_id,
            edge_2.edge_id,
            RoutingMode.MOVE,
        )

    if complete_token:
        outcome = RowOutcome.FAILED if fail_transform else RowOutcome.COMPLETED
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id=run_id),
            outcome=outcome,
            sink_name=None if fail_transform else "csv_sink",
            error_hash="e" * 64 if fail_transform else None,
        )

    if complete_run:
        status = RunStatus.FAILED if fail_transform else RunStatus.COMPLETED
        factory.run_lifecycle.complete_run(run_id, status)

    return {
        "db": db,
        "factory": factory,
        "run_id": run_id,
        "source_node_id": source_node_id,
        "transform_node_id": transform_node_id,
        "sink_node_id": sink_node_id,
        "row": row,
        "token": token,
        "node_state": ns,
        "edge_1": edge_1,
        "edge_2": edge_2,
    }


# ===========================================================================
# explain_token tests — via underlying explain() function
# ===========================================================================


class TestExplainTokenLineage:
    """Tests for explain_token lineage via the underlying explain() function.

    The MCP explain_token() wrapper calls dataclass_to_dict() which has a bug:
    it does not convert tuples, only lists. Since LineageResult uses tuples
    for all collections, explain_token() crashes with TypeError on any result
    that has routing_events, node_states, etc.

    These tests exercise the underlying explain() to verify lineage correctness,
    and separately test explain_token() to document the conversion bug.
    """

    def test_explain_by_token_id_returns_lineage(self) -> None:
        """explain() returns LineageResult with correct token and source row."""
        p = _build_linear_pipeline()
        result = explain(p["factory"].query, p["factory"].data_flow, p["run_id"], token_id=p["token"].token_id)

        assert result is not None
        assert result.token.token_id == p["token"].token_id
        assert result.source_row.row_id == p["row"].row_id
        assert len(result.node_states) == 1
        assert result.node_states[0].status == NodeStateStatus.COMPLETED
        assert result.outcome is not None
        assert result.outcome.outcome == RowOutcome.COMPLETED

    def test_explain_by_row_id_resolves_token(self) -> None:
        """explain() resolves token from row_id when one terminal token exists."""
        p = _build_linear_pipeline()
        result = explain(p["factory"].query, p["factory"].data_flow, p["run_id"], row_id=p["row"].row_id)

        assert result is not None
        assert result.token.token_id == p["token"].token_id

    def test_explain_returns_none_for_nonexistent_token(self) -> None:
        """explain() returns None for a token_id that does not exist."""
        p = _build_linear_pipeline()
        result = explain(p["factory"].query, p["factory"].data_flow, p["run_id"], token_id="nonexistent-token")

        assert result is None

    def test_explain_returns_none_for_nonexistent_row(self) -> None:
        """explain() returns None for a row_id with no outcomes."""
        p = _build_linear_pipeline()
        result = explain(p["factory"].query, p["factory"].data_flow, p["run_id"], row_id="nonexistent-row")

        assert result is None

    def test_explain_includes_routing_events(self) -> None:
        """explain() includes routing events for the token."""
        p = _build_linear_pipeline()
        result = explain(p["factory"].query, p["factory"].data_flow, p["run_id"], token_id=p["token"].token_id)

        assert result is not None
        assert len(result.routing_events) == 1
        assert result.routing_events[0].mode == RoutingMode.MOVE

    def test_explain_includes_calls(self) -> None:
        """explain() includes external calls made during processing."""
        p = _build_linear_pipeline()
        state_id = p["node_state"].state_id

        call_index = p["factory"].execution.allocate_call_index(state_id)
        p["factory"].execution.record_call(
            state_id,
            call_index,
            CallType.LLM,
            CallStatus.SUCCESS,
            RawCallPayload({"prompt": "test"}),
            RawCallPayload({"response": "ok"}),
            latency_ms=100.0,
        )

        result = explain(p["factory"].query, p["factory"].data_flow, p["run_id"], token_id=p["token"].token_id)

        assert result is not None
        assert len(result.calls) == 1
        assert result.calls[0].call_type == CallType.LLM
        assert result.calls[0].latency_ms == 100.0

    def test_explain_includes_transform_errors(self) -> None:
        """explain() includes transform errors for the token."""
        setup = make_recorder_with_run(run_id="run-terr", source_node_id="src")
        factory, run_id = setup.factory, setup.run_id

        register_test_node(factory.data_flow, run_id, "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        row = factory.data_flow.create_row(run_id, "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)

        ns = factory.execution.begin_node_state(token.token_id, "xform", run_id, step_index=1, input_data={"x": 1})
        error_reason: TransformErrorReason = {"reason": "validation_failed", "message": "division by zero"}
        factory.execution.complete_node_state(ns.state_id, NodeStateStatus.FAILED, error=error_reason, duration_ms=5.0)

        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token.token_id, run_id=run_id),
            transform_id="xform",
            row_data={"x": 1},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id=run_id), outcome=RowOutcome.QUARANTINED, error_hash="b" * 64
        )
        factory.run_lifecycle.complete_run(run_id, RunStatus.FAILED)

        result = explain(factory.query, factory.data_flow, run_id, token_id=token.token_id)

        assert result is not None
        assert len(result.transform_errors) == 1
        assert result.transform_errors[0].transform_id == "xform"

    def test_explain_raises_for_neither_token_nor_row(self) -> None:
        """explain() raises ValueError when neither token_id nor row_id given."""
        p = _build_linear_pipeline()
        with pytest.raises(ValueError, match="Must provide either token_id or row_id"):
            explain(p["factory"].query, p["factory"].data_flow, p["run_id"])


class TestExplainTokenMCPWrapper:
    """Tests for the explain_token() MCP wrapper function.

    BUG: dataclass_to_dict() in formatters.py does not handle tuples.
    LineageResult uses tuple[RoutingEvent, ...], tuple[NodeState, ...], etc.
    When routing_events is non-empty, explain_token crashes with TypeError
    because it tries event["mode"] on a RoutingEvent dataclass (not a dict).
    """

    def test_explain_token_returns_none_for_nonexistent_token(self) -> None:
        """explain_token returns None when token does not exist (no conversion)."""
        p = _build_linear_pipeline()
        result = explain_token(p["db"], p["factory"], p["run_id"], token_id="nonexistent")

        assert result is None

    def test_explain_token_returns_none_for_nonexistent_row(self) -> None:
        """explain_token returns None when row has no outcomes."""
        p = _build_linear_pipeline()
        result = explain_token(p["db"], p["factory"], p["run_id"], row_id="nonexistent")

        assert result is None

    def test_explain_token_with_routing_events(self) -> None:
        """explain_token converts tuple[RoutingEvent, ...] to list of dicts."""
        p = _build_linear_pipeline()
        result = explain_token(p["db"], p["factory"], p["run_id"], token_id=p["token"].token_id)

        assert result is not None
        assert isinstance(result["routing_events"], list)

    def test_explain_token_works_without_routing_events(self) -> None:
        """explain_token succeeds when routing_events is empty (no conversion needed).

        With no routing events, the tuple is empty so the iteration in
        explain_token's for loop body is never reached, avoiding the crash.
        """
        # Build pipeline where transform fails (no routing event recorded)
        p = _build_linear_pipeline(run_id="no-route-run", fail_transform=True)
        result = explain_token(p["db"], p["factory"], "no-route-run", token_id=p["token"].token_id)

        assert result is not None
        assert result["divert_summary"] is None


# ===========================================================================
# get_failure_context tests
# ===========================================================================


class TestGetFailureContext:
    """Tests for get_failure_context -- the primary incident debugging tool."""

    def test_returns_error_for_nonexistent_run(self) -> None:
        """get_failure_context returns error dict for unknown run_id."""
        setup = make_recorder_with_run(run_id="existing-run")
        result = get_failure_context(setup.db, setup.factory, "nonexistent-run")

        assert "error" in result
        error_result = cast(ErrorResult, result)
        assert "not found" in error_result["error"]

    def test_empty_failure_context_for_clean_run(self) -> None:
        """get_failure_context returns empty lists when run has no failures."""
        p = _build_linear_pipeline(run_id="clean-run")
        result = get_failure_context(p["db"], p["factory"], "clean-run")

        assert "error" not in result
        assert result["run_id"] == "clean-run"
        assert result["run_status"] == "completed"
        assert result["failed_node_states"] == []
        assert result["transform_errors"] == []
        assert result["validation_errors"] == []
        assert result["patterns"]["failure_count"] == 0
        assert result["patterns"]["has_retries"] is False

    def test_failure_context_with_failed_node_states(self) -> None:
        """get_failure_context returns failed node states with plugin info."""
        p = _build_linear_pipeline(run_id="fail-run", fail_transform=True)
        result = get_failure_context(p["db"], p["factory"], "fail-run")

        assert "error" not in result
        assert result["run_status"] == "failed"
        assert len(result["failed_node_states"]) == 1

        failed = result["failed_node_states"][0]
        assert failed["token_id"] == p["token"].token_id
        assert failed["plugin"] == "field_mapper"
        assert failed["type"] == "transform"
        assert failed["attempt"] == 0

    def test_failure_context_with_transform_errors(self) -> None:
        """get_failure_context includes transform error details with plugin name."""
        setup = make_recorder_with_run(run_id="terr-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "terr-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="llm_classifier")

        row = factory.data_flow.create_row("terr-run", "src", row_index=0, data={"text": "hello"})
        token = factory.data_flow.create_token(row.row_id)

        ns = factory.execution.begin_node_state(token.token_id, "xform", "terr-run", step_index=1, input_data={"text": "hello"})
        error_reason: TransformErrorReason = {"reason": "llm_call_failed", "error": "timeout"}
        factory.execution.complete_node_state(ns.state_id, NodeStateStatus.FAILED, error=error_reason, duration_ms=5000.0)

        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token.token_id, run_id="terr-run"),
            transform_id="xform",
            row_data={"text": "hello"},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="terr-run"), outcome=RowOutcome.QUARANTINED, error_hash="c" * 64
        )
        factory.run_lifecycle.complete_run("terr-run", RunStatus.FAILED)

        result = get_failure_context(db, factory, "terr-run")

        assert "error" not in result
        assert len(result["transform_errors"]) == 1
        te = result["transform_errors"][0]
        assert te["plugin"] == "llm_classifier"
        assert te["details"] is not None
        assert te["details"]["reason"] == "llm_call_failed"
        assert result["patterns"]["transform_error_count"] == 1

    def test_failure_context_with_validation_errors(self) -> None:
        """get_failure_context includes validation errors with plugin name."""
        setup = make_recorder_with_run(run_id="verr-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        factory.data_flow.record_validation_error(
            "verr-run",
            "src",
            {"bad_field": None},
            "required field missing",
            "observed",
            "quarantine",
        )
        factory.run_lifecycle.complete_run("verr-run", RunStatus.COMPLETED)

        result = get_failure_context(db, factory, "verr-run")

        assert "error" not in result
        assert len(result["validation_errors"]) == 1
        ve = result["validation_errors"][0]
        assert ve["plugin"] == "source"
        assert ve["sample_data"] is not None
        assert result["patterns"]["validation_error_count"] == 1

    def test_failure_context_detects_retries(self) -> None:
        """get_failure_context sets has_retries=True when any attempt > 0."""
        setup = make_recorder_with_run(run_id="retry-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "retry-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="flaky")

        row = factory.data_flow.create_row("retry-run", "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)

        # Attempt 0: failed (initial)
        ns0 = factory.execution.begin_node_state(token.token_id, "xform", "retry-run", step_index=1, input_data={"x": 1}, attempt=0)
        factory.execution.complete_node_state(
            ns0.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )

        # Attempt 1: failed (first retry)
        ns1 = factory.execution.begin_node_state(token.token_id, "xform", "retry-run", step_index=1, input_data={"x": 1}, attempt=1)
        factory.execution.complete_node_state(
            ns1.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )

        # Attempt 2: failed (second retry — triggers has_retries detection)
        ns2 = factory.execution.begin_node_state(token.token_id, "xform", "retry-run", step_index=1, input_data={"x": 1}, attempt=2)
        factory.execution.complete_node_state(
            ns2.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )

        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="retry-run"), outcome=RowOutcome.FAILED, error_hash="d" * 64
        )
        factory.run_lifecycle.complete_run("retry-run", RunStatus.FAILED)

        result = get_failure_context(db, factory, "retry-run")

        assert "error" not in result
        assert len(result["failed_node_states"]) == 3  # FailureContextReport variant
        assert result["patterns"]["has_retries"] is True  # FailureContextReport variant
        assert result["patterns"]["failure_count"] == 3  # FailureContextReport variant

    def test_failure_context_detects_first_retry(self) -> None:
        """has_retries is True when only the first retry (attempt=1) exists."""
        setup = make_recorder_with_run(run_id="first-retry-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "first-retry-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="flaky")

        row = factory.data_flow.create_row("first-retry-run", "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)

        # Attempt 0: initial try
        ns0 = factory.execution.begin_node_state(token.token_id, "xform", "first-retry-run", step_index=1, input_data={"x": 1}, attempt=0)
        factory.execution.complete_node_state(
            ns0.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )

        # Attempt 1: first retry — this alone should trigger has_retries
        ns1 = factory.execution.begin_node_state(token.token_id, "xform", "first-retry-run", step_index=1, input_data={"x": 1}, attempt=1)
        factory.execution.complete_node_state(
            ns1.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )

        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="first-retry-run"), outcome=RowOutcome.FAILED, error_hash="e" * 64
        )
        factory.run_lifecycle.complete_run("first-retry-run", RunStatus.FAILED)

        result = get_failure_context(db, factory, "first-retry-run")

        assert result["patterns"]["has_retries"] is True  # type: ignore[typeddict-item]  # FailureContextReport variant

    def test_failure_context_has_retries_false_for_single_attempt(self) -> None:
        """has_retries is False when all failures are attempt 0 (no retries)."""
        p = _build_linear_pipeline(run_id="no-retry-run", fail_transform=True)
        result = get_failure_context(p["db"], p["factory"], "no-retry-run")

        assert "error" not in result
        assert result["patterns"]["has_retries"] is False

    def test_failure_context_uses_composite_key_for_nodes_join(self) -> None:
        """Verify get_failure_context joins nodes with BOTH (node_id, run_id).

        This is the critical composite PK test. We create two runs in the
        same DB with the same node_id but different plugin_names. If the
        join only uses node_id, the plugin_name could come from the wrong run.
        """
        # Create a shared DB with two runs
        setup = make_recorder_with_run(run_id="run-X", source_node_id="src")
        db, factory = setup.db, setup.factory

        # Run X: xform is "llm_classifier"
        register_test_node(factory.data_flow, "run-X", "xform", node_type=NodeType.TRANSFORM, plugin_name="llm_classifier")

        row_x = factory.data_flow.create_row("run-X", "src", row_index=0, data={"x": 1})
        token_x = factory.data_flow.create_token(row_x.row_id)

        ns_x = factory.execution.begin_node_state(token_x.token_id, "xform", "run-X", step_index=1, input_data={"x": 1})
        factory.execution.complete_node_state(
            ns_x.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token_x.token_id, run_id="run-X"), outcome=RowOutcome.FAILED, error_hash="e" * 64
        )
        factory.run_lifecycle.complete_run("run-X", RunStatus.FAILED)

        # Run Y: same node_id "xform" but different plugin "field_mapper"
        factory.run_lifecycle.begin_run(config={}, canonical_version="v1", run_id="run-Y")
        register_test_node(factory.data_flow, "run-Y", "src", node_type=NodeType.SOURCE, plugin_name="source")
        register_test_node(factory.data_flow, "run-Y", "xform", node_type=NodeType.TRANSFORM, plugin_name="field_mapper")

        row_y = factory.data_flow.create_row("run-Y", "src", row_index=0, data={"y": 2})
        token_y = factory.data_flow.create_token(row_y.row_id)

        ns_y = factory.execution.begin_node_state(token_y.token_id, "xform", "run-Y", step_index=1, input_data={"y": 2})
        factory.execution.complete_node_state(
            ns_y.state_id,
            NodeStateStatus.FAILED,
            duration_ms=20.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token_y.token_id, run_id="run-Y"), outcome=RowOutcome.FAILED, error_hash="f" * 64
        )
        factory.run_lifecycle.complete_run("run-Y", RunStatus.FAILED)

        # Query run-X failure context
        result_x = get_failure_context(db, factory, "run-X")
        assert "error" not in result_x
        assert len(result_x["failed_node_states"]) == 1
        # The plugin name MUST be from run-X, not run-Y
        assert result_x["failed_node_states"][0]["plugin"] == "llm_classifier"

        # Query run-Y failure context
        result_y = get_failure_context(db, factory, "run-Y")
        assert "error" not in result_y
        assert len(result_y["failed_node_states"]) == 1
        assert result_y["failed_node_states"][0]["plugin"] == "field_mapper"

    def test_failure_context_composite_key_transform_errors(self) -> None:
        """Verify transform_errors join uses composite key (node_id, run_id).

        Same setup as composite key test for node_states, but verifying
        the transform_errors -> nodes outerjoin uses both keys.
        """
        setup = make_recorder_with_run(run_id="run-P", source_node_id="src")
        db, factory = setup.db, setup.factory

        # Run P: xform is "slow_transform"
        register_test_node(factory.data_flow, "run-P", "xform", node_type=NodeType.TRANSFORM, plugin_name="slow_transform")
        row_p = factory.data_flow.create_row("run-P", "src", row_index=0, data={"p": 1})
        token_p = factory.data_flow.create_token(row_p.row_id)
        error_reason: TransformErrorReason = {"reason": "retry_timeout"}
        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token_p.token_id, run_id="run-P"),
            transform_id="xform",
            row_data={"p": 1},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token_p.token_id, run_id="run-P"), outcome=RowOutcome.QUARANTINED, error_hash="a" * 64
        )
        factory.run_lifecycle.complete_run("run-P", RunStatus.FAILED)

        # Run Q: same node_id "xform" but "fast_transform"
        factory.run_lifecycle.begin_run(config={}, canonical_version="v1", run_id="run-Q")
        register_test_node(factory.data_flow, "run-Q", "src", node_type=NodeType.SOURCE, plugin_name="source")
        register_test_node(factory.data_flow, "run-Q", "xform", node_type=NodeType.TRANSFORM, plugin_name="fast_transform")
        row_q = factory.data_flow.create_row("run-Q", "src", row_index=0, data={"q": 2})
        token_q = factory.data_flow.create_token(row_q.row_id)
        error_reason_q: TransformErrorReason = {"reason": "invalid_input"}
        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token_q.token_id, run_id="run-Q"),
            transform_id="xform",
            row_data={"q": 2},
            error_details=error_reason_q,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token_q.token_id, run_id="run-Q"), outcome=RowOutcome.QUARANTINED, error_hash="b" * 64
        )
        factory.run_lifecycle.complete_run("run-Q", RunStatus.FAILED)

        result_p = get_failure_context(db, factory, "run-P")
        assert len(result_p["transform_errors"]) == 1  # type: ignore[typeddict-item]  # FailureContextReport variant
        assert result_p["transform_errors"][0]["plugin"] == "slow_transform"  # type: ignore[typeddict-item]  # FailureContextReport variant

        result_q = get_failure_context(db, factory, "run-Q")
        assert len(result_q["transform_errors"]) == 1  # type: ignore[typeddict-item]  # FailureContextReport variant
        assert result_q["transform_errors"][0]["plugin"] == "fast_transform"  # type: ignore[typeddict-item]  # FailureContextReport variant

    def test_failure_context_limit_parameter(self) -> None:
        """get_failure_context respects the limit parameter."""
        setup = make_recorder_with_run(run_id="limit-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "limit-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        # Create 5 rows, all failing
        for i in range(5):
            row = factory.data_flow.create_row("limit-run", "src", row_index=i, data={"i": i})
            token = factory.data_flow.create_token(row.row_id)
            ns = factory.execution.begin_node_state(token.token_id, "xform", "limit-run", step_index=1, input_data={"i": i})
            factory.execution.complete_node_state(
                ns.state_id,
                NodeStateStatus.FAILED,
                duration_ms=10.0,
                error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
            )
            factory.data_flow.record_token_outcome(
                ref=TokenRef(token_id=token.token_id, run_id="limit-run"), outcome=RowOutcome.FAILED, error_hash="a" * 64
            )

        factory.run_lifecycle.complete_run("limit-run", RunStatus.FAILED)

        result = get_failure_context(db, factory, "limit-run", limit=2)

        assert "error" not in result
        assert len(result["failed_node_states"]) == 2
        assert result["patterns"]["failure_count"] == 2

    def test_failure_context_plugins_failing_pattern(self) -> None:
        """get_failure_context identifies which plugins are failing."""
        setup = make_recorder_with_run(run_id="pattern-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "pattern-run", "xform-a", node_type=NodeType.TRANSFORM, plugin_name="mapper")
        register_test_node(factory.data_flow, "pattern-run", "xform-b", node_type=NodeType.TRANSFORM, plugin_name="classifier")

        # Fail in xform-a
        row0 = factory.data_flow.create_row("pattern-run", "src", row_index=0, data={"i": 0})
        token0 = factory.data_flow.create_token(row0.row_id)
        ns0 = factory.execution.begin_node_state(token0.token_id, "xform-a", "pattern-run", step_index=1, input_data={"i": 0})
        factory.execution.complete_node_state(
            ns0.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token0.token_id, run_id="pattern-run"), outcome=RowOutcome.FAILED, error_hash="a" * 64
        )

        # Fail in xform-b
        row1 = factory.data_flow.create_row("pattern-run", "src", row_index=1, data={"i": 1})
        token1 = factory.data_flow.create_token(row1.row_id)
        ns1 = factory.execution.begin_node_state(token1.token_id, "xform-b", "pattern-run", step_index=2, input_data={"i": 1})
        factory.execution.complete_node_state(
            ns1.state_id,
            NodeStateStatus.FAILED,
            duration_ms=10.0,
            error=ExecutionError(exception="test_failure", exception_type="TestFailure"),
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token1.token_id, run_id="pattern-run"), outcome=RowOutcome.FAILED, error_hash="b" * 64
        )

        factory.run_lifecycle.complete_run("pattern-run", RunStatus.FAILED)

        result = get_failure_context(db, factory, "pattern-run")

        assert "error" not in result
        assert result["patterns"]["failure_count"] == 2
        plugins = sorted(result["patterns"]["plugins_failing"])
        assert plugins == ["classifier", "mapper"]


# ===========================================================================
# get_run_summary tests
# ===========================================================================


class TestGetRunSummary:
    """Tests for get_run_summary -- summary statistics for a run."""

    def test_summary_for_completed_run(self) -> None:
        """get_run_summary returns correct counts for a completed run."""
        p = _build_linear_pipeline(run_id="summary-run")
        result = get_run_summary(p["db"], p["factory"], "summary-run")

        assert "error" not in result
        assert result["run_id"] == "summary-run"
        assert result["status"] == "completed"
        assert result["counts"]["rows"] == 1
        assert result["counts"]["tokens"] == 1
        assert result["counts"]["nodes"] == 3  # source + transform + sink
        assert result["counts"]["node_states"] == 1
        assert result["errors"]["validation"] == 0
        assert result["errors"]["transform"] == 0
        assert result["errors"]["total"] == 0
        assert result["outcome_distribution"]["completed"] == 1

    def test_summary_for_nonexistent_run(self) -> None:
        """get_run_summary returns error for unknown run_id."""
        setup = make_recorder_with_run()
        result = get_run_summary(setup.db, setup.factory, "nonexistent")

        assert "error" in result

    def test_summary_counts_errors_correctly(self) -> None:
        """get_run_summary counts both validation and transform errors."""
        setup = make_recorder_with_run(run_id="err-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "err-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        # Record a validation error
        factory.data_flow.record_validation_error("err-run", "src", {"bad": "data"}, "missing field", "observed", "quarantine")

        # Record a transform error
        row = factory.data_flow.create_row("err-run", "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)
        error_reason: TransformErrorReason = {"reason": "api_error"}
        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token.token_id, run_id="err-run"),
            transform_id="xform",
            row_data={"x": 1},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="err-run"), outcome=RowOutcome.QUARANTINED, error_hash="a" * 64
        )
        factory.run_lifecycle.complete_run("err-run", RunStatus.COMPLETED)

        result = get_run_summary(db, factory, "err-run")

        assert "error" not in result
        assert result["errors"]["validation"] == 1
        assert result["errors"]["transform"] == 1
        assert result["errors"]["total"] == 2

    def test_summary_outcome_distribution(self) -> None:
        """get_run_summary returns correct outcome distribution for mixed outcomes."""
        setup = make_recorder_with_run(run_id="dist-run", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "dist-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")
        register_test_node(factory.data_flow, "dist-run", "sink", node_type=NodeType.SINK, plugin_name="csv_sink")

        # Row 0: completed
        row0 = factory.data_flow.create_row("dist-run", "src", row_index=0, data={"i": 0})
        token0 = factory.data_flow.create_token(row0.row_id)
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token0.token_id, run_id="dist-run"), outcome=RowOutcome.COMPLETED, sink_name="csv_sink"
        )

        # Row 1: quarantined
        row1 = factory.data_flow.create_row("dist-run", "src", row_index=1, data={"i": 1})
        token1 = factory.data_flow.create_token(row1.row_id)
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token1.token_id, run_id="dist-run"), outcome=RowOutcome.QUARANTINED, error_hash="b" * 64
        )

        # Row 2: completed
        row2 = factory.data_flow.create_row("dist-run", "src", row_index=2, data={"i": 2})
        token2 = factory.data_flow.create_token(row2.row_id)
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token2.token_id, run_id="dist-run"), outcome=RowOutcome.COMPLETED, sink_name="csv_sink"
        )

        factory.run_lifecycle.complete_run("dist-run", RunStatus.COMPLETED)

        result = get_run_summary(db, factory, "dist-run")

        assert "error" not in result
        assert result["outcome_distribution"]["completed"] == 2
        assert result["outcome_distribution"]["quarantined"] == 1

    def test_summary_avg_state_duration(self) -> None:
        """get_run_summary returns average node state duration."""
        p = _build_linear_pipeline(run_id="dur-run")
        result = get_run_summary(p["db"], p["factory"], "dur-run")

        assert "error" not in result
        # Pipeline has one node state with duration_ms=50.0
        assert result["avg_state_duration_ms"] == 50.0


# ===========================================================================
# list_runs tests (basic query coverage)
# ===========================================================================


class TestListRuns:
    """Tests for list_runs -- basic run listing."""

    def test_list_runs_returns_all(self) -> None:
        """list_runs returns runs in the database."""
        setup = make_recorder_with_run(run_id="list-run-1")
        factory = setup.factory
        factory.run_lifecycle.complete_run("list-run-1", RunStatus.COMPLETED)

        result = list_runs(setup.db, factory)

        assert len(result) == 1
        assert result[0]["run_id"] == "list-run-1"
        assert result[0]["status"] == "completed"

    def test_list_runs_filters_by_status(self) -> None:
        """list_runs filters by status when provided."""
        setup = make_recorder_with_run(run_id="filter-run")
        factory = setup.factory
        factory.run_lifecycle.complete_run("filter-run", RunStatus.FAILED)

        # Should find it with "failed" filter
        result = list_runs(setup.db, factory, status="failed")
        assert len(result) == 1

        # Should not find it with "completed" filter
        result = list_runs(setup.db, factory, status="completed")
        assert len(result) == 0

    def test_list_runs_invalid_status_raises(self) -> None:
        """list_runs raises ValueError for invalid status."""
        setup = make_recorder_with_run()

        with pytest.raises(ValueError, match="Invalid status"):
            list_runs(setup.db, setup.factory, status="bogus")


# ===========================================================================
# Tier 1 corruption guard tests
# ===========================================================================


def _delete_node(db: Any, run_id: str, node_id: str) -> None:
    """Directly delete a node row to simulate Tier 1 audit corruption.

    Disables FK enforcement temporarily — real corruption doesn't follow FK rules.
    """
    from sqlalchemy import text

    with db.connection() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        conn.execute(nodes_table.delete().where((nodes_table.c.node_id == node_id) & (nodes_table.c.run_id == run_id)))
        conn.execute(text("PRAGMA foreign_keys = ON"))


class TestFailureContextCorruptionGuards:
    """Tier 1 corruption guards in get_failure_context.

    These tests simulate audit database corruption by deleting node rows
    after creating valid pipeline data. The analyzer must raise
    AuditIntegrityError instead of silently producing degraded reports.

    Bugs: elspeth-2da5ab21dc, elspeth-b3556eb237
    """

    def test_missing_node_for_failed_state_raises(self) -> None:
        """Failed node_state referencing a deleted node must raise, not silently drop."""
        p = _build_linear_pipeline(run_id="corrupt-ns", fail_transform=True)
        _delete_node(p["db"], "corrupt-ns", p["transform_node_id"])

        with pytest.raises(AuditIntegrityError, match=r"Tier-1 corruption.*node_states"):
            get_failure_context(p["db"], p["factory"], "corrupt-ns")

    def test_missing_node_for_transform_error_raises(self) -> None:
        """Transform error referencing a deleted node must raise, not emit plugin=None."""
        setup = make_recorder_with_run(run_id="corrupt-te", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "corrupt-te", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        row = factory.data_flow.create_row("corrupt-te", "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)
        error_reason: TransformErrorReason = {"reason": "test_error"}
        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token.token_id, run_id="corrupt-te"),
            transform_id="xform",
            row_data={"x": 1},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="corrupt-te"), outcome=RowOutcome.QUARANTINED, error_hash="a" * 64
        )
        factory.run_lifecycle.complete_run("corrupt-te", RunStatus.FAILED)

        _delete_node(db, "corrupt-te", "xform")

        with pytest.raises(AuditIntegrityError, match=r"Tier-1 corruption.*transform_errors"):
            get_failure_context(db, factory, "corrupt-te")

    def test_missing_node_for_validation_error_raises(self) -> None:
        """Validation error with node_id but deleted node must raise."""
        setup = make_recorder_with_run(run_id="corrupt-ve", source_node_id="src")
        db, factory = setup.db, setup.factory

        factory.data_flow.record_validation_error("corrupt-ve", "src", {"bad": "data"}, "missing field", "observed", "quarantine")
        factory.run_lifecycle.complete_run("corrupt-ve", RunStatus.COMPLETED)

        _delete_node(db, "corrupt-ve", "src")

        with pytest.raises(AuditIntegrityError, match=r"Tier-1 corruption.*validation_errors"):
            get_failure_context(db, factory, "corrupt-ve")

    def test_clean_run_still_works(self) -> None:
        """Corruption guards don't break normal operation."""
        p = _build_linear_pipeline(run_id="clean-guard", fail_transform=True)
        result = get_failure_context(p["db"], p["factory"], "clean-guard")

        assert "error" not in result
        assert result["patterns"]["failure_count"] == 1
        assert result["failed_node_states"][0]["plugin"] == "field_mapper"


class TestErrorAnalysisCorruptionGuard:
    """Tier 1 corruption guard in get_error_analysis.

    Bug: elspeth-71f25623b2
    """

    def test_missing_node_for_transform_error_raises(self) -> None:
        """Transform error grouped with plugin=None must raise, not emit None bucket."""
        setup = make_recorder_with_run(run_id="corrupt-ea", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "corrupt-ea", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        row = factory.data_flow.create_row("corrupt-ea", "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)
        error_reason: TransformErrorReason = {"reason": "test_error"}
        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token.token_id, run_id="corrupt-ea"),
            transform_id="xform",
            row_data={"x": 1},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="corrupt-ea"), outcome=RowOutcome.QUARANTINED, error_hash="a" * 64
        )
        factory.run_lifecycle.complete_run("corrupt-ea", RunStatus.FAILED)

        _delete_node(db, "corrupt-ea", "xform")

        with pytest.raises(AuditIntegrityError, match=r"Tier-1 corruption.*transform_errors"):
            get_error_analysis(db, factory, "corrupt-ea")

    def test_clean_error_analysis_still_works(self) -> None:
        """Corruption guard doesn't break normal error analysis."""
        setup = make_recorder_with_run(run_id="clean-ea", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "clean-ea", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        row = factory.data_flow.create_row("clean-ea", "src", row_index=0, data={"x": 1})
        token = factory.data_flow.create_token(row.row_id)
        error_reason: TransformErrorReason = {"reason": "test_error"}
        factory.data_flow.record_transform_error(
            ref=TokenRef(token_id=token.token_id, run_id="clean-ea"),
            transform_id="xform",
            row_data={"x": 1},
            error_details=error_reason,
            destination="quarantine",
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token.token_id, run_id="clean-ea"), outcome=RowOutcome.QUARANTINED, error_hash="a" * 64
        )
        factory.run_lifecycle.complete_run("clean-ea", RunStatus.FAILED)

        result = get_error_analysis(db, factory, "clean-ea")

        assert "error" not in result
        assert result["transform_errors"]["total"] == 1
        assert result["transform_errors"]["by_transform"][0]["transform_plugin"] == "mapper"


class TestExplainTokenErrorHandling:
    """LandscapeAnalyzer.explain_token input validation and error handling.

    Bug: elspeth-4e410d1fbf
    """

    def test_neither_token_nor_row_returns_error(self) -> None:
        """explain_token returns ErrorResult when neither token_id nor row_id given."""
        setup = make_recorder_with_run(run_id="et-err")
        factory = setup.factory
        factory.run_lifecycle.complete_run("et-err", RunStatus.COMPLETED)

        # Use the analyzer facade directly (not the underlying function)
        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = setup.db
        analyzer._factory = factory

        result = analyzer.explain_token("et-err")

        assert "error" in result
        error_result = cast(ErrorResult, result)
        assert "Must provide either token_id or row_id" in error_result["error"]

    def test_ambiguous_row_returns_error(self) -> None:
        """explain_token returns ErrorResult for row with multiple terminal tokens."""
        setup = make_recorder_with_run(run_id="et-ambig", source_node_id="src")
        db, factory = setup.db, setup.factory

        register_test_node(factory.data_flow, "et-ambig", "sink-a", node_type=NodeType.SINK, plugin_name="sink_a")
        register_test_node(factory.data_flow, "et-ambig", "sink-b", node_type=NodeType.SINK, plugin_name="sink_b")

        row = factory.data_flow.create_row("et-ambig", "src", row_index=0, data={"x": 1})
        token_a = factory.data_flow.create_token(row.row_id)
        token_b = factory.data_flow.create_token(row.row_id)
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token_a.token_id, run_id="et-ambig"), outcome=RowOutcome.COMPLETED, sink_name="sink_a"
        )
        factory.data_flow.record_token_outcome(
            ref=TokenRef(token_id=token_b.token_id, run_id="et-ambig"), outcome=RowOutcome.COMPLETED, sink_name="sink_b"
        )
        factory.run_lifecycle.complete_run("et-ambig", RunStatus.COMPLETED)

        analyzer = LandscapeAnalyzer.__new__(LandscapeAnalyzer)
        analyzer._db = db
        analyzer._factory = factory

        result = analyzer.explain_token("et-ambig", row_id=row.row_id)

        assert "error" in result


class TestQueryDuplicateColumns:
    """Regression test for elspeth-fc7e25384c: query() silently drops duplicate columns."""

    def test_duplicate_column_names_rejected(self) -> None:
        """query() must reject SQL that produces duplicate column names.

        dict(zip(columns, values)) silently drops earlier values for
        duplicate keys — silent data loss in the audit surface.
        """
        from elspeth.mcp.analyzers.queries import query

        setup = make_recorder_with_run(run_id="dup-col")
        factory = setup.factory
        factory.run_lifecycle.complete_run("dup-col", RunStatus.COMPLETED)

        # Self-join produces duplicate column names (e.g., run_id, run_id)
        sql = "SELECT a.run_id, b.run_id FROM runs a, runs b WHERE a.run_id = b.run_id"

        with pytest.raises(ValueError, match="duplicate column names"):
            query(setup.db, factory, sql)

    def test_aliased_columns_work(self) -> None:
        """Aliased columns (no duplicates) should work fine."""
        from elspeth.mcp.analyzers.queries import query

        setup = make_recorder_with_run(run_id="alias-col")
        factory = setup.factory
        factory.run_lifecycle.complete_run("alias-col", RunStatus.COMPLETED)

        sql = "SELECT a.run_id AS a_run_id, b.run_id AS b_run_id FROM runs a, runs b WHERE a.run_id = b.run_id"
        results = query(setup.db, factory, sql)
        assert len(results) == 1
        assert "a_run_id" in results[0]
        assert "b_run_id" in results[0]
