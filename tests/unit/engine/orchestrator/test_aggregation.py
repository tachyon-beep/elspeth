# tests/unit/engine/orchestrator/test_aggregation.py
"""Tests for aggregation handling functions in the orchestrator.

aggregation.py handles:
- Finding batch-aware transforms by node ID
- Recovering incomplete batches after crash
- Checking and flushing aggregation timeouts (pre-row)
- Flushing remaining buffers at end-of-source

These are pure delegation functions — no internal state — tested via mocks.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.enums import BatchStatus, TriggerType
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.types import NodeID
from elspeth.engine.orchestrator.aggregation import (
    _route_aggregation_outcome,
    check_aggregation_timeouts,
    find_aggregation_transform,
    flush_remaining_aggregation_buffers,
    handle_incomplete_batches,
)
from elspeth.engine.orchestrator.types import PipelineConfig
from elspeth.plugins.protocols import TransformProtocol
from elspeth.testing import make_row, make_token_info

# =============================================================================
# Helpers
# =============================================================================


def _make_batch_transform(*, node_id: str, is_batch_aware: bool = True) -> Mock:
    """Create a mock transform satisfying TransformProtocol with batch awareness."""
    from elspeth.plugins.protocols import TransformProtocol

    transform = Mock(spec=TransformProtocol)
    transform.node_id = node_id
    transform.is_batch_aware = is_batch_aware
    transform.name = f"transform-{node_id}"
    return transform


def _make_config(
    *,
    transforms: list[Any] | None = None,
    aggregation_settings: dict[str, Any] | None = None,
) -> PipelineConfig:
    """Build a minimal PipelineConfig for aggregation tests."""
    source = Mock()
    source.name = "test-source"
    return PipelineConfig(
        source=source,
        transforms=transforms or [],
        sinks={"output": Mock()},
        aggregation_settings=aggregation_settings or {},
    )


def _make_agg_settings(*, name: str = "batch_agg") -> Mock:
    settings = Mock()
    settings.name = name
    return settings


def _make_result(
    outcome: RowOutcome,
    *,
    token: TokenInfo | None = None,
    sink_name: str | None = None,
) -> Mock:
    result = Mock()
    result.outcome = outcome
    result.token = token or make_token_info()
    result.sink_name = sink_name
    return result


def _make_work_item(
    *,
    token: TokenInfo | None = None,
    current_node_id: NodeID | None = None,
    coalesce_node_id: NodeID | None = None,
    coalesce_name: str | None = None,
) -> Mock:
    item = Mock()
    item.token = token or make_token_info()
    item.current_node_id = current_node_id if current_node_id is not None else NodeID("node-0")
    item.coalesce_node_id = coalesce_node_id
    item.coalesce_name = coalesce_name
    return item


def _make_pending() -> dict[str, list[tuple[TokenInfo, PendingOutcome | None]]]:
    return {"output": []}


# =============================================================================
# find_aggregation_transform
# =============================================================================


class TestFindAggregationTransform:
    """Tests for find_aggregation_transform()."""

    def test_finds_batch_aware_transform(self) -> None:
        """Returns transform and aggregation node ID for matching node_id."""
        t = _make_batch_transform(node_id="agg-node-1")
        config = _make_config(transforms=[Mock(), t, Mock()])

        result_transform, result_node_id = find_aggregation_transform(config, "agg-node-1", "batch1")

        assert result_transform is t
        assert result_node_id == NodeID("agg-node-1")

    def test_non_batch_aware_skipped(self) -> None:
        """Transform with is_batch_aware=False is not matched."""
        t = _make_batch_transform(node_id="agg-node-1", is_batch_aware=False)
        config = _make_config(transforms=[t])

        with pytest.raises(RuntimeError, match="No batch-aware transform"):
            find_aggregation_transform(config, "agg-node-1", "batch1")

    def test_wrong_node_id_skipped(self) -> None:
        """Transform with different node_id is not matched."""
        t = _make_batch_transform(node_id="other-node")
        config = _make_config(transforms=[t])

        with pytest.raises(RuntimeError, match="No batch-aware transform"):
            find_aggregation_transform(config, "agg-node-1", "batch1")

    def test_no_transforms_raises(self) -> None:
        """Empty transforms list raises with helpful error."""
        config = _make_config(transforms=[])

        with pytest.raises(RuntimeError, match="No batch-aware transform"):
            find_aggregation_transform(config, "agg-node-1", "batch1")

    def test_error_includes_aggregation_name(self) -> None:
        """Error message includes the aggregation name for debugging."""
        config = _make_config(transforms=[])

        with pytest.raises(RuntimeError, match="my_aggregation"):
            find_aggregation_transform(config, "agg-node-1", "my_aggregation")

    def test_error_lists_available_transforms(self) -> None:
        """Error message lists available transform node IDs."""
        t = _make_batch_transform(node_id="other")
        config = _make_config(transforms=[t])

        with pytest.raises(RuntimeError, match="other"):
            find_aggregation_transform(config, "agg-node-1", "batch1")

    def test_first_matching_transform_returned(self) -> None:
        """If multiple transforms match (shouldn't happen), first wins."""
        t1 = _make_batch_transform(node_id="agg-node-1")
        t2 = _make_batch_transform(node_id="agg-node-1")
        config = _make_config(transforms=[t1, t2])

        result_transform, result_node_id = find_aggregation_transform(config, "agg-node-1", "batch1")

        assert result_transform is t1
        assert result_node_id == NodeID("agg-node-1")


# =============================================================================
# handle_incomplete_batches
# =============================================================================


class TestHandleIncompleteBatches:
    """Tests for crash recovery of incomplete batches."""

    def test_executing_batch_marked_failed_then_retried(self) -> None:
        """EXECUTING batch (crash interrupted) -> failed -> retried."""
        batch = Mock()
        batch.status = BatchStatus.EXECUTING
        batch.batch_id = "batch-123"

        recorder = Mock()
        recorder.get_incomplete_batches.return_value = [batch]

        handle_incomplete_batches(recorder, "run-1")

        recorder.update_batch_status.assert_called_once_with("batch-123", BatchStatus.FAILED)
        recorder.retry_batch.assert_called_once_with("batch-123")

    def test_failed_batch_retried(self) -> None:
        """FAILED batch is retried directly."""
        batch = Mock()
        batch.status = BatchStatus.FAILED
        batch.batch_id = "batch-456"

        recorder = Mock()
        recorder.get_incomplete_batches.return_value = [batch]

        handle_incomplete_batches(recorder, "run-1")

        recorder.update_batch_status.assert_not_called()
        recorder.retry_batch.assert_called_once_with("batch-456")

    def test_draft_batch_left_alone(self) -> None:
        """DRAFT batch continues collection — no action taken."""
        batch = Mock()
        batch.status = BatchStatus.DRAFT
        batch.batch_id = "batch-789"

        recorder = Mock()
        recorder.get_incomplete_batches.return_value = [batch]

        handle_incomplete_batches(recorder, "run-1")

        recorder.update_batch_status.assert_not_called()
        recorder.retry_batch.assert_not_called()

    def test_no_incomplete_batches(self) -> None:
        """No incomplete batches means no action."""
        recorder = Mock()
        recorder.get_incomplete_batches.return_value = []

        handle_incomplete_batches(recorder, "run-1")

        recorder.update_batch_status.assert_not_called()
        recorder.retry_batch.assert_not_called()

    def test_multiple_batches_handled_independently(self) -> None:
        """Each batch handled according to its own status."""
        executing = Mock(status=BatchStatus.EXECUTING, batch_id="b1")
        failed = Mock(status=BatchStatus.FAILED, batch_id="b2")
        draft = Mock(status=BatchStatus.DRAFT, batch_id="b3")

        recorder = Mock()
        recorder.get_incomplete_batches.return_value = [executing, failed, draft]

        handle_incomplete_batches(recorder, "run-1")

        assert recorder.update_batch_status.call_count == 1
        assert recorder.retry_batch.call_count == 2


# =============================================================================
# check_aggregation_timeouts
# =============================================================================


class TestCheckAggregationTimeouts:
    """Tests for pre-row aggregation timeout checks."""

    def test_no_aggregation_settings_returns_zero_result(self) -> None:
        """No aggregation settings means nothing to check."""
        config = _make_config(aggregation_settings={})
        processor = Mock()
        pending = _make_pending()

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 0
        assert result.rows_failed == 0

    def test_no_flush_needed_returns_zero(self) -> None:
        """Timeout check says no flush needed — nothing happens."""
        config = _make_config(aggregation_settings={"agg-1": _make_agg_settings()})
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (False, None)
        pending = _make_pending()

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 0

    def test_count_trigger_skipped(self) -> None:
        """Count triggers are handled in buffer_row — skip in pre-row check."""
        config = _make_config(aggregation_settings={"agg-1": _make_agg_settings()})
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.COUNT)
        pending = _make_pending()

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 0

    def test_condition_trigger_flushes_pre_row(self) -> None:
        """Condition triggers that are time-based must flush before next row.

        P1-2026-02-05: Condition triggers like 'batch_age_seconds >= 5' can
        become true between rows. They must be treated like timeout triggers
        for pre-row flush, and the actual trigger_type must be passed through
        (not hardcoded as TIMEOUT).
        """
        token = make_token_info()
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.CONDITION)
        processor.get_aggregation_buffer_count.return_value = 3
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        # Condition trigger should flush (not be skipped)
        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

        # Verify actual trigger_type is passed (not hardcoded TIMEOUT)
        call_kwargs = processor.handle_timeout_flush.call_args.kwargs
        assert call_kwargs["trigger_type"] == TriggerType.CONDITION

    def test_empty_buffer_skipped(self) -> None:
        """Timeout fires but buffer is empty — nothing to flush."""
        config = _make_config(aggregation_settings={"agg-1": _make_agg_settings()})
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 0
        pending = _make_pending()

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 0
        processor.handle_timeout_flush.assert_not_called()

    def test_timeout_flush_completed_results(self) -> None:
        """Timeout flush produces completed tokens routed to sink."""
        token = make_token_info()
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 5
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

    def test_timeout_flush_failed_results(self) -> None:
        """Failed results from flush increment failed counter."""
        failed = Mock(outcome=RowOutcome.FAILED)

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 3
        processor.handle_timeout_flush.return_value = ([failed], [])

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_failed == 1
        assert result.rows_succeeded == 0

    def test_work_items_continue_processing(self) -> None:
        """Work items from flush continue through remaining transforms."""
        work_token = make_token_info()
        work_item = _make_work_item(token=work_token, current_node_id=NodeID("continue-node"))
        downstream_result = _make_result(RowOutcome.COMPLETED, token=work_token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform, Mock()],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 2
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [downstream_result]

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_succeeded == 1
        processor.process_token.assert_called_once()
        assert processor.process_token.call_args.kwargs["current_node_id"] == NodeID("continue-node")

    def test_work_items_with_coalesce_node(self) -> None:
        """Work items can carry an explicit coalesce node continuation."""
        work_item = _make_work_item(
            current_node_id=NodeID("continue-node"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name="merge",
        )

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform, Mock(), Mock()],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = []

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert processor.process_token.call_args.kwargs["current_node_id"] == NodeID("continue-node")
        assert processor.process_token.call_args.kwargs["coalesce_node_id"] == NodeID("coalesce::merge")
        assert processor.process_token.call_args.kwargs["coalesce_name"] == "merge"

    def test_downstream_routed_outcome(self) -> None:
        """ROUTED outcome from downstream is tracked."""
        work_item = _make_work_item()
        routed = _make_result(RowOutcome.ROUTED, sink_name="risk_sink")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [routed]

        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "risk_sink": []}
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_routed == 1
        assert result.routed_destinations == {"risk_sink": 1}
        assert len(pending["risk_sink"]) == 1

    def test_downstream_quarantined_outcome(self) -> None:
        """QUARANTINED outcome from downstream is counted."""
        work_item = _make_work_item()
        quarantined = _make_result(RowOutcome.QUARANTINED)

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [quarantined]

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_quarantined == 1

    def test_downstream_coalesced_outcome(self) -> None:
        """COALESCED outcome increments both coalesced and succeeded."""
        work_item = _make_work_item()
        coalesced = _make_result(RowOutcome.COALESCED, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [coalesced]

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_coalesced == 1
        assert result.rows_succeeded == 1

    def test_downstream_failed_in_timeout(self) -> None:
        """FAILED downstream outcome from work items in timeout check."""
        work_item = _make_work_item()
        failed = _make_result(RowOutcome.FAILED)

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [failed]

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_failed == 1

    def test_downstream_completed_branch_fallback_in_timeout(self) -> None:
        """COMPLETED work item with unknown branch routes to sink_name from result."""
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="unknown")
        work_item = _make_work_item(token=token)
        completed = _make_result(RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [completed]

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

    def test_downstream_forked_expanded_buffered(self) -> None:
        """FORKED, EXPANDED, BUFFERED outcomes each tracked separately."""
        work_item = _make_work_item()
        outcomes = [
            _make_result(RowOutcome.FORKED),
            _make_result(RowOutcome.EXPANDED),
            _make_result(RowOutcome.BUFFERED),
        ]

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = outcomes

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_forked == 1
        assert result.rows_expanded == 1
        assert result.rows_buffered == 1

    def test_completed_result_branch_fallback_in_timeout(self) -> None:
        """Completed result with branch not in pending routes to sink_name from result."""
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="missing_sink")
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()
        lookup: dict[str, tuple[TransformProtocol, NodeID]] = {"agg-1": (agg_transform, NodeID("agg-1"))}

        result = check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=lookup,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

    def test_fallback_lookup_when_no_cache(self) -> None:
        """Without agg_transform_lookup, find_aggregation_transform is called."""
        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.check_aggregation_timeout.return_value = (True, TriggerType.TIMEOUT)
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [])

        pending = _make_pending()

        # No lookup passed — function should find the transform itself
        check_aggregation_timeouts(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            agg_transform_lookup=None,
        )

        processor.handle_timeout_flush.assert_called_once()


# =============================================================================
# flush_remaining_aggregation_buffers
# =============================================================================


class TestFlushRemainingAggregationBuffers:
    """Tests for end-of-source aggregation buffer flush."""

    def test_empty_buffer_skipped(self) -> None:
        """Aggregation with empty buffer is skipped."""
        config = _make_config(aggregation_settings={"agg-1": _make_agg_settings()})
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 0
        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 0
        processor.handle_timeout_flush.assert_not_called()

    def test_flush_completed_results(self) -> None:
        """Completed results from flush go to sink."""
        token = make_token_info()
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 3
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

    def test_checkpoint_callback_called_for_completed(self) -> None:
        """checkpoint_callback is invoked for each completed token."""
        token = make_token_info()
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()
        callback = Mock()

        flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            checkpoint_callback=callback,
        )

        callback.assert_called_once_with(token)

    def test_checkpoint_callback_not_called_for_failed(self) -> None:
        """checkpoint_callback is NOT invoked for failed tokens."""
        failed = Mock(outcome=RowOutcome.FAILED)

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([failed], [])

        pending = _make_pending()
        callback = Mock()

        flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            checkpoint_callback=callback,
        )

        callback.assert_not_called()

    def test_uses_end_of_source_trigger(self) -> None:
        """Flush uses END_OF_SOURCE trigger type."""
        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [])

        pending = _make_pending()

        flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        call_kwargs = processor.handle_timeout_flush.call_args.kwargs
        assert call_kwargs["trigger_type"] == TriggerType.END_OF_SOURCE

    def test_work_items_continue_downstream(self) -> None:
        """Work items from flush continue through remaining transforms."""
        work_token = make_token_info()
        work_item = _make_work_item(token=work_token, current_node_id=NodeID("continue-node"))
        downstream = _make_result(RowOutcome.COMPLETED, token=work_token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform, Mock()],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [downstream]

        pending = _make_pending()
        callback = Mock()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            checkpoint_callback=callback,
        )

        assert result.rows_succeeded == 1
        callback.assert_called_once_with(work_token)

    def test_downstream_routed_with_checkpoint(self) -> None:
        """ROUTED downstream outcome triggers checkpoint callback."""
        work_item = _make_work_item()
        routed = _make_result(RowOutcome.ROUTED, sink_name="risk")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [routed]

        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "risk": []}
        callback = Mock()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            checkpoint_callback=callback,
        )

        assert result.rows_routed == 1
        callback.assert_called_once()

    def test_downstream_coalesced_with_checkpoint(self) -> None:
        """COALESCED downstream outcome increments both counters + checkpoint."""
        work_item = _make_work_item()
        coalesced = _make_result(RowOutcome.COALESCED, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [coalesced]

        pending = _make_pending()
        callback = Mock()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            checkpoint_callback=callback,
        )

        assert result.rows_coalesced == 1
        assert result.rows_succeeded == 1
        callback.assert_called_once()

    def test_no_callback_when_none(self) -> None:
        """No crash when checkpoint_callback is None."""
        token = make_token_info()
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()

        # No crash — checkpoint_callback=None is valid
        flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
            checkpoint_callback=None,
        )

    def test_branch_routing_for_completed_tokens(self) -> None:
        """Completed tokens route via result.sink_name, not branch_name."""
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="path_a")
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]] = {"output": [], "path_a": []}

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 1
        assert len(pending["path_a"]) == 0
        assert len(pending["output"]) == 1

    def test_downstream_failed_in_flush(self) -> None:
        """FAILED outcome from downstream work items counted in flush."""
        work_item = _make_work_item()
        failed = _make_result(RowOutcome.FAILED)

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [failed]

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_failed == 1

    def test_downstream_completed_branch_fallback_in_flush(self) -> None:
        """COMPLETED work item with unknown branch routes to sink_name from result."""
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="unknown")
        work_item = _make_work_item(token=token)
        completed = _make_result(RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [completed]

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

    def test_downstream_quarantined_in_flush(self) -> None:
        """QUARANTINED outcome from downstream work items counted in flush."""
        work_item = _make_work_item()
        quarantined = _make_result(RowOutcome.QUARANTINED)

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = [quarantined]

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_quarantined == 1

    def test_downstream_forked_expanded_buffered_in_flush(self) -> None:
        """FORKED, EXPANDED, BUFFERED outcomes from work items tracked in flush."""
        work_item = _make_work_item()
        outcomes = [
            _make_result(RowOutcome.FORKED),
            _make_result(RowOutcome.EXPANDED),
            _make_result(RowOutcome.BUFFERED),
        ]

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = outcomes

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_forked == 1
        assert result.rows_expanded == 1
        assert result.rows_buffered == 1

    def test_work_item_with_coalesce_node_in_flush(self) -> None:
        """Work items with coalesce_node_id preserve continuation metadata in flush."""
        work_item = _make_work_item(
            current_node_id=NodeID("continue-node"),
            coalesce_node_id=NodeID("coalesce::merge"),
            coalesce_name="merge",
        )

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform, Mock(), Mock()],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([], [work_item])
        processor.process_token.return_value = []

        pending = _make_pending()

        flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert processor.process_token.call_args.kwargs["current_node_id"] == NodeID("continue-node")
        assert processor.process_token.call_args.kwargs["coalesce_node_id"] == NodeID("coalesce::merge")

    def test_completed_result_branch_fallback_to_sink_name(self) -> None:
        """Completed result with branch not in pending routes to sink_name from result."""
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="missing")
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1

    def test_branch_routing_falls_back_to_sink_name(self) -> None:
        """Branch name not in pending_tokens routes to sink_name from result."""
        token = TokenInfo(row_id="row-1", token_id="tok-1", row_data=make_row({}), branch_name="nonexistent")
        completed = Mock(outcome=RowOutcome.COMPLETED, token=token, sink_name="output")

        agg_transform = _make_batch_transform(node_id="agg-1")
        config = _make_config(
            transforms=[agg_transform],
            aggregation_settings={"agg-1": _make_agg_settings()},
        )
        processor = Mock()
        processor.get_aggregation_buffer_count.return_value = 1
        processor.handle_timeout_flush.return_value = ([completed], [])

        pending = _make_pending()

        result = flush_remaining_aggregation_buffers(
            config=config,
            processor=processor,
            ctx=Mock(),
            pending_tokens=pending,
        )

        assert result.rows_succeeded == 1
        assert len(pending["output"]) == 1


# =============================================================================
# _route_aggregation_outcome invariant tests
# =============================================================================


class TestRouteAggregationOutcome:
    """Tests for _route_aggregation_outcome() fail-closed safety check."""

    def test_routes_to_known_sink(self) -> None:
        """Successfully routes result to a known sink in pending_tokens."""
        result = _make_result(RowOutcome.COMPLETED, sink_name="output")
        pending = _make_pending()

        _route_aggregation_outcome(result, pending)

        assert len(pending["output"]) == 1
        assert pending["output"][0][0] == result.token

    def test_unknown_sink_raises_invariant_error(self) -> None:
        """Raises OrchestrationInvariantError when sink_name is not in pending_tokens."""
        result = _make_result(RowOutcome.COMPLETED, sink_name="nonexistent")
        pending = _make_pending()

        with pytest.raises(OrchestrationInvariantError, match="not in configured sinks"):
            _route_aggregation_outcome(result, pending)

    def test_missing_sink_name_raises_invariant_error(self) -> None:
        """Missing sink_name must fail closed with invariant error."""
        result = _make_result(RowOutcome.COMPLETED, sink_name=None)
        pending = _make_pending()

        with pytest.raises(OrchestrationInvariantError, match="missing sink_name"):
            _route_aggregation_outcome(result, pending)

    def test_invokes_checkpoint_callback(self) -> None:
        """Calls checkpoint_callback with the routed token after successful routing."""
        result = _make_result(RowOutcome.COMPLETED, sink_name="output")
        pending = _make_pending()
        callback = Mock()

        _route_aggregation_outcome(result, pending, checkpoint_callback=callback)

        callback.assert_called_once_with(result.token)
