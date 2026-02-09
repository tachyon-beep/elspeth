# tests/unit/engine/test_processor.py
"""Unit tests for RowProcessor — the DAG execution state machine.

processor.py orchestrates row processing through transforms, gates, and
aggregation. It is the largest file in the engine (~2,000 lines) and the
most critical path for correctness.

Test strategy:
- Use LandscapeDB.in_memory() for real audit recording (no mock recorder)
- Use real SpanFactory (no tracer — no-op spans)
- Mock transforms/gates to control routing outcomes
- Verify outcomes via RowResult assertions

This avoids the anti-pattern of testing mocks instead of behavior.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest

# For node registration
from elspeth.contracts import NodeType, RowOutcome, SourceRow, TokenInfo, TransformResult
from elspeth.contracts.enums import (
    NodeStateStatus,
    RoutingKind,
    TriggerType,
)
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import SchemaContract
from elspeth.contracts.types import BranchName, CoalesceName, GateName, NodeID
from elspeth.core.config import AggregationSettings, GateSettings
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.engine.processor import (
    MAX_WORK_QUEUE_ITERATIONS,
    DAGTraversalContext,
    RowProcessor,
    _WorkItem,
)
from elspeth.engine.retry import MaxRetriesExceeded, RetryManager
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.clients.llm import LLMClientError
from elspeth.plugins.protocols import GateProtocol, TransformProtocol
from elspeth.testing import make_contract, make_row, make_source_row, make_token_info

# =============================================================================
# Helpers
# =============================================================================

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return make_contract(fields={"value": int}, mode="OBSERVED")


def _make_source_row(data: dict[str, Any] | None = None) -> SourceRow:
    """Create a valid SourceRow with contract."""
    contract = _make_contract()
    return make_source_row(data or {"value": 42}, contract=contract)


def _make_recorder(
    *,
    run_id: str = "test-run",
    source_node_id: str = "source-0",
) -> tuple[LandscapeDB, LandscapeRecorder]:
    """Create an in-memory LandscapeDB with run and source node registered.

    This satisfies FK constraints: rows table references nodes(node_id, run_id).
    """
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    recorder.register_node(
        run_id=run_id,
        plugin_name="test-source",
        node_type=NodeType.SOURCE,
        plugin_version="1.0",
        config={},
        node_id=source_node_id,
        schema_config=_DYNAMIC_SCHEMA,
    )
    return db, recorder


def _make_processor(
    recorder: LandscapeRecorder,
    *,
    run_id: str = "test-run",
    source_node_id: str = "source-0",
    edge_map: dict[tuple[NodeID, str], str] | None = None,
    route_resolution_map: dict[tuple[NodeID, str], str] | None = None,
    config_gates: list[GateSettings] | None = None,
    config_gate_id_map: dict[GateName, NodeID] | None = None,
    aggregation_settings: dict[NodeID, AggregationSettings] | None = None,
    retry_manager: RetryManager | None = None,
    coalesce_executor: Any = None,
    coalesce_node_ids: dict[CoalesceName, NodeID] | None = None,
    branch_to_coalesce: dict[BranchName, CoalesceName] | None = None,
    coalesce_step_map: dict[CoalesceName, int] | None = None,
    coalesce_on_success_map: dict[CoalesceName, str] | None = None,
    node_to_next: dict[NodeID, NodeID | None] | None = None,
    restored_aggregation_state: dict[NodeID, dict[str, Any]] | None = None,
    telemetry_manager: Any = None,
) -> RowProcessor:
    """Create a RowProcessor with sensible defaults."""
    coalesce_nodes = dict(coalesce_node_ids or {})
    if coalesce_step_map:
        for coalesce_name in coalesce_step_map:
            coalesce_nodes.setdefault(coalesce_name, NodeID(f"coalesce::{coalesce_name}"))

    traversal = DAGTraversalContext(
        node_step_map={},
        node_to_plugin={
            config_gate_id_map[GateName(gate.name)]: gate
            for gate in (config_gates or [])
            if config_gate_id_map and GateName(gate.name) in config_gate_id_map
        },
        first_transform_node_id=None,
        node_to_next=node_to_next or {},
        coalesce_node_map=coalesce_nodes,
    )

    return RowProcessor(
        recorder=recorder,
        span_factory=SpanFactory(),  # No tracer — no-op spans
        run_id=run_id,
        source_node_id=NodeID(source_node_id),
        traversal=traversal,
        edge_map=edge_map,
        route_resolution_map=route_resolution_map,
        aggregation_settings=aggregation_settings,
        retry_manager=retry_manager,
        coalesce_executor=coalesce_executor,
        branch_to_coalesce=branch_to_coalesce,
        coalesce_step_map=coalesce_step_map,
        coalesce_on_success_map=coalesce_on_success_map,
        restored_aggregation_state=restored_aggregation_state,
        telemetry_manager=telemetry_manager,
    )


def _make_mock_transform(
    *,
    node_id: str = "transform-1",
    name: str = "test-transform",
    on_error: str | None = "discard",
    is_batch_aware: bool = False,
    creates_tokens: bool = False,
    result: TransformResult | None = None,
) -> Mock:
    """Create a mock transform satisfying TransformProtocol."""
    transform = Mock(spec=TransformProtocol)
    transform.node_id = node_id
    transform.name = name
    transform.on_error = on_error
    transform.is_batch_aware = is_batch_aware
    transform.creates_tokens = creates_tokens
    if result is not None:
        transform.process.return_value = result
    return transform


def _make_mock_gate(
    *,
    node_id: str = "gate-1",
    name: str = "test-gate",
) -> Mock:
    """Create a mock gate satisfying GateProtocol."""
    gate = Mock(spec=GateProtocol)
    gate.node_id = node_id
    gate.name = name
    return gate


# =============================================================================
# Constructor: Error Edge Map
# =============================================================================


class TestConstructorErrorEdgeMap:
    """Tests for error edge map construction in __init__."""

    def test_extracts_error_edges_from_edge_map(self) -> None:
        """Error edges (labels like __error_0__) are extracted into error_edge_ids."""
        _, recorder = _make_recorder()
        edge_map = {
            (NodeID("t1"), "continue"): "edge-1",
            (NodeID("t1"), "__error_0__"): "error-edge-1",
            (NodeID("t2"), "continue"): "edge-2",
            (NodeID("t2"), "__error_1__"): "error-edge-2",
        }
        processor = _make_processor(recorder, edge_map=edge_map)
        assert processor._error_edge_ids == {
            NodeID("t1"): "error-edge-1",
            NodeID("t2"): "error-edge-2",
        }

    def test_empty_edge_map_produces_no_error_edges(self) -> None:
        """No edge_map means no error edges."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)
        assert processor._error_edge_ids == {}

    def test_non_error_labels_ignored(self) -> None:
        """Only __error_N__ labels are extracted; other labels are ignored."""
        _, recorder = _make_recorder()
        edge_map = {
            (NodeID("t1"), "continue"): "edge-1",
            (NodeID("t1"), "route_to_sink"): "edge-2",
            (NodeID("t1"), "fork_path_a"): "edge-3",
        }
        processor = _make_processor(recorder, edge_map=edge_map)
        assert processor._error_edge_ids == {}

    def test_restores_aggregation_state(self) -> None:
        """Restored aggregation state is passed to AggregationExecutor."""
        _, recorder = _make_recorder()
        # We can't easily verify internal state restoration without exposing
        # internals, but we can verify the constructor doesn't crash with
        # restoration data
        processor = _make_processor(
            recorder,
            aggregation_settings={
                NodeID("agg-1"): AggregationSettings(
                    name="test-agg",
                    plugin="test-plugin",
                    trigger={"count": 3},
                ),
            },
            restored_aggregation_state={
                NodeID("agg-1"): {"buffer": [], "trigger_state": {}},
            },
        )
        assert processor is not None


# =============================================================================
# _get_gate_destinations
# =============================================================================


class TestGetGateDestinations:
    """Tests for the gate destination extraction helper."""

    def test_routed_to_sink(self) -> None:
        """Gate routed to a named sink returns that sink name."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)
        outcome = Mock()
        outcome.sink_name = "error-sink"
        assert processor._get_gate_destinations(outcome) == ("error-sink",)

    def test_fork_to_paths(self) -> None:
        """Fork returns branch names of child tokens."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)
        child_a = Mock()
        child_a.branch_name = "path_a"
        child_b = Mock()
        child_b.branch_name = "path_b"
        outcome = Mock()
        outcome.sink_name = None
        outcome.result.action.kind = RoutingKind.FORK_TO_PATHS
        outcome.child_tokens = [child_a, child_b]
        assert processor._get_gate_destinations(outcome) == ("path_a", "path_b")

    def test_continue_routing(self) -> None:
        """Continue routing returns ("continue",)."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)
        outcome = Mock()
        outcome.sink_name = None
        outcome.result.action.kind = RoutingKind.CONTINUE
        assert processor._get_gate_destinations(outcome) == ("continue",)


# =============================================================================
# process_row: Linear pipeline (no transforms)
# =============================================================================


class TestProcessRowNoTransforms:
    """Tests for process_row with an empty transform list."""

    def test_empty_pipeline_returns_completed(self) -> None:
        """Row through empty pipeline gets COMPLETED outcome."""
        _, recorder = _make_recorder()

        processor = _make_processor(recorder)
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        results = processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.COMPLETED
        assert results[0].token.row_data["value"] == 42

    def test_creates_row_and_token_records(self) -> None:
        """process_row creates row record and token in audit trail."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        results = processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        # Verify token was created (result has a valid token_id)
        token = results[0].token
        assert token.token_id is not None
        assert token.row_id is not None

    def test_records_source_node_state(self) -> None:
        """process_row records a source node_state with COMPLETED status."""
        db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )

        # Check that source node_state was recorded
        from sqlalchemy import select

        from elspeth.core.landscape.schema import node_states_table

        with db.connection() as conn:
            states = conn.execute(select(node_states_table).where(node_states_table.c.run_id == "test-run")).fetchall()

        # At minimum, the source node_state should exist
        assert len(states) >= 1
        source_state = states[0]
        assert source_state.status == NodeStateStatus.COMPLETED.value


# =============================================================================
# process_row: Single transform
# =============================================================================


class TestProcessRowSingleTransform:
    """Tests for process_row with a single transform."""

    def _setup(self) -> tuple[LandscapeDB, LandscapeRecorder, RowProcessor]:
        db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        return db, recorder, processor

    def test_successful_transform_returns_completed(self) -> None:
        """Row passes through transform → COMPLETED."""
        _db, _recorder, processor = self._setup()
        source_row = _make_source_row({"value": 10})
        ctx = PluginContext(run_id="test-run", config={})

        transform = _make_mock_transform()
        output_data = make_row({"value": 10, "enriched": True})
        success_result = TransformResult.success(
            output_data,
            success_reason={"action": "test"},
        )

        # side_effect receives the real token and returns it with the desired result
        def executor_side_effect(*, transform, token, ctx, step_in_pipeline, attempt=0):
            return (success_result, token, None)

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=executor_side_effect,
        ):
            results = processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[transform],
                ctx=ctx,
            )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.COMPLETED

    def test_transform_error_with_discard_returns_quarantined(self) -> None:
        """Transform error with on_error='discard' → QUARANTINED."""
        _db, _recorder, processor = self._setup()
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        transform = _make_mock_transform(on_error="discard")
        error_result = TransformResult.error(
            {"reason": "bad_value"},
            retryable=False,
        )

        def executor_side_effect(*, transform, token, ctx, step_in_pipeline, attempt=0):
            return (error_result, token, "discard")

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=executor_side_effect,
        ):
            results = processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[transform],
                ctx=ctx,
            )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.QUARANTINED

    def test_transform_error_with_named_sink_returns_routed(self) -> None:
        """Transform error with on_error='errors' → ROUTED to error sink."""
        _db, _recorder, processor = self._setup()
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        transform = _make_mock_transform(on_error="errors")
        error_result = TransformResult.error(
            {"reason": "bad_value"},
            retryable=False,
        )

        def executor_side_effect(*, transform, token, ctx, step_in_pipeline, attempt=0):
            return (error_result, token, "errors")

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=executor_side_effect,
        ):
            results = processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[transform],
                ctx=ctx,
            )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.ROUTED
        assert results[0].sink_name == "errors"

    def test_max_retries_exceeded_returns_failed(self) -> None:
        """MaxRetriesExceeded → FAILED outcome."""
        _db, _recorder, processor = self._setup()
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        transform = _make_mock_transform()
        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=MaxRetriesExceeded(3, Exception("boom")),
        ):
            results = processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[transform],
                ctx=ctx,
            )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.FAILED
        assert results[0].error is not None


# =============================================================================
# process_row: Multi-row output (deaggregation)
# =============================================================================


class TestProcessRowMultiRowOutput:
    """Tests for deaggregation (1→N) in regular transforms."""

    def test_multi_row_with_creates_tokens_returns_expanded(self) -> None:
        """Transform with creates_tokens=True returning multi-row → EXPANDED."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        contract = _make_contract()
        output_rows = [
            make_row({"value": 1}, contract=contract),
            make_row({"value": 2}, contract=contract),
        ]
        multi_result = TransformResult.success_multi(
            output_rows,
            success_reason={"action": "expand"},
        )

        transform = _make_mock_transform(creates_tokens=True)

        def executor_side_effect(*, transform, token, ctx, step_in_pipeline, attempt=0):
            return (multi_result, token, None)

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=executor_side_effect,
        ):
            results = processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[transform],
                ctx=ctx,
            )

        # Parent should be EXPANDED, children should be COMPLETED
        outcomes = {r.outcome for r in results}
        assert RowOutcome.EXPANDED in outcomes
        assert RowOutcome.COMPLETED in outcomes

    def test_multi_row_without_creates_tokens_raises(self) -> None:
        """Transform returning multi-row without creates_tokens=True → RuntimeError."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        contract = _make_contract()
        output_rows = [
            make_row({"value": 1}, contract=contract),
            make_row({"value": 2}, contract=contract),
        ]
        multi_result = TransformResult.success_multi(
            output_rows,
            success_reason={"action": "expand"},
        )

        transform = _make_mock_transform(creates_tokens=False)

        def executor_side_effect(*, transform, token, ctx, step_in_pipeline, attempt=0):
            return (multi_result, token, None)

        with (
            patch.object(
                processor._transform_executor,
                "execute_transform",
                side_effect=executor_side_effect,
            ),
            pytest.raises(RuntimeError, match="creates_tokens=False"),
        ):
            processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[transform],
                ctx=ctx,
            )

    def test_multi_row_with_inconsistent_contracts_raises(self) -> None:
        """Multi-row result with mixed contracts must crash at construction (plugin bug).

        Validation lives in TransformResult.success_multi() — it fires before
        the result can reach any consumer in the processor.
        """
        from elspeth.contracts.errors import PluginContractViolation

        contract_a = make_contract(fields={"value": int}, mode="OBSERVED")
        contract_b = make_contract(fields={"other": str}, mode="OBSERVED")
        output_rows = [
            make_row({"value": 1}, contract=contract_a),
            make_row({"other": "x"}, contract=contract_b),
        ]
        with pytest.raises(PluginContractViolation, match="inconsistent contracts"):
            TransformResult.success_multi(
                output_rows,
                success_reason={"action": "expand"},
            )


# =============================================================================
# process_existing_row (resume path)
# =============================================================================


class TestProcessExistingRow:
    """Tests for process_existing_row (resume after crash)."""

    def test_does_not_create_new_row_record(self) -> None:
        """process_existing_row creates token but NOT a new row."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)

        contract = _make_contract()
        row_data = make_row({"value": 42}, contract=contract)
        ctx = PluginContext(run_id="test-run", config={})

        # We need a pre-existing row. Create one via process_row first.
        source_row = _make_source_row({"value": 42})
        first_results = processor.process_row(
            row_index=0,
            source_row=source_row,
            transforms=[],
            ctx=ctx,
        )
        existing_row_id = first_results[0].token.row_id

        # Now process_existing_row for the same row
        results = processor.process_existing_row(
            row_id=existing_row_id,
            row_data=row_data,
            transforms=[],
            ctx=ctx,
        )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.COMPLETED
        # The row_id should match the existing row
        assert results[0].token.row_id == existing_row_id


# =============================================================================
# process_token (mid-pipeline entry)
# =============================================================================


class TestProcessToken:
    """Tests for process_token (used for coalesce merge continuations)."""

    def test_process_token_from_midpoint(self) -> None:
        """process_token starts processing from a given step."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        ctx = PluginContext(run_id="test-run", config={})

        # Create a token to process
        token = make_token_info(data={"value": 42})

        results = processor.process_token(
            token=token,
            transforms=[],
            ctx=ctx,
            start_step=0,
        )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.COMPLETED


# =============================================================================
# _drain_work_queue: Iteration Guard
# =============================================================================


class TestDrainWorkQueueIterationGuard:
    """Tests for the MAX_WORK_QUEUE_ITERATIONS safety limit."""

    def test_iteration_guard_prevents_infinite_loop(self) -> None:
        """Work queue exceeding MAX_WORK_QUEUE_ITERATIONS raises RuntimeError."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        ctx = PluginContext(run_id="test-run", config={})
        token = make_token_info(data={"value": 1})

        # Mock _process_single_token to always produce more work
        def infinite_loop_producer(token, transforms, ctx, current_node_id, **kwargs):
            new_token = make_token_info(data={"value": 1})
            return (None, [_WorkItem(token=new_token, current_node_id=NodeID("source-0"))])

        with (
            patch.object(processor, "_process_single_token", side_effect=infinite_loop_producer),
            pytest.raises(RuntimeError, match=r"exceeded.*iterations"),
        ):
            processor._drain_work_queue(
                _WorkItem(token=token, current_node_id=NodeID("source-0")),
                transforms=[],
                ctx=ctx,
            )

    def test_max_iterations_constant_is_reasonable(self) -> None:
        """MAX_WORK_QUEUE_ITERATIONS should be at least 1000."""
        assert MAX_WORK_QUEUE_ITERATIONS >= 1000


# =============================================================================
# _execute_transform_with_retry: No retry manager
# =============================================================================


class TestExecuteTransformNoRetry:
    """Tests for _execute_transform_with_retry when no retry_manager is set."""

    def _setup(self) -> tuple[LandscapeDB, LandscapeRecorder, RowProcessor]:
        db, recorder = _make_recorder()

        processor = _make_processor(recorder, retry_manager=None)
        return db, recorder, processor

    def test_single_attempt_success(self) -> None:
        """Without retry_manager, executes single attempt."""
        _, _, processor = self._setup()
        transform = _make_mock_transform()
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})
        expected_result = TransformResult.success(
            make_row({"value": 42}),
            success_reason={"action": "test"},
        )

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            return_value=(expected_result, token, None),
        ) as mock_exec:
            result, _out_token, error_sink = processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )
            mock_exec.assert_called_once()
            assert result.status == "success"
            assert error_sink is None

    def test_retryable_llm_error_with_on_error_discard(self) -> None:
        """Retryable LLMClientError with on_error='discard' returns error result (no re-raise)."""
        _, _, processor = self._setup()
        transform = _make_mock_transform(node_id="t1", on_error="discard")
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        llm_error = LLMClientError("rate limited", retryable=True)
        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=llm_error,
        ):
            result, _out_token, error_sink = processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

        assert result.status == "error"
        assert error_sink == "discard"

    def test_retryable_llm_error_without_on_error_raises(self) -> None:
        """Retryable LLMClientError without on_error raises RuntimeError."""
        _, _, processor = self._setup()
        transform = _make_mock_transform(node_id="t1", on_error=None)
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        llm_error = LLMClientError("rate limited", retryable=True)
        with (
            patch.object(
                processor._transform_executor,
                "execute_transform",
                side_effect=llm_error,
            ),
            pytest.raises(RuntimeError, match="no on_error configured"),
        ):
            processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

    def test_non_retryable_llm_error_reraises(self) -> None:
        """Non-retryable LLMClientError is re-raised directly."""
        _, _, processor = self._setup()
        transform = _make_mock_transform(node_id="t1", on_error="discard")
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        llm_error = LLMClientError("content policy", retryable=False)
        with (
            patch.object(
                processor._transform_executor,
                "execute_transform",
                side_effect=llm_error,
            ),
            pytest.raises(LLMClientError, match="content policy"),
        ):
            processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

    def test_transient_connection_error_with_on_error(self) -> None:
        """ConnectionError with on_error returns error result (no re-raise)."""
        _, _, processor = self._setup()
        transform = _make_mock_transform(node_id="t1", on_error="discard")
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=ConnectionError("connection reset"),
        ):
            result, _out_token, error_sink = processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

        assert result.status == "error"
        assert error_sink == "discard"

    def test_transient_timeout_error_with_on_error(self) -> None:
        """TimeoutError with on_error returns error result."""
        _, _, processor = self._setup()
        transform = _make_mock_transform(node_id="t1", on_error="discard")
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        with patch.object(
            processor._transform_executor,
            "execute_transform",
            side_effect=TimeoutError("timed out"),
        ):
            result, _out_token, error_sink = processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

        assert result.status == "error"
        assert error_sink == "discard"

    def test_transient_error_without_on_error_raises(self) -> None:
        """Transient error without on_error raises RuntimeError."""
        _, _, processor = self._setup()
        transform = _make_mock_transform(node_id="t1", on_error=None)
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        with (
            patch.object(
                processor._transform_executor,
                "execute_transform",
                side_effect=ConnectionError("connection reset"),
            ),
            pytest.raises(RuntimeError, match="no on_error configured"),
        ):
            processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

    def test_retryable_llm_error_with_named_error_sink_returns_error_sink(self) -> None:
        """Retryable LLMClientError with on_error pointing to real sink returns that sink."""
        _, recorder, processor = self._setup()
        # Set up error edge so the routing path is reachable
        processor._error_edge_ids = {NodeID("t1"): "error-edge-1"}

        transform = _make_mock_transform(node_id="t1", on_error="error-sink")
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})
        ctx.state_id = "state-123"

        llm_error = LLMClientError("rate limited", retryable=True)
        # Mock record_routing_event since we don't have a real state_id in DB
        with (
            patch.object(processor._transform_executor, "execute_transform", side_effect=llm_error),
            patch.object(recorder, "record_routing_event"),
        ):
            result, _out_token, error_sink = processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )

        assert result.status == "error"
        assert error_sink == "error-sink"

    def test_retryable_llm_error_with_missing_error_edge_raises(self) -> None:
        """Retryable error with named sink but no DIVERT edge → OrchestrationInvariantError."""
        _, _, processor = self._setup()
        # No error edges configured
        processor._error_edge_ids = {}

        transform = _make_mock_transform(node_id="t1", on_error="error-sink")
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})
        ctx.state_id = "state-123"

        llm_error = LLMClientError("rate limited", retryable=True)
        with (
            patch.object(
                processor._transform_executor,
                "execute_transform",
                side_effect=llm_error,
            ),
            pytest.raises(OrchestrationInvariantError, match="no DIVERT edge"),
        ):
            processor._execute_transform_with_retry(
                transform=transform,
                token=token,
                ctx=ctx,
                step=1,
            )


# =============================================================================
# _execute_transform_with_retry: With retry manager
# =============================================================================


class TestExecuteTransformWithRetry:
    """Tests for _execute_transform_with_retry when retry_manager IS configured."""

    def test_delegates_to_retry_manager(self) -> None:
        """With retry_manager, delegates to execute_with_retry."""
        _, recorder = _make_recorder()

        retry_manager = Mock(spec=RetryManager)
        processor = _make_processor(recorder, retry_manager=retry_manager)

        expected = (
            TransformResult.success(make_row({"value": 42}), success_reason={"action": "test"}),
            make_token_info(data={"value": 42}),
            None,
        )
        retry_manager.execute_with_retry.return_value = expected

        transform = _make_mock_transform()
        token = make_token_info(data={"value": 42})
        ctx = PluginContext(run_id="test-run", config={})

        result = processor._execute_transform_with_retry(
            transform=transform,
            token=token,
            ctx=ctx,
            step=1,
        )

        retry_manager.execute_with_retry.assert_called_once()
        assert result == expected

    def test_is_retryable_accepts_retryable_llm_error(self) -> None:
        """is_retryable callback returns True for retryable LLMClientError."""
        _, recorder = _make_recorder()

        retry_manager = Mock(spec=RetryManager)
        processor = _make_processor(recorder, retry_manager=retry_manager)

        # Capture the is_retryable callback
        retry_manager.execute_with_retry.return_value = (
            TransformResult.success(make_row({}), success_reason={"action": "t"}),
            make_token_info(),
            None,
        )

        transform = _make_mock_transform()
        token = make_token_info()
        ctx = PluginContext(run_id="test-run", config={})

        processor._execute_transform_with_retry(
            transform=transform,
            token=token,
            ctx=ctx,
            step=1,
        )

        # Extract the is_retryable callback from the call
        call_kwargs = retry_manager.execute_with_retry.call_args
        is_retryable = call_kwargs.kwargs.get("is_retryable") or call_kwargs[1].get("is_retryable")
        if is_retryable is None:
            # Might be positional
            is_retryable = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs.kwargs["is_retryable"]

        # Verify retryable logic
        assert is_retryable(LLMClientError("rate limit", retryable=True)) is True
        assert is_retryable(LLMClientError("content policy", retryable=False)) is False
        assert is_retryable(ConnectionError("conn reset")) is True
        assert is_retryable(TimeoutError("timeout")) is True
        assert is_retryable(AttributeError("bug")) is False
        assert is_retryable(TypeError("bug")) is False


# =============================================================================
# _maybe_coalesce_token
# =============================================================================


class TestMaybeCoalesceToken:
    """Tests for _maybe_coalesce_token branch routing."""

    def test_no_coalesce_executor_returns_not_handled(self) -> None:
        """Without coalesce_executor, always returns (False, None)."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder, coalesce_executor=None)
        token = make_token_info()

        handled, result = processor._maybe_coalesce_token(
            token,
            current_node_id=NodeID("coalesce::merge"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name=CoalesceName("merge"),
            child_items=[],
        )

        assert handled is False
        assert result is None

    def test_token_without_branch_returns_not_handled(self) -> None:
        """Token without branch_name is not a fork child, skip coalesce."""
        _, recorder = _make_recorder()
        coalesce = Mock()
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            coalesce_step_map={CoalesceName("merge"): 1},
        )
        token = make_token_info()
        # Ensure branch_name is None
        token = TokenInfo(
            row_id=token.row_id,
            token_id=token.token_id,
            row_data=token.row_data,
            branch_name=None,
        )

        handled, _result = processor._maybe_coalesce_token(
            token,
            current_node_id=NodeID("coalesce::merge"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name=CoalesceName("merge"),
            child_items=[],
        )

        assert handled is False

    def test_current_node_not_coalesce_node_returns_not_handled(self) -> None:
        """Coalesce is only triggered when traversal reaches the coalesce node."""
        _, recorder = _make_recorder()
        coalesce = Mock()
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            coalesce_step_map={CoalesceName("merge"): 5},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        handled, _result = processor._maybe_coalesce_token(
            token,
            current_node_id=NodeID("transform-3"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name=CoalesceName("merge"),
            child_items=[],
        )

        assert handled is False

    def test_coalesce_held_returns_handled_with_none(self) -> None:
        """Token accepted but not all branches arrived → handled=True, result=None."""
        _, recorder = _make_recorder()
        coalesce = Mock()
        coalesce.accept.return_value = Mock(held=True, merged_token=None)
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            coalesce_step_map={CoalesceName("merge"): 2},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        handled, result = processor._maybe_coalesce_token(
            token,
            current_node_id=NodeID("coalesce::merge"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name=CoalesceName("merge"),
            child_items=[],
        )

        assert handled is True
        assert result is None

    def test_coalesce_merged_at_terminal_returns_coalesced_result(self) -> None:
        """All branches arrived at terminal coalesce → COALESCED result."""
        _, recorder = _make_recorder()
        merged_token = make_token_info(data={"merged": True})
        coalesce = Mock()
        coalesce.accept.return_value = Mock(held=False, merged_token=merged_token)
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            coalesce_step_map={CoalesceName("merge"): 3},
            coalesce_on_success_map={CoalesceName("merge"): "output"},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        handled, result = processor._maybe_coalesce_token(
            token,
            current_node_id=NodeID("coalesce::merge"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name=CoalesceName("merge"),
            child_items=[],
        )

        assert handled is True
        assert result is not None
        assert result.outcome == RowOutcome.COALESCED

    def test_coalesce_merged_at_non_terminal_queues_work(self) -> None:
        """Merged at non-terminal step → child work item added, no result."""
        _, recorder = _make_recorder()
        merged_token = make_token_info(data={"merged": True})
        coalesce = Mock()
        coalesce.accept.return_value = Mock(held=False, merged_token=merged_token)
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            coalesce_step_map={CoalesceName("merge"): 2},
            node_to_next={NodeID("coalesce::merge"): NodeID("transform-5")},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )
        child_items: list[_WorkItem] = []

        handled, result = processor._maybe_coalesce_token(
            token,
            current_node_id=NodeID("coalesce::merge"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name=CoalesceName("merge"),
            child_items=child_items,
        )

        assert handled is True
        assert result is None
        assert len(child_items) == 1
        assert processor._node_id_to_step(child_items[0].current_node_id) == 2


# =============================================================================
# _notify_coalesce_of_lost_branch
# =============================================================================


class TestNotifyCoalesceOfLostBranch:
    """Tests for the branch loss notification to coalesce executor."""

    def test_no_coalesce_executor_returns_empty(self) -> None:
        """Without coalesce_executor, returns empty list."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder, coalesce_executor=None)
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        results = processor._notify_coalesce_of_lost_branch(
            token,
            "quarantined:bad_value",
            [],
        )

        assert results == []

    def test_token_without_branch_returns_empty(self) -> None:
        """Non-forked token → no coalesce notification needed."""
        _, recorder = _make_recorder()
        coalesce = Mock()
        processor = _make_processor(recorder, coalesce_executor=coalesce)
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name=None,
        )

        results = processor._notify_coalesce_of_lost_branch(
            token,
            "quarantined:bad_value",
            [],
        )

        assert results == []

    def test_branch_not_in_coalesce_map_returns_empty(self) -> None:
        """Branch without coalesce mapping → no notification."""
        _, recorder = _make_recorder()
        coalesce = Mock()
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            branch_to_coalesce={},  # Empty map
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="unmapped_branch",
        )

        results = processor._notify_coalesce_of_lost_branch(
            token,
            "quarantined:bad_value",
            [],
        )

        assert results == []

    def test_lost_branch_with_failure_returns_sibling_results(self) -> None:
        """Branch loss causing coalesce failure returns FAILED sibling results."""
        _, recorder = _make_recorder()
        coalesce = Mock()
        sibling_token = make_token_info(data={"value": 99})
        coalesce.notify_branch_lost.return_value = Mock(
            merged_token=None,
            failure_reason="not enough branches",
            consumed_tokens=[sibling_token],
        )
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            branch_to_coalesce={BranchName("path_a"): CoalesceName("merge")},
            coalesce_step_map={CoalesceName("merge"): 3},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        results = processor._notify_coalesce_of_lost_branch(
            token,
            "quarantined:bad_value",
            [],
        )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.FAILED
        assert results[0].error is not None
        assert "not enough branches" in results[0].error.message

    def test_lost_branch_triggers_terminal_merge(self) -> None:
        """Branch loss triggers merge at terminal coalesce → COALESCED result."""
        _, recorder = _make_recorder()
        merged_token = make_token_info(data={"merged": True})
        coalesce = Mock()
        coalesce.notify_branch_lost.return_value = Mock(
            merged_token=merged_token,
            failure_reason=None,
            consumed_tokens=[],
        )
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            branch_to_coalesce={BranchName("path_a"): CoalesceName("merge")},
            coalesce_step_map={CoalesceName("merge"): 5},
            coalesce_on_success_map={CoalesceName("merge"): "output"},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        results = processor._notify_coalesce_of_lost_branch(
            token,
            "quarantined:bad_value",
            [],
        )

        assert len(results) == 1
        assert results[0].outcome == RowOutcome.COALESCED

    def test_lost_branch_triggers_nonterminal_merge_queues_work(self) -> None:
        """Branch loss triggers merge at non-terminal step → queues work."""
        _, recorder = _make_recorder()
        merged_token = make_token_info(data={"merged": True})
        coalesce = Mock()
        coalesce.notify_branch_lost.return_value = Mock(
            merged_token=merged_token,
            failure_reason=None,
            consumed_tokens=[],
        )
        child_items: list[_WorkItem] = []
        processor = _make_processor(
            recorder,
            coalesce_executor=coalesce,
            branch_to_coalesce={BranchName("path_a"): CoalesceName("merge")},
            coalesce_step_map={CoalesceName("merge"): 3},
            node_to_next={NodeID("coalesce::merge"): NodeID("transform-4")},
        )
        token = TokenInfo(
            row_id="row-1",
            token_id="token-1",
            row_data=make_row({}),
            branch_name="path_a",
        )

        results = processor._notify_coalesce_of_lost_branch(
            token,
            "quarantined:bad_value",
            child_items,
        )

        assert results == []
        assert len(child_items) == 1
        assert processor._node_id_to_step(child_items[0].current_node_id) == 3


# =============================================================================
# Unknown transform type
# =============================================================================


class TestUnknownTransformType:
    """Tests for the TypeError guard on unknown transform types."""

    def test_unknown_type_raises_type_error(self) -> None:
        """Transform that is neither TransformProtocol nor GateProtocol raises TypeError."""
        _db, recorder = _make_recorder()

        processor = _make_processor(recorder)
        source_row = _make_source_row()
        ctx = PluginContext(run_id="test-run", config={})

        # Create an object that is NOT a transform or gate
        class FakePlugin:
            pass

        with pytest.raises(TypeError, match="Unknown transform type"):
            processor.process_row(
                row_index=0,
                source_row=source_row,
                transforms=[FakePlugin()],
                ctx=ctx,
            )


# =============================================================================
# Aggregation facades (thin delegation tests)
# =============================================================================


class TestAggregationFacades:
    """Tests for the aggregation public facade methods."""

    def test_check_aggregation_timeout_delegates(self) -> None:
        """check_aggregation_timeout delegates to aggregation_executor."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)

        with patch.object(
            processor._aggregation_executor,
            "check_flush_status",
            return_value=(True, TriggerType.TIMEOUT),
        ):
            should_flush, trigger = processor.check_aggregation_timeout(NodeID("agg-1"))

        assert should_flush is True
        assert trigger == TriggerType.TIMEOUT

    def test_get_aggregation_buffer_count_delegates(self) -> None:
        """get_aggregation_buffer_count delegates to aggregation_executor."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)

        with patch.object(
            processor._aggregation_executor,
            "get_buffer_count",
            return_value=5,
        ):
            count = processor.get_aggregation_buffer_count(NodeID("agg-1"))

        assert count == 5

    def test_get_aggregation_checkpoint_state_delegates(self) -> None:
        """get_aggregation_checkpoint_state delegates to aggregation_executor."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)

        checkpoint = {"agg-1": {"buffer": [], "trigger_state": {}}}
        with patch.object(
            processor._aggregation_executor,
            "get_checkpoint_state",
            return_value=checkpoint,
        ):
            result = processor.get_aggregation_checkpoint_state()

        assert result == checkpoint


# =============================================================================
# Telemetry emission (optional)
# =============================================================================


class TestTelemetryEmission:
    """Tests for telemetry emission behavior."""

    def test_no_telemetry_manager_does_not_crash(self) -> None:
        """Without telemetry_manager, _emit_telemetry is a no-op."""
        _, recorder = _make_recorder()
        processor = _make_processor(recorder)
        # Should not raise
        processor._emit_telemetry(Mock())

    def test_telemetry_manager_receives_events(self) -> None:
        """With telemetry_manager, events are forwarded."""
        _, recorder = _make_recorder()

        telemetry = Mock()
        processor = _make_processor(recorder, telemetry_manager=telemetry)

        event = Mock()
        processor._emit_telemetry(event)
        telemetry.handle_event.assert_called_once_with(event)
