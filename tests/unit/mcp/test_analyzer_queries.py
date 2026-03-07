# tests/unit/mcp/test_analyzer_queries.py
"""Tests for MCP analyzer query and diagnostic functions.

Priority coverage:
  1. explain_token — most complex, critical for debugging
  2. get_failure_context — 150+ lines, primary incident debugging tool
  3. get_run_summary — basic summary with real DB data

All tests use in-memory SQLite with pre-populated audit data via the
real LandscapeRecorder (no mocks for DB interaction).

Bug focus: nodes table has composite PK (node_id, run_id). Queries joining
through nodes must use BOTH keys to avoid cross-run contamination.

Bug found: dataclass_to_dict does not handle tuples, only lists.
LineageResult stores collections as tuples (tuple[RoutingEvent, ...], etc.),
so explain_token crashes with TypeError when iterating routing_events.
Tests for explain_token that hit this path are marked xfail.
"""

from __future__ import annotations

from typing import Any

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
from elspeth.contracts.call_data import RawCallPayload
from elspeth.contracts.errors import TransformErrorReason
from elspeth.core.landscape.lineage import explain
from elspeth.mcp.analyzers.diagnostics import get_failure_context
from elspeth.mcp.analyzers.queries import explain_token, list_runs
from elspeth.mcp.analyzers.reports import get_run_summary
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

    Returns a dict with db, recorder, run_id, and all entity IDs.
    """
    setup = make_recorder_with_run(
        run_id=run_id,
        source_node_id=source_node_id,
    )
    db = setup.db
    recorder = setup.recorder

    # Register transform and sink nodes
    register_test_node(
        recorder,
        run_id,
        transform_node_id,
        node_type=NodeType.TRANSFORM,
        plugin_name="field_mapper",
    )
    register_test_node(
        recorder,
        run_id,
        sink_node_id,
        node_type=NodeType.SINK,
        plugin_name="csv_sink",
    )

    # Register edges
    edge_1 = recorder.register_edge(run_id, source_node_id, transform_node_id, "continue", RoutingMode.MOVE)
    edge_2 = recorder.register_edge(run_id, transform_node_id, sink_node_id, "on_success", RoutingMode.MOVE)

    # Create row and token
    data = row_data or {"name": "Alice", "amount": 100}
    row = recorder.create_row(run_id, source_node_id, row_index=0, data=data)
    token = recorder.create_token(row.row_id)

    # Process through transform
    ns = recorder.begin_node_state(token.token_id, transform_node_id, run_id, step_index=1, input_data=data)

    if fail_transform:
        recorder.complete_node_state(
            ns.state_id,
            NodeStateStatus.FAILED,
            duration_ms=50.0,
            error={"reason": "test_failure", "message": "deliberately failed"},
        )
    else:
        recorder.complete_node_state(
            ns.state_id,
            NodeStateStatus.COMPLETED,
            output_data=data,
            duration_ms=50.0,
        )
        # Record routing event for the transform->sink edge
        recorder.record_routing_event(
            ns.state_id,
            edge_2.edge_id,
            RoutingMode.MOVE,
        )

    if complete_token:
        outcome = RowOutcome.FAILED if fail_transform else RowOutcome.COMPLETED
        recorder.record_token_outcome(
            run_id,
            token.token_id,
            outcome,
            sink_name=None if fail_transform else "csv_sink",
            error_hash="e" * 64 if fail_transform else None,
        )

    if complete_run:
        status = RunStatus.FAILED if fail_transform else RunStatus.COMPLETED
        recorder.complete_run(run_id, status)

    return {
        "db": db,
        "recorder": recorder,
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
        result = explain(p["recorder"], p["run_id"], token_id=p["token"].token_id)

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
        result = explain(p["recorder"], p["run_id"], row_id=p["row"].row_id)

        assert result is not None
        assert result.token.token_id == p["token"].token_id

    def test_explain_returns_none_for_nonexistent_token(self) -> None:
        """explain() returns None for a token_id that does not exist."""
        p = _build_linear_pipeline()
        result = explain(p["recorder"], p["run_id"], token_id="nonexistent-token")

        assert result is None

    def test_explain_returns_none_for_nonexistent_row(self) -> None:
        """explain() returns None for a row_id with no outcomes."""
        p = _build_linear_pipeline()
        result = explain(p["recorder"], p["run_id"], row_id="nonexistent-row")

        assert result is None

    def test_explain_includes_routing_events(self) -> None:
        """explain() includes routing events for the token."""
        p = _build_linear_pipeline()
        result = explain(p["recorder"], p["run_id"], token_id=p["token"].token_id)

        assert result is not None
        assert len(result.routing_events) == 1
        assert result.routing_events[0].mode == RoutingMode.MOVE

    def test_explain_includes_calls(self) -> None:
        """explain() includes external calls made during processing."""
        p = _build_linear_pipeline()
        state_id = p["node_state"].state_id

        call_index = p["recorder"].allocate_call_index(state_id)
        p["recorder"].record_call(
            state_id,
            call_index,
            CallType.LLM,
            CallStatus.SUCCESS,
            RawCallPayload({"prompt": "test"}),
            RawCallPayload({"response": "ok"}),
            latency_ms=100.0,
        )

        result = explain(p["recorder"], p["run_id"], token_id=p["token"].token_id)

        assert result is not None
        assert len(result.calls) == 1
        assert result.calls[0].call_type == CallType.LLM
        assert result.calls[0].latency_ms == 100.0

    def test_explain_includes_transform_errors(self) -> None:
        """explain() includes transform errors for the token."""
        setup = make_recorder_with_run(run_id="run-terr", source_node_id="src")
        recorder, run_id = setup.recorder, setup.run_id

        register_test_node(recorder, run_id, "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        row = recorder.create_row(run_id, "src", row_index=0, data={"x": 1})
        token = recorder.create_token(row.row_id)

        ns = recorder.begin_node_state(token.token_id, "xform", run_id, step_index=1, input_data={"x": 1})
        error_reason: TransformErrorReason = {"reason": "value_error", "message": "division by zero"}
        recorder.complete_node_state(ns.state_id, NodeStateStatus.FAILED, error=error_reason, duration_ms=5.0)

        recorder.record_transform_error(run_id, token.token_id, "xform", {"x": 1}, error_reason, "quarantine")
        recorder.record_token_outcome(run_id, token.token_id, RowOutcome.QUARANTINED, error_hash="b" * 64)
        recorder.complete_run(run_id, RunStatus.FAILED)

        result = explain(recorder, run_id, token_id=token.token_id)

        assert result is not None
        assert len(result.transform_errors) == 1
        assert result.transform_errors[0].transform_id == "xform"

    def test_explain_raises_for_neither_token_nor_row(self) -> None:
        """explain() raises ValueError when neither token_id nor row_id given."""
        p = _build_linear_pipeline()
        with pytest.raises(ValueError, match="Must provide either token_id or row_id"):
            explain(p["recorder"], p["run_id"])


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
        result = explain_token(p["db"], p["recorder"], p["run_id"], token_id="nonexistent")

        assert result is None

    def test_explain_token_returns_none_for_nonexistent_row(self) -> None:
        """explain_token returns None when row has no outcomes."""
        p = _build_linear_pipeline()
        result = explain_token(p["db"], p["recorder"], p["run_id"], row_id="nonexistent")

        assert result is None

    @pytest.mark.xfail(
        reason=(
            "BUG: dataclass_to_dict does not convert tuples to lists of dicts. "
            "LineageResult.routing_events is tuple[RoutingEvent, ...] which "
            "passes through unconverted, causing TypeError on subscript access."
        ),
        raises=TypeError,
        strict=True,
    )
    def test_explain_token_crashes_on_routing_events(self) -> None:
        """explain_token crashes when routing_events is non-empty.

        This documents the bug: dataclass_to_dict handles list but not tuple.
        The fix is to add tuple handling in dataclass_to_dict.
        """
        p = _build_linear_pipeline()
        # This should work but crashes due to the tuple conversion bug
        explain_token(p["db"], p["recorder"], p["run_id"], token_id=p["token"].token_id)

    def test_explain_token_works_without_routing_events(self) -> None:
        """explain_token succeeds when routing_events is empty (no conversion needed).

        With no routing events, the tuple is empty so the iteration in
        explain_token's for loop body is never reached, avoiding the crash.
        """
        # Build pipeline where transform fails (no routing event recorded)
        p = _build_linear_pipeline(run_id="no-route-run", fail_transform=True)
        result = explain_token(p["db"], p["recorder"], "no-route-run", token_id=p["token"].token_id)

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
        result = get_failure_context(setup.db, setup.recorder, "nonexistent-run")

        assert "error" in result
        assert "not found" in result["error"]

    def test_empty_failure_context_for_clean_run(self) -> None:
        """get_failure_context returns empty lists when run has no failures."""
        p = _build_linear_pipeline(run_id="clean-run")
        result = get_failure_context(p["db"], p["recorder"], "clean-run")

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
        result = get_failure_context(p["db"], p["recorder"], "fail-run")

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
        db, recorder = setup.db, setup.recorder

        register_test_node(recorder, "terr-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="llm_classifier")

        row = recorder.create_row("terr-run", "src", row_index=0, data={"text": "hello"})
        token = recorder.create_token(row.row_id)

        ns = recorder.begin_node_state(token.token_id, "xform", "terr-run", step_index=1, input_data={"text": "hello"})
        error_reason: TransformErrorReason = {"reason": "llm_call_failed", "error": "timeout"}
        recorder.complete_node_state(ns.state_id, NodeStateStatus.FAILED, error=error_reason, duration_ms=5000.0)

        recorder.record_transform_error("terr-run", token.token_id, "xform", {"text": "hello"}, error_reason, "quarantine")
        recorder.record_token_outcome("terr-run", token.token_id, RowOutcome.QUARANTINED, error_hash="c" * 64)
        recorder.complete_run("terr-run", RunStatus.FAILED)

        result = get_failure_context(db, recorder, "terr-run")

        assert "error" not in result
        assert len(result["transform_errors"]) == 1
        te = result["transform_errors"][0]
        assert te["plugin"] == "llm_classifier"
        assert te["details"]["reason"] == "llm_call_failed"
        assert result["patterns"]["transform_error_count"] == 1

    def test_failure_context_with_validation_errors(self) -> None:
        """get_failure_context includes validation errors with plugin name."""
        setup = make_recorder_with_run(run_id="verr-run", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        recorder.record_validation_error(
            "verr-run",
            "src",
            {"bad_field": None},
            "required field missing",
            "observed",
            "quarantine",
        )
        recorder.complete_run("verr-run", RunStatus.COMPLETED)

        result = get_failure_context(db, recorder, "verr-run")

        assert "error" not in result
        assert len(result["validation_errors"]) == 1
        ve = result["validation_errors"][0]
        assert ve["plugin"] == "source"
        assert ve["sample_data"] is not None
        assert result["patterns"]["validation_error_count"] == 1

    def test_failure_context_detects_retries(self) -> None:
        """get_failure_context sets has_retries=True when attempt > 1.

        NOTE: Production code uses ``attempt > 1`` which means attempts 0 and 1
        are NOT considered retries. This is a potential off-by-one: attempt=0 is
        the initial try, attempt=1 is the first retry, so ``attempt > 0`` would
        be the correct threshold. We test the actual behavior here (attempt=2).
        """
        setup = make_recorder_with_run(run_id="retry-run", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        register_test_node(recorder, "retry-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="flaky")

        row = recorder.create_row("retry-run", "src", row_index=0, data={"x": 1})
        token = recorder.create_token(row.row_id)

        # Attempt 0: failed (initial)
        ns0 = recorder.begin_node_state(token.token_id, "xform", "retry-run", step_index=1, input_data={"x": 1}, attempt=0)
        recorder.complete_node_state(ns0.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})

        # Attempt 1: failed (first retry)
        ns1 = recorder.begin_node_state(token.token_id, "xform", "retry-run", step_index=1, input_data={"x": 1}, attempt=1)
        recorder.complete_node_state(ns1.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})

        # Attempt 2: failed (second retry — triggers has_retries detection)
        ns2 = recorder.begin_node_state(token.token_id, "xform", "retry-run", step_index=1, input_data={"x": 1}, attempt=2)
        recorder.complete_node_state(ns2.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})

        recorder.record_token_outcome("retry-run", token.token_id, RowOutcome.FAILED, error_hash="d" * 64)
        recorder.complete_run("retry-run", RunStatus.FAILED)

        result = get_failure_context(db, recorder, "retry-run")

        assert "error" not in result
        assert len(result["failed_node_states"]) == 3
        assert result["patterns"]["has_retries"] is True
        assert result["patterns"]["failure_count"] == 3

    def test_failure_context_has_retries_false_for_single_attempt(self) -> None:
        """has_retries is False when all failures are attempt 0 (no retries)."""
        p = _build_linear_pipeline(run_id="no-retry-run", fail_transform=True)
        result = get_failure_context(p["db"], p["recorder"], "no-retry-run")

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
        db, recorder = setup.db, setup.recorder

        # Run X: xform is "llm_classifier"
        register_test_node(recorder, "run-X", "xform", node_type=NodeType.TRANSFORM, plugin_name="llm_classifier")

        row_x = recorder.create_row("run-X", "src", row_index=0, data={"x": 1})
        token_x = recorder.create_token(row_x.row_id)

        ns_x = recorder.begin_node_state(token_x.token_id, "xform", "run-X", step_index=1, input_data={"x": 1})
        recorder.complete_node_state(ns_x.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})
        recorder.record_token_outcome("run-X", token_x.token_id, RowOutcome.FAILED, error_hash="e" * 64)
        recorder.complete_run("run-X", RunStatus.FAILED)

        # Run Y: same node_id "xform" but different plugin "field_mapper"
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-Y")
        register_test_node(recorder, "run-Y", "src", node_type=NodeType.SOURCE, plugin_name="source")
        register_test_node(recorder, "run-Y", "xform", node_type=NodeType.TRANSFORM, plugin_name="field_mapper")

        row_y = recorder.create_row("run-Y", "src", row_index=0, data={"y": 2})
        token_y = recorder.create_token(row_y.row_id)

        ns_y = recorder.begin_node_state(token_y.token_id, "xform", "run-Y", step_index=1, input_data={"y": 2})
        recorder.complete_node_state(ns_y.state_id, NodeStateStatus.FAILED, duration_ms=20.0, error={"reason": "test_failure"})
        recorder.record_token_outcome("run-Y", token_y.token_id, RowOutcome.FAILED, error_hash="f" * 64)
        recorder.complete_run("run-Y", RunStatus.FAILED)

        # Query run-X failure context
        result_x = get_failure_context(db, recorder, "run-X")
        assert "error" not in result_x
        assert len(result_x["failed_node_states"]) == 1
        # The plugin name MUST be from run-X, not run-Y
        assert result_x["failed_node_states"][0]["plugin"] == "llm_classifier"

        # Query run-Y failure context
        result_y = get_failure_context(db, recorder, "run-Y")
        assert "error" not in result_y
        assert len(result_y["failed_node_states"]) == 1
        assert result_y["failed_node_states"][0]["plugin"] == "field_mapper"

    def test_failure_context_composite_key_transform_errors(self) -> None:
        """Verify transform_errors join uses composite key (node_id, run_id).

        Same setup as composite key test for node_states, but verifying
        the transform_errors -> nodes outerjoin uses both keys.
        """
        setup = make_recorder_with_run(run_id="run-P", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        # Run P: xform is "slow_transform"
        register_test_node(recorder, "run-P", "xform", node_type=NodeType.TRANSFORM, plugin_name="slow_transform")
        row_p = recorder.create_row("run-P", "src", row_index=0, data={"p": 1})
        token_p = recorder.create_token(row_p.row_id)
        error_reason: TransformErrorReason = {"reason": "timeout"}
        recorder.record_transform_error("run-P", token_p.token_id, "xform", {"p": 1}, error_reason, "quarantine")
        recorder.record_token_outcome("run-P", token_p.token_id, RowOutcome.QUARANTINED, error_hash="a" * 64)
        recorder.complete_run("run-P", RunStatus.FAILED)

        # Run Q: same node_id "xform" but "fast_transform"
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-Q")
        register_test_node(recorder, "run-Q", "src", node_type=NodeType.SOURCE, plugin_name="source")
        register_test_node(recorder, "run-Q", "xform", node_type=NodeType.TRANSFORM, plugin_name="fast_transform")
        row_q = recorder.create_row("run-Q", "src", row_index=0, data={"q": 2})
        token_q = recorder.create_token(row_q.row_id)
        error_reason_q: TransformErrorReason = {"reason": "bad_data"}
        recorder.record_transform_error("run-Q", token_q.token_id, "xform", {"q": 2}, error_reason_q, "quarantine")
        recorder.record_token_outcome("run-Q", token_q.token_id, RowOutcome.QUARANTINED, error_hash="b" * 64)
        recorder.complete_run("run-Q", RunStatus.FAILED)

        result_p = get_failure_context(db, recorder, "run-P")
        assert len(result_p["transform_errors"]) == 1
        assert result_p["transform_errors"][0]["plugin"] == "slow_transform"

        result_q = get_failure_context(db, recorder, "run-Q")
        assert len(result_q["transform_errors"]) == 1
        assert result_q["transform_errors"][0]["plugin"] == "fast_transform"

    def test_failure_context_limit_parameter(self) -> None:
        """get_failure_context respects the limit parameter."""
        setup = make_recorder_with_run(run_id="limit-run", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        register_test_node(recorder, "limit-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        # Create 5 rows, all failing
        for i in range(5):
            row = recorder.create_row("limit-run", "src", row_index=i, data={"i": i})
            token = recorder.create_token(row.row_id)
            ns = recorder.begin_node_state(token.token_id, "xform", "limit-run", step_index=1, input_data={"i": i})
            recorder.complete_node_state(ns.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})
            recorder.record_token_outcome("limit-run", token.token_id, RowOutcome.FAILED, error_hash="a" * 64)

        recorder.complete_run("limit-run", RunStatus.FAILED)

        result = get_failure_context(db, recorder, "limit-run", limit=2)

        assert "error" not in result
        assert len(result["failed_node_states"]) == 2
        assert result["patterns"]["failure_count"] == 2

    def test_failure_context_plugins_failing_pattern(self) -> None:
        """get_failure_context identifies which plugins are failing."""
        setup = make_recorder_with_run(run_id="pattern-run", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        register_test_node(recorder, "pattern-run", "xform-a", node_type=NodeType.TRANSFORM, plugin_name="mapper")
        register_test_node(recorder, "pattern-run", "xform-b", node_type=NodeType.TRANSFORM, plugin_name="classifier")

        # Fail in xform-a
        row0 = recorder.create_row("pattern-run", "src", row_index=0, data={"i": 0})
        token0 = recorder.create_token(row0.row_id)
        ns0 = recorder.begin_node_state(token0.token_id, "xform-a", "pattern-run", step_index=1, input_data={"i": 0})
        recorder.complete_node_state(ns0.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})
        recorder.record_token_outcome("pattern-run", token0.token_id, RowOutcome.FAILED, error_hash="a" * 64)

        # Fail in xform-b
        row1 = recorder.create_row("pattern-run", "src", row_index=1, data={"i": 1})
        token1 = recorder.create_token(row1.row_id)
        ns1 = recorder.begin_node_state(token1.token_id, "xform-b", "pattern-run", step_index=2, input_data={"i": 1})
        recorder.complete_node_state(ns1.state_id, NodeStateStatus.FAILED, duration_ms=10.0, error={"reason": "test_failure"})
        recorder.record_token_outcome("pattern-run", token1.token_id, RowOutcome.FAILED, error_hash="b" * 64)

        recorder.complete_run("pattern-run", RunStatus.FAILED)

        result = get_failure_context(db, recorder, "pattern-run")

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
        result = get_run_summary(p["db"], p["recorder"], "summary-run")

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
        result = get_run_summary(setup.db, setup.recorder, "nonexistent")

        assert "error" in result

    def test_summary_counts_errors_correctly(self) -> None:
        """get_run_summary counts both validation and transform errors."""
        setup = make_recorder_with_run(run_id="err-run", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        register_test_node(recorder, "err-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")

        # Record a validation error
        recorder.record_validation_error("err-run", "src", {"bad": "data"}, "missing field", "observed", "quarantine")

        # Record a transform error
        row = recorder.create_row("err-run", "src", row_index=0, data={"x": 1})
        token = recorder.create_token(row.row_id)
        error_reason: TransformErrorReason = {"reason": "processing_error"}
        recorder.record_transform_error("err-run", token.token_id, "xform", {"x": 1}, error_reason, "quarantine")
        recorder.record_token_outcome("err-run", token.token_id, RowOutcome.QUARANTINED, error_hash="a" * 64)
        recorder.complete_run("err-run", RunStatus.COMPLETED)

        result = get_run_summary(db, recorder, "err-run")

        assert "error" not in result
        assert result["errors"]["validation"] == 1
        assert result["errors"]["transform"] == 1
        assert result["errors"]["total"] == 2

    def test_summary_outcome_distribution(self) -> None:
        """get_run_summary returns correct outcome distribution for mixed outcomes."""
        setup = make_recorder_with_run(run_id="dist-run", source_node_id="src")
        db, recorder = setup.db, setup.recorder

        register_test_node(recorder, "dist-run", "xform", node_type=NodeType.TRANSFORM, plugin_name="mapper")
        register_test_node(recorder, "dist-run", "sink", node_type=NodeType.SINK, plugin_name="csv_sink")

        # Row 0: completed
        row0 = recorder.create_row("dist-run", "src", row_index=0, data={"i": 0})
        token0 = recorder.create_token(row0.row_id)
        recorder.record_token_outcome("dist-run", token0.token_id, RowOutcome.COMPLETED, sink_name="csv_sink")

        # Row 1: quarantined
        row1 = recorder.create_row("dist-run", "src", row_index=1, data={"i": 1})
        token1 = recorder.create_token(row1.row_id)
        recorder.record_token_outcome("dist-run", token1.token_id, RowOutcome.QUARANTINED, error_hash="b" * 64)

        # Row 2: completed
        row2 = recorder.create_row("dist-run", "src", row_index=2, data={"i": 2})
        token2 = recorder.create_token(row2.row_id)
        recorder.record_token_outcome("dist-run", token2.token_id, RowOutcome.COMPLETED, sink_name="csv_sink")

        recorder.complete_run("dist-run", RunStatus.COMPLETED)

        result = get_run_summary(db, recorder, "dist-run")

        assert "error" not in result
        assert result["outcome_distribution"]["completed"] == 2
        assert result["outcome_distribution"]["quarantined"] == 1

    def test_summary_avg_state_duration(self) -> None:
        """get_run_summary returns average node state duration."""
        p = _build_linear_pipeline(run_id="dur-run")
        result = get_run_summary(p["db"], p["recorder"], "dur-run")

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
        recorder = setup.recorder
        recorder.complete_run("list-run-1", RunStatus.COMPLETED)

        result = list_runs(setup.db, recorder)

        assert len(result) == 1
        assert result[0]["run_id"] == "list-run-1"
        assert result[0]["status"] == "completed"

    def test_list_runs_filters_by_status(self) -> None:
        """list_runs filters by status when provided."""
        setup = make_recorder_with_run(run_id="filter-run")
        recorder = setup.recorder
        recorder.complete_run("filter-run", RunStatus.FAILED)

        # Should find it with "failed" filter
        result = list_runs(setup.db, recorder, status="failed")
        assert len(result) == 1

        # Should not find it with "completed" filter
        result = list_runs(setup.db, recorder, status="completed")
        assert len(result) == 0

    def test_list_runs_invalid_status_raises(self) -> None:
        """list_runs raises ValueError for invalid status."""
        setup = make_recorder_with_run()

        with pytest.raises(ValueError, match="Invalid status"):
            list_runs(setup.db, setup.recorder, status="bogus")
