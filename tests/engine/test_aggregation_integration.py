"""Integration tests for aggregation timeout behavior.

These tests verify that aggregation timeouts fire during active processing,
not just at end-of-source.

Bug reference: P1-2026-01-22-aggregation-timeout-idle-never-fires
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest

from elspeth.contracts import (
    RunStatus,
    SourceRow,
)
from elspeth.core.config import (
    AggregationSettings,
    ElspethSettings,
    SinkSettings,
    SourceSettings,
    TriggerConfig,
)
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.artifacts import ArtifactDescriptor
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import TransformResult
from tests.conftest import (
    _TestSchema,
    _TestSinkBase,
    _TestSourceBase,
    as_sink,
    as_source,
    as_transform,
)

# Note: ExecutionGraph.from_plugin_instances is used directly (imported locally)
# instead of build_production_graph, because we need to control node_id assignment


@pytest.fixture(scope="module")
def landscape_db() -> LandscapeDB:
    """Module-scoped in-memory database for aggregation integration tests."""
    return LandscapeDB.in_memory()


class TestAggregationTimeoutIntegration:
    """Test aggregation timeout fires during processing, not just at end-of-source.

    Bug: P1-2026-01-22-aggregation-timeout-idle-never-fires
    Root cause: should_flush() is only called after buffer_row(), so timeouts
    never fire during idle periods.
    """

    def test_aggregation_timeout_flushes_during_processing(
        self,
        landscape_db: LandscapeDB,
    ) -> None:
        """Aggregation should flush on timeout during processing, not wait for end-of-source.

        This test proves BUG P1-2026-01-22-aggregation-timeout-idle-never-fires:
        - Row 1 buffered at T=0s (timeout=0.1s)
        - Source sleeps for 0.25s
        - Row 2 emitted at T=0.25s, gives time for timeout to fire
        - Expect: Row 1's batch flushes via timeout DURING processing of row 2
        - Actual (bug): Row 1's batch only flushes at end-of-source
        """
        # Track when batches arrive at sink
        flush_times: list[tuple[int, float]] = []  # (batch_num, time)
        start_time = time.monotonic()

        class SlowSource(_TestSourceBase):
            """Source that emits rows with delays between them."""

            name = "slow_source"
            output_schema = _TestSchema

            def __init__(self) -> None:
                pass

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                # Row 1: buffered into aggregation at T=0
                yield SourceRow.valid({"id": 1, "value": 100})
                # Wait long enough for timeout to fire if check is called
                time.sleep(0.25)
                # Row 2: should trigger timeout check for row 1's batch
                yield SourceRow.valid({"id": 2, "value": 200})
                # Row 3: will start a new batch
                yield SourceRow.valid({"id": 3, "value": 300})

            def close(self) -> None:
                pass

        class BatchStatsTransform(BaseTransform):
            """Simple batch-aware transform that aggregates rows."""

            name = "batch_stats"
            input_schema = _TestSchema
            output_schema = _TestSchema
            is_batch_aware = True
            # Note: node_id is assigned by graph construction, not pre-set

            def __init__(self) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})

            def process(self, row: dict[str, Any] | list[dict[str, Any]], ctx: Any) -> TransformResult:
                """Process single row or batch.

                Batch-aware transforms must check if input is a list (batch mode)
                or dict (single row mode) and dispatch accordingly.
                """
                if isinstance(row, list):
                    # Batch mode - aggregate the rows
                    rows = row
                    total = sum(r.get("value", 0) for r in rows)
                    return TransformResult.success({"id": rows[0].get("id"), "value": total, "count": len(rows)})
                else:
                    # Single row mode - passthrough
                    return TransformResult.success(dict(row))

        class TimingSink(_TestSinkBase):
            """Sink that tracks when batches arrive."""

            name = "timing_sink"

            def __init__(self) -> None:
                self.rows: list[dict[str, Any]] = []
                self.batch_num = 0

            def on_start(self, ctx: Any) -> None:
                pass

            def on_complete(self, ctx: Any) -> None:
                pass

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                now = time.monotonic()
                self.batch_num += 1
                for row in rows:
                    flush_times.append((self.batch_num, now - start_time))
                    self.rows.append(row)
                return ArtifactDescriptor.for_file(
                    path="memory://test",
                    size_bytes=0,
                    content_hash="test",
                )

            def close(self) -> None:
                pass

        # Build pipeline with short timeout
        source = as_source(SlowSource())
        transform = as_transform(BatchStatsTransform())
        sink = as_sink(TimingSink())

        # Build graph FIRST to get the assigned node_id for the transform
        # We pass an empty aggregations dict since we're using a batch-aware
        # transform in the transforms list, not a separate aggregation node
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph.from_plugin_instances(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
            aggregations={},  # Empty - aggregation behavior comes from settings
            gates=[],
            default_sink="output",
            coalesce_settings=None,
        )

        # Get the graph-assigned node_id for the transform
        transform_id_map = graph.get_transform_id_map()
        assert 0 in transform_id_map, "Transform should have an assigned node_id"
        transform_node_id = transform_id_map[0]  # First (only) transform

        agg_settings = AggregationSettings(
            name="test_agg",
            plugin="batch_stats",
            trigger=TriggerConfig(
                timeout_seconds=0.1,  # Short timeout - should fire during sleep
                count=100,  # High count - won't trigger by count
            ),
            output_mode="single",
        )

        # Now create the config with the correct node_id in aggregation_settings
        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
            gates=[],
            aggregation_settings={
                transform_node_id: agg_settings,  # Use graph-assigned node_id
            },
            coalesce_settings={},
        )

        settings = ElspethSettings(
            source=SourceSettings(plugin="slow_source", options={}),
            sinks={"output": SinkSettings(plugin="timing_sink", options={})},
            default_sink="output",
            transforms=[],
            gates=[],
            aggregation={},
        )

        orchestrator = Orchestrator(db=landscape_db)
        result = orchestrator.run(config, graph=graph, settings=settings)

        assert result.status == RunStatus.COMPLETED, f"Run failed: {result}"

        # Verify we got results
        written_rows = sink.rows
        assert len(written_rows) >= 1, "Expected at least one batch to be flushed"

        # KEY ASSERTION: Timeout should cause MULTIPLE flushes
        # If timeout works during processing:
        #   - Row 1 buffered at T=0
        #   - Timeout of 0.1s should fire when row 2 arrives at T=0.25s
        #   - process_batch called with 1 row (row 1) -> count=1
        #   - Rows 2 and 3 go into a NEW batch, flushed at end-of-source -> count=2
        #   - Result: 2 output rows with different count values
        #
        # If bug exists (no timeout check during processing):
        #   - All 3 rows accumulate in ONE batch
        #   - Flushed at end-of-source
        #   - Result: 1 batch with count=3
        #
        # We can detect whether timeout worked by checking if we got multiple
        # output rows with different "count" values (each representing a separate batch)
        batch_counts = [r.get("count") for r in written_rows]

        # Timeout worked if we have more than one output row (multiple batches)
        assert len(written_rows) >= 2, (
            f"Aggregation timeout did not fire during processing! "
            f"Only {len(written_rows)} output row(s) with counts {batch_counts}. "
            f"Expected 2+ output rows (timeout batch + end-of-source batch). "
            f"Bug P1-2026-01-22: timeout only fires at end-of-source."
        )

        # Verify batch sizes: first batch should be row 1 (count=1),
        # second batch should be rows 2+3 (count=2)
        assert 1 in batch_counts, f"Expected a batch with count=1 (row 1 alone), got {batch_counts}"
        assert 2 in batch_counts, f"Expected a batch with count=2 (rows 2+3), got {batch_counts}"

        # If timeout didn't work, we'd see a single batch with count=3
        assert 3 not in batch_counts, (
            "Timeout did NOT fire! All 3 rows were in one batch (count=3). Bug P1-2026-01-22: timeout only fires at end-of-source."
        )
