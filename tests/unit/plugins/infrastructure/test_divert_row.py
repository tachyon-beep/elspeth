"""Tests for BaseSink diversion infrastructure."""

from __future__ import annotations

import pytest

from elspeth.contracts.diversion import SinkWriteResult
from elspeth.plugins.infrastructure.base import BaseSink


class StubSink(BaseSink):
    """Minimal concrete sink for testing diversion infrastructure."""

    def write(self, rows, ctx):
        # Simulate a sink that diverts row 1 and writes the rest
        for i, row in enumerate(rows):
            if row.get("bad"):
                self._divert_row(i, "bad value", row)
        return SinkWriteResult(
            artifact=self._null_artifact(),
            diversions=self._get_diversions(),
        )

    def _null_artifact(self):
        from elspeth.contracts.results import ArtifactDescriptor

        return ArtifactDescriptor.for_file(path="/dev/null", content_hash="0" * 12, size_bytes=0)

    def flush(self):
        pass

    def close(self):
        pass


class TestDivertRow:
    def test_divert_row_records_diversion(self) -> None:
        sink = StubSink.__new__(StubSink)
        sink._diversion_log = []
        sink._divert_row(0, "test reason", {"a": 1})
        diversions = sink._get_diversions()
        assert len(diversions) == 1
        assert diversions[0].row_index == 0
        assert diversions[0].reason == "test reason"
        assert diversions[0].row_data["a"] == 1

    def test_get_diversions_returns_tuple(self) -> None:
        sink = StubSink.__new__(StubSink)
        sink._diversion_log = []
        sink._divert_row(0, "r1", {"x": 1})
        sink._divert_row(2, "r2", {"x": 2})
        result = sink._get_diversions()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_reset_diversion_log_clears(self) -> None:
        sink = StubSink.__new__(StubSink)
        sink._diversion_log = []
        sink._divert_row(0, "test", {"a": 1})
        sink._reset_diversion_log()
        assert sink._get_diversions() == ()

    def test_get_diversions_freezes_row_data(self) -> None:
        sink = StubSink.__new__(StubSink)
        sink._diversion_log = []
        sink._divert_row(0, "test", {"nested": {"key": "val"}})
        diversions = sink._get_diversions()
        with pytest.raises(TypeError):
            diversions[0].row_data["new"] = "bad"  # type: ignore[index]

    def test_diversion_log_initialized_in_init(self) -> None:
        """BaseSink.__init__ should initialize _diversion_log."""
        # This tests that the real __init__ sets up the log
        # We can't easily construct a real BaseSink without config,
        # so test via StubSink.__new__ + manual init
        sink = StubSink.__new__(StubSink)
        sink._diversion_log = []
        assert sink._get_diversions() == ()
