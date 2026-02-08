"""Unit tests for track_operation lifecycle behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from elspeth.contracts import BatchPendingError
from elspeth.core.operations import track_operation
from tests.fixtures.factories import make_context


@dataclass
class _Operation:
    operation_id: str


class _FakeRecorder:
    def __init__(self, *, complete_error: Exception | None = None) -> None:
        self.begin_calls: list[dict[str, Any]] = []
        self.complete_calls: list[dict[str, Any]] = []
        self._complete_error = complete_error

    def begin_operation(
        self,
        *,
        run_id: str,
        node_id: str,
        operation_type: str,
        input_data: dict[str, Any] | None = None,
    ) -> _Operation:
        self.begin_calls.append(
            {
                "run_id": run_id,
                "node_id": node_id,
                "operation_type": operation_type,
                "input_data": input_data,
            }
        )
        return _Operation(operation_id="op-001")

    def complete_operation(
        self,
        *,
        operation_id: str,
        status: str,
        output_data: dict[str, Any] | None,
        error: str | None,
        duration_ms: float,
    ) -> None:
        self.complete_calls.append(
            {
                "operation_id": operation_id,
                "status": status,
                "output_data": output_data,
                "error": error,
                "duration_ms": duration_ms,
            }
        )
        if self._complete_error is not None:
            raise self._complete_error


def test_track_operation_records_completed_status_and_output_data() -> None:
    recorder = _FakeRecorder()
    ctx = make_context()
    assert ctx.operation_id is None

    with track_operation(
        recorder=recorder,
        run_id="run-001",
        node_id="node-001",
        operation_type="source_load",
        ctx=ctx,
        input_data={"source": "csv"},
    ) as handle:
        assert ctx.operation_id == "op-001"
        handle.output_data = {"rows_loaded": 3}

    assert ctx.operation_id is None
    assert recorder.begin_calls[0]["input_data"] == {"source": "csv"}
    assert recorder.complete_calls[0]["status"] == "completed"
    assert recorder.complete_calls[0]["output_data"] == {"rows_loaded": 3}


def test_track_operation_marks_pending_for_batch_pending_error() -> None:
    recorder = _FakeRecorder()
    ctx = make_context()

    with (
        pytest.raises(BatchPendingError),
        track_operation(
            recorder=recorder,
            run_id="run-001",
            node_id="node-001",
            operation_type="sink_write",
            ctx=ctx,
        ),
    ):
        raise BatchPendingError("batch-001", "submitted")

    assert recorder.complete_calls[0]["status"] == "pending"
    assert recorder.complete_calls[0]["error"] is None
    assert ctx.operation_id is None


def test_track_operation_marks_failed_for_exception() -> None:
    recorder = _FakeRecorder()
    ctx = make_context()

    with (
        pytest.raises(ValueError, match="boom"),
        track_operation(
            recorder=recorder,
            run_id="run-001",
            node_id="node-001",
            operation_type="source_load",
            ctx=ctx,
        ),
    ):
        raise ValueError("boom")

    assert recorder.complete_calls[0]["status"] == "failed"
    assert recorder.complete_calls[0]["error"] == "boom"
    assert ctx.operation_id is None


def test_track_operation_marks_failed_for_base_exception() -> None:
    class _Fatal(BaseException):
        pass

    recorder = _FakeRecorder()
    ctx = make_context()

    with (
        pytest.raises(_Fatal, match="stop-now"),
        track_operation(
            recorder=recorder,
            run_id="run-001",
            node_id="node-001",
            operation_type="source_load",
            ctx=ctx,
        ),
    ):
        raise _Fatal("stop-now")

    assert recorder.complete_calls[0]["status"] == "failed"
    assert recorder.complete_calls[0]["error"] == "stop-now"
    assert ctx.operation_id is None


def test_track_operation_raises_db_error_if_completion_fails_after_success() -> None:
    recorder = _FakeRecorder(complete_error=RuntimeError("db write failed"))
    ctx = make_context()

    with (
        pytest.raises(RuntimeError, match="db write failed"),
        track_operation(
            recorder=recorder,
            run_id="run-001",
            node_id="node-001",
            operation_type="sink_write",
            ctx=ctx,
        ),
    ):
        pass

    assert recorder.complete_calls[0]["status"] == "completed"
    assert ctx.operation_id is None


def test_track_operation_does_not_mask_original_exception_when_completion_fails() -> None:
    recorder = _FakeRecorder(complete_error=RuntimeError("db write failed"))
    ctx = make_context()

    with (
        pytest.raises(ValueError, match="original failure"),
        track_operation(
            recorder=recorder,
            run_id="run-001",
            node_id="node-001",
            operation_type="source_load",
            ctx=ctx,
        ),
    ):
        raise ValueError("original failure")

    assert recorder.complete_calls[0]["status"] == "failed"
    assert recorder.complete_calls[0]["error"] == "original failure"
    assert ctx.operation_id is None
