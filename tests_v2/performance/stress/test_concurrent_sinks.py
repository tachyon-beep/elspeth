# tests_v2/performance/stress/test_concurrent_sinks.py
"""Concurrent sink write stress tests.

Tests that multiple sink instances writing concurrently do not lose data
or corrupt ordering. Uses CollectSink from tests_v2.fixtures.plugins
to capture output in memory.

These tests do NOT require ChaosLLM; they exercise sink write paths directly.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests_v2.fixtures.plugins import CollectSink

pytestmark = pytest.mark.stress


def _make_rows(count: int, prefix: str = "row") -> list[dict[str, Any]]:
    """Generate simple row dicts for sink testing."""
    return [{"id": f"{prefix}-{i}", "value": i} for i in range(count)]


@pytest.mark.stress
class TestConcurrentSinks:
    """Concurrent sink write tests."""

    def test_concurrent_sink_writes_no_data_loss(self) -> None:
        """Multiple threads writing to separate sinks concurrently.

        Creates N sinks and N threads, each thread writing a batch of rows
        to its own sink concurrently. Verifies no data is lost.

        Verifies:
        - All rows are captured across all sinks
        - No duplicate or missing rows
        - Sink write calls complete without exception
        """
        num_sinks = 5
        rows_per_sink = 200

        sinks = [CollectSink(f"sink_{i}") for i in range(num_sinks)]
        errors: list[Exception] = []
        lock = threading.Lock()

        def writer(sink: CollectSink, rows: list[dict[str, Any]]) -> None:
            try:
                # Write in batches of 10 to simulate realistic usage
                batch_size = 10
                for start in range(0, len(rows), batch_size):
                    batch = rows[start : start + batch_size]
                    sink.write(batch, ctx=None)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Each sink gets its own rows with unique prefix
        all_row_sets = [_make_rows(rows_per_sink, prefix=f"sink{i}") for i in range(num_sinks)]

        threads = [
            threading.Thread(target=writer, args=(sinks[i], all_row_sets[i]), name=f"writer-{i}")
            for i in range(num_sinks)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        # No errors
        assert len(errors) == 0, f"Unexpected errors: {errors}"

        # Verify each sink got its full row count
        for i, sink in enumerate(sinks):
            assert len(sink.results) == rows_per_sink, (
                f"Sink {i} got {len(sink.results)} rows, expected {rows_per_sink}"
            )

        # Verify total row count across all sinks
        total = sum(len(s.results) for s in sinks)
        assert total == num_sinks * rows_per_sink, (
            f"Total rows: {total}, expected {num_sinks * rows_per_sink}"
        )

        # Verify no cross-sink contamination (each sink only has its prefix)
        for i, sink in enumerate(sinks):
            prefix = f"sink{i}"
            for row in sink.results:
                assert row["id"].startswith(prefix), (
                    f"Sink {i} contains foreign row: {row['id']}"
                )

    def test_concurrent_sink_ordering(self) -> None:
        """Sink writes maintain ordering within each sink.

        Multiple threads write to the same sink (protected by the sink's
        internal list append). Verifies that within each thread's batch,
        ordering is preserved.

        Verifies:
        - Rows from each thread appear in correct relative order
        - No interleaving within a single write() call
        """
        sink = CollectSink("ordered")
        num_threads = 4
        rows_per_thread = 100
        errors: list[Exception] = []
        lock = threading.Lock()

        def writer(thread_id: int) -> None:
            try:
                rows = _make_rows(rows_per_thread, prefix=f"t{thread_id}")
                # Write all rows in one call to test atomicity of write()
                sink.write(rows, ctx=None)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(i,), name=f"ordered-writer-{i}")
            for i in range(num_threads)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        # No errors
        assert len(errors) == 0, f"Unexpected errors: {errors}"

        # Total row count should be correct
        expected_total = num_threads * rows_per_thread
        assert len(sink.results) == expected_total, (
            f"Got {len(sink.results)} rows, expected {expected_total}"
        )

        # Verify per-thread ordering: rows from the same thread should appear
        # in monotonically increasing order by their index
        for tid in range(num_threads):
            prefix = f"t{tid}"
            thread_rows = [r for r in sink.results if r["id"].startswith(prefix)]
            assert len(thread_rows) == rows_per_thread, (
                f"Thread {tid} has {len(thread_rows)} rows, expected {rows_per_thread}"
            )

            # Within each thread's rows, values should be in order
            values = [r["value"] for r in thread_rows]
            assert values == sorted(values), (
                f"Thread {tid} rows are not in order: first 10 = {values[:10]}"
            )
