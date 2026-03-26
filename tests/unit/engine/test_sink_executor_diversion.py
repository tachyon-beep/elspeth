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
