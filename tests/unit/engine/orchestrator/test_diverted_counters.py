"""Tests for DIVERTED outcome in ExecutionCounters."""

from __future__ import annotations

from elspeth.engine.orchestrator.types import ExecutionCounters


class TestExecutionCountersDiverted:
    def test_rows_diverted_default_zero(self) -> None:
        counters = ExecutionCounters()
        assert counters.rows_diverted == 0

    def test_rows_diverted_explicit(self) -> None:
        counters = ExecutionCounters(rows_diverted=5)
        assert counters.rows_diverted == 5
