"""Tests for SinkExecutor failsink routing.

Tests the critical path: after sink.write() returns a SinkWriteResult with
diversions, the executor must record correct per-token outcomes and write
diverted rows to the failsink (or record discard).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from elspeth.contracts import PendingOutcome, RowOutcome, TokenInfo
from elspeth.contracts.diversion import RowDiversion, SinkWriteResult
from elspeth.contracts.enums import NodeStateStatus, RoutingMode
from elspeth.contracts.results import ArtifactDescriptor
from elspeth.engine.executors.sink import SinkExecutor


def _make_token(token_id: str = "tok-1", row_data: dict | None = None) -> MagicMock:
    """Create a minimal TokenInfo mock."""
    token = MagicMock(spec=TokenInfo)
    token.token_id = token_id
    token.row_id = f"row-{token_id}"
    mock_row = MagicMock()
    mock_row.to_dict.return_value = row_data or {"field": "value"}
    mock_row.contract = MagicMock()
    mock_row.contract.merge.return_value = mock_row.contract
    token.row_data = mock_row
    return token


def _make_artifact(path: str = "/tmp/test") -> ArtifactDescriptor:
    return ArtifactDescriptor.for_file(path=path, content_hash="a" * 64, size_bytes=100)


def _make_sink(
    name: str = "primary",
    node_id: str = "node-primary",
    diversions: tuple[RowDiversion, ...] = (),
    on_write_failure: str = "discard",
) -> MagicMock:
    sink = MagicMock()
    sink.name = name
    sink.node_id = node_id
    sink.validate_input = False
    sink.declared_required_fields = frozenset()
    sink.write.return_value = SinkWriteResult(
        artifact=_make_artifact(),
        diversions=diversions,
    )
    sink._on_write_failure = on_write_failure
    sink._reset_diversion_log = MagicMock()
    return sink


def _make_failsink(name: str = "csv_failsink", node_id: str = "node-failsink") -> MagicMock:
    failsink = MagicMock()
    failsink.name = name
    failsink.node_id = node_id
    failsink.write.return_value = SinkWriteResult(artifact=_make_artifact("/tmp/failsink"))
    failsink._reset_diversion_log = MagicMock()
    return failsink


def _make_executor() -> tuple[SinkExecutor, MagicMock]:
    recorder = MagicMock()
    state_counter = [0]

    def _begin_state(**kwargs: Any) -> MagicMock:
        state_counter[0] += 1
        state = MagicMock()
        state.state_id = f"state-{state_counter[0]}"
        return state

    recorder.begin_node_state.side_effect = _begin_state
    recorder.allocate_operation_call_index = MagicMock(return_value=0)
    spans = MagicMock()
    spans.sink_span.return_value.__enter__ = MagicMock(return_value=None)
    spans.sink_span.return_value.__exit__ = MagicMock(return_value=False)
    executor = SinkExecutor(recorder, spans, "run-1")
    return executor, recorder


class TestNoDiversions:
    """Existing behavior preserved when no diversions occur."""

    def test_all_tokens_get_completed_outcome(self) -> None:
        executor, recorder = _make_executor()
        sink = _make_sink()
        tokens = [_make_token("t0"), _make_token("t1"), _make_token("t2")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert len(outcome_calls) == 3
        for c in outcome_calls:
            assert c.kwargs["outcome"] == RowOutcome.COMPLETED
            assert c.kwargs["sink_name"] == "primary"

    def test_no_failsink_write_called(self) -> None:
        executor, _recorder = _make_executor()
        sink = _make_sink()
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        failsink.write.assert_not_called()

    def test_returns_artifact_and_zero_diversions(self) -> None:
        executor, _recorder = _make_executor()
        sink = _make_sink()
        tokens = [_make_token("t0")]
        artifact, diversion_count = executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        assert artifact is not None
        assert diversion_count == 0


class TestDiscardMode:
    """on_write_failure='discard' — diverted rows are dropped with audit record."""

    def test_diverted_tokens_get_diverted_outcome(self) -> None:
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="bad metadata", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert len(outcome_calls) == 2
        # Build a lookup by token_id for order-independence
        outcomes_by_token = {c.kwargs["token_id"]: c.kwargs for c in outcome_calls}
        # t0 (index 0) → COMPLETED
        assert outcomes_by_token["t0"]["outcome"] == RowOutcome.COMPLETED
        assert outcomes_by_token["t0"]["sink_name"] == "primary"
        # t1 (index 1) → DIVERTED
        assert outcomes_by_token["t1"]["outcome"] == RowOutcome.DIVERTED
        assert outcomes_by_token["t1"]["error_hash"] is not None
        assert outcomes_by_token["t1"]["sink_name"] == "__discard__"

    def test_all_diverted_all_get_diverted(self) -> None:
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),
            RowDiversion(row_index=1, reason="bad", row_data={"x": 2}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert all(c.kwargs["outcome"] == RowOutcome.DIVERTED for c in outcome_calls)

    def test_returns_no_artifact_when_all_diverted(self) -> None:
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0")]
        artifact, diversion_count = executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        assert artifact is None
        assert diversion_count == 1


class TestFailsinkMode:
    """on_write_failure=<sink_name> — diverted rows are written to failsink."""

    def test_failsink_write_called_with_enriched_rows(self) -> None:
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="invalid metadata", row_data={"doc": "hello"}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        # Failsink should have been called with the diverted row
        failsink.write.assert_called_once()
        failsink_rows = failsink.write.call_args[0][0]
        assert len(failsink_rows) == 1
        assert "__diversion_reason" in failsink_rows[0]
        assert failsink_rows[0]["__diversion_reason"] == "invalid metadata"
        assert failsink_rows[0]["__diverted_from"] == "primary"
        assert "__diversion_timestamp" in failsink_rows[0]

    def test_failsink_flush_called(self) -> None:
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        failsink.flush.assert_called_once()

    def test_no_diversions_no_failsink_call(self) -> None:
        executor, _recorder = _make_executor()
        sink = _make_sink(diversions=(), on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
        )
        failsink.write.assert_not_called()

    def test_diverted_tokens_get_failsink_sink_name(self) -> None:
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        assert outcome_calls[0].kwargs["sink_name"] == "csv_failsink"

    def test_routing_event_recorded_for_diverted_tokens(self) -> None:
        """Failsink mode must record routing_event linking primary -> failsink."""
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad metadata", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        # routing_event must be called with DIVERT mode and the failsink edge
        recorder.record_routing_event.assert_called_once()
        call_kwargs = recorder.record_routing_event.call_args.kwargs
        assert call_kwargs["edge_id"] == "edge-failsink-1"
        assert call_kwargs["mode"] == RoutingMode.DIVERT
        assert "bad metadata" in call_kwargs["reason"]["diversion_reason"]

    def test_both_artifacts_registered_in_mixed_batch(self) -> None:
        """Mixed batch: primary artifact + failsink artifact both registered."""
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        # Both primary and failsink artifacts should be registered
        assert recorder.register_artifact.call_count == 2

    def test_node_states_opened_at_correct_nodes(self) -> None:
        """Primary tokens get states at primary node, diverted at failsink node."""
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0"), _make_token("t1")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        begin_calls = recorder.begin_node_state.call_args_list
        # 3 states: t0 at primary, t1 at primary (divert anchor), t1 at failsink
        assert len(begin_calls) == 3
        primary_calls = [c for c in begin_calls if c.kwargs["node_id"] == "node-primary"]
        failsink_calls = [c for c in begin_calls if c.kwargs["node_id"] == "node-failsink"]
        assert len(primary_calls) == 2  # t0 (written) + t1 (divert anchor)
        assert len(failsink_calls) == 1  # t1 (destination)


class TestFailsinkErrorHandling:
    def test_failsink_write_failure_crashes(self) -> None:
        """If failsink write fails, crash — it's the last resort."""
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        failsink.write.side_effect = OSError("disk full")
        tokens = [_make_token("t0")]
        with pytest.raises(OSError, match="disk full"):
            executor.write(
                sink=sink,
                tokens=tokens,
                ctx=MagicMock(run_id="run-1"),
                step_in_pipeline=5,
                sink_name="primary",
                pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
                failsink=failsink,
                failsink_name="csv_failsink",
                failsink_edge_id="edge-failsink-1",
            )


class TestFailsinkCleanup:
    """Verify node_state recording when failsink write/flush fails."""

    def test_failsink_write_failure_completes_failsink_states_as_failed(self) -> None:
        """When failsink.write() raises, no failsink node_states are opened.

        Batch: 1 token, 1 diversion. The failsink write crashes before
        begin_node_state is called for failsink states, so complete_node_state
        is never called with FAILED for the failsink node.
        """
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        failsink.write.side_effect = OSError("disk full")
        tokens = [_make_token("t0")]
        with pytest.raises(OSError):
            executor.write(
                sink=sink,
                tokens=tokens,
                ctx=MagicMock(run_id="run-1"),
                step_in_pipeline=5,
                sink_name="primary",
                pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
                failsink=failsink,
                failsink_name="csv_failsink",
                failsink_edge_id="edge-failsink-1",
            )
        # t0's primary divert state was opened (divert anchor), then failsink
        # write crashed. The cleanup marks the primary divert state as FAILED.
        complete_calls = recorder.complete_node_state.call_args_list
        failed_calls = [c for c in complete_calls if c.kwargs.get("status") == NodeStateStatus.FAILED]
        completed_calls = [c for c in complete_calls if c.kwargs.get("status") == NodeStateStatus.COMPLETED]
        assert len(failed_calls) == 1  # primary divert anchor cleaned up
        assert len(completed_calls) == 0
        # Primary divert state opened, but no failsink states (write crashed first)
        begin_calls = recorder.begin_node_state.call_args_list
        primary_begins = [c for c in begin_calls if c.kwargs.get("node_id") == sink.node_id]
        failsink_begins = [c for c in begin_calls if c.kwargs.get("node_id") == failsink.node_id]
        assert len(primary_begins) == 1  # divert anchor
        assert len(failsink_begins) == 0

    def test_failsink_failure_does_not_affect_primary_states(self) -> None:
        """Primary COMPLETED states remain intact when failsink fails.

        Batch: 2 tokens, 1 diversion at index 1.
        Expect: t0 COMPLETED at primary, t1 gets no failsink state (write crashes).
        """
        executor, recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        failsink.write.side_effect = OSError("disk full")
        tokens = [_make_token("t0"), _make_token("t1")]
        with pytest.raises(OSError):
            executor.write(
                sink=sink,
                tokens=tokens,
                ctx=MagicMock(run_id="run-1"),
                step_in_pipeline=5,
                sink_name="primary",
                pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
                failsink=failsink,
                failsink_name="csv_failsink",
                failsink_edge_id="edge-failsink-1",
            )
        complete_calls = recorder.complete_node_state.call_args_list
        # t0: COMPLETED at primary (Phase 2)
        # t1: FAILED at primary (divert anchor — failsink write crashed)
        completed_calls = [c for c in complete_calls if c.kwargs.get("status") == NodeStateStatus.COMPLETED]
        failed_calls = [c for c in complete_calls if c.kwargs.get("status") == NodeStateStatus.FAILED]
        assert len(completed_calls) == 1  # t0
        assert len(failed_calls) == 1  # t1 primary divert state cleaned up
        # Verify: 2 primary states opened (t0 + t1 divert anchor), 0 failsink states
        begin_calls = recorder.begin_node_state.call_args_list
        primary_begins = [c for c in begin_calls if c.kwargs.get("node_id") == sink.node_id]
        failsink_begins = [c for c in begin_calls if c.kwargs.get("node_id") == failsink.node_id]
        assert len(primary_begins) == 2  # t0 + t1 divert anchor
        assert len(failsink_begins) == 0  # failsink write crashed before state opening

    def test_failsink_flush_failure_crashes(self) -> None:
        """If failsink.flush() raises, crash — it's the last resort."""
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        failsink.flush.side_effect = OSError("disk full")
        tokens = [_make_token("t0")]
        with pytest.raises(OSError, match="disk full"):
            executor.write(
                sink=sink,
                tokens=tokens,
                ctx=MagicMock(run_id="run-1"),
                step_in_pipeline=5,
                sink_name="primary",
                pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
                failsink=failsink,
                failsink_name="csv_failsink",
                failsink_edge_id="edge-failsink-1",
            )


class TestNonContiguousDiversions:
    """Verify correct partitioning when diverted rows are non-contiguous."""

    def test_non_contiguous_diversions(self) -> None:
        """Rows 0 and 2 diverted, row 1 primary. Outcomes correctly partitioned.

        Uses token_id keying, not call ordering -- the executor may process
        primary tokens before diverted tokens.
        """
        executor, recorder = _make_executor()
        diversions = (
            RowDiversion(row_index=0, reason="bad", row_data={"x": 1}),
            RowDiversion(row_index=2, reason="bad", row_data={"x": 3}),
        )
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0"), _make_token("t1"), _make_token("t2")]
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
        )
        outcome_calls = recorder.record_token_outcome.call_args_list
        outcomes_by_token = {c.kwargs["token_id"]: c.kwargs["outcome"] for c in outcome_calls}
        assert outcomes_by_token["t0"] == RowOutcome.DIVERTED
        assert outcomes_by_token["t1"] == RowOutcome.COMPLETED
        assert outcomes_by_token["t2"] == RowOutcome.DIVERTED


class TestEmptyBatch:
    """Verify behavior when no tokens are provided."""

    def test_empty_batch_with_failsink_configured(self) -> None:
        """Empty token list with failsink configured -- no-op, no crash."""
        executor, recorder = _make_executor()
        sink = _make_sink(on_write_failure="csv_failsink")
        failsink = _make_failsink()
        result = executor.write(
            sink=sink,
            tokens=[],
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
        )
        assert result == (None, 0)
        failsink.write.assert_not_called()
        recorder.record_token_outcome.assert_not_called()


class TestOnTokenWrittenWithDiversions:
    """Verify on_token_written callback is NOT called for diverted tokens."""

    def test_on_token_written_not_called_for_diverted_discard_mode(self) -> None:
        """on_token_written must not fire for diverted tokens (discard mode)."""
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="discard")
        tokens = [_make_token("t0"), _make_token("t1")]
        callback = MagicMock()
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            on_token_written=callback,
        )
        # callback called once for t0 (primary), NOT for t1 (diverted)
        assert callback.call_count == 1
        assert callback.call_args[0][0].token_id == "t0"

    def test_on_token_written_not_called_for_diverted_failsink_mode(self) -> None:
        """on_token_written must not fire for diverted tokens (failsink mode)."""
        executor, _recorder = _make_executor()
        diversions = (RowDiversion(row_index=1, reason="bad", row_data={"x": 1}),)
        sink = _make_sink(diversions=diversions, on_write_failure="csv_failsink")
        failsink = _make_failsink()
        tokens = [_make_token("t0"), _make_token("t1")]
        callback = MagicMock()
        executor.write(
            sink=sink,
            tokens=tokens,
            ctx=MagicMock(run_id="run-1"),
            step_in_pipeline=5,
            sink_name="primary",
            pending_outcome=PendingOutcome(RowOutcome.COMPLETED),
            failsink=failsink,
            failsink_name="csv_failsink",
            failsink_edge_id="edge-failsink-1",
            on_token_written=callback,
        )
        # callback called once for t0 (primary), NOT for t1 (diverted to failsink)
        assert callback.call_count == 1
        assert callback.call_args[0][0].token_id == "t0"
