# tests/engine/test_processor_batch.py
"""Tests for batch-aware transforms and deaggregation in RowProcessor.

This module tests:
- Batch-aware transforms with aggregation configuration
- Buffer management and flush triggers
- Checkpoint restoration for aggregation state
- Deaggregation / multi-row output handling (expanding transforms)

Test plugins inherit from base classes (BaseTransform)
because the processor uses isinstance() for type-safe plugin detection.
"""

from typing import Any

from elspeth.contracts.types import NodeID
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.context import PluginContext
from elspeth.plugins.results import (
    RowOutcome,
    TransformResult,
)
from tests.engine.conftest import DYNAMIC_SCHEMA, _TestSchema


class TestProcessorBatchTransforms:
    """Tests for batch-aware transforms in RowProcessor."""

    def test_processor_buffers_rows_for_aggregation_node(self) -> None:
        """Processor buffers rows at aggregation nodes and flushes on trigger."""
        from elspeth.contracts import Determinism
        from elspeth.core.config import AggregationSettings, TriggerConfig
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import RowOutcome, TransformResult

        class SumTransform(BaseTransform):
            name = "sum"
            input_schema = _TestSchema
            output_schema = _TestSchema
            is_batch_aware = True
            determinism = Determinism.DETERMINISTIC
            plugin_version = "1.0"

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})
                self.node_id = node_id

            def process(self, rows: list[dict[str, Any]] | dict[str, Any], ctx: PluginContext) -> TransformResult:
                if isinstance(rows, list):
                    total = sum(r["value"] for r in rows)
                    return TransformResult.success({"total": total})
                return TransformResult.success(rows)

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sum_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="sum",
            node_type="aggregation",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        aggregation_settings = {
            NodeID(sum_node.node_id): AggregationSettings(
                name="sum_batch",
                plugin="sum",
                trigger=TriggerConfig(count=3),
            ),
        }

        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
            edge_map={},
            route_resolution_map={},
            aggregation_settings=aggregation_settings,
        )

        transform = SumTransform(sum_node.node_id)
        ctx = PluginContext(run_id=run.run_id, config={})

        # Process 3 rows - should buffer first 2, flush on 3rd
        results = []
        for i in range(3):
            result_list = processor.process_row(
                row_index=i,
                row_data={"value": i + 1},  # 1, 2, 3
                transforms=[transform],
                ctx=ctx,
            )
            # process_row returns list[RowResult] - take first item
            results.append(result_list[0])

        # First two rows consumed into batch
        assert results[0].outcome == RowOutcome.CONSUMED_IN_BATCH
        assert results[1].outcome == RowOutcome.CONSUMED_IN_BATCH

        # Third row triggers flush - transform receives [1, 2, 3]
        # Result should have total = 6
        assert results[2].outcome == RowOutcome.COMPLETED
        assert results[2].final_data == {"total": 6}

    def test_processor_batch_transform_without_aggregation_config(self) -> None:
        """Batch-aware transform without aggregation config uses single-row mode."""
        from elspeth.contracts import Determinism
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import RowOutcome, TransformResult

        class DoubleTransform(BaseTransform):
            name = "double"
            input_schema = _TestSchema
            output_schema = _TestSchema
            is_batch_aware = True  # But no aggregation config
            determinism = Determinism.DETERMINISTIC
            plugin_version = "1.0"

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})
                self.node_id = node_id

            def process(self, rows: list[dict[str, Any]] | dict[str, Any], ctx: PluginContext) -> TransformResult:
                if isinstance(rows, list):
                    # Batch mode - sum all values
                    return TransformResult.success({"value": sum(r["value"] for r in rows)})
                # Single-row mode - double
                return TransformResult.success({"value": rows["value"] * 2})

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="double",
            node_type="transform",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        # No aggregation_settings - so batch-aware transform uses single-row mode
        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
            edge_map={},
            route_resolution_map={},
            aggregation_settings={},  # Empty - not an aggregation node
        )

        transform = DoubleTransform(transform_node.node_id)
        ctx = PluginContext(run_id=run.run_id, config={})

        # Process row - should use single-row mode (double)
        result_list = processor.process_row(
            row_index=0,
            row_data={"value": 5},
            transforms=[transform],
            ctx=ctx,
        )

        result = result_list[0]
        assert result.outcome == RowOutcome.COMPLETED
        assert result.final_data == {"value": 10}  # Doubled, not summed

    def test_processor_buffers_restored_on_recovery(self) -> None:
        """Processor restores buffer state from checkpoint."""
        from elspeth.contracts import Determinism
        from elspeth.core.config import AggregationSettings, TriggerConfig
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory
        from elspeth.plugins.base import BaseTransform
        from elspeth.plugins.context import PluginContext
        from elspeth.plugins.results import RowOutcome, TransformResult

        class SumTransform(BaseTransform):
            name = "sum"
            input_schema = _TestSchema
            output_schema = _TestSchema
            is_batch_aware = True
            determinism = Determinism.DETERMINISTIC
            plugin_version = "1.0"

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})
                self.node_id = node_id

            def process(self, rows: list[dict[str, Any]] | dict[str, Any], ctx: PluginContext) -> TransformResult:
                if isinstance(rows, list):
                    total = sum(r["value"] for r in rows)
                    return TransformResult.success({"total": total})
                return TransformResult.success(rows)

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        run = recorder.begin_run(config={}, canonical_version="v1")

        source_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type="source",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        sum_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="sum",
            node_type="aggregation",
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        aggregation_settings = {
            NodeID(sum_node.node_id): AggregationSettings(
                name="sum_batch",
                plugin="sum",
                trigger=TriggerConfig(count=3),  # Trigger at 3
            ),
        }

        # Create rows and tokens that will be referenced by the checkpoint
        row0 = recorder.create_row(
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
            row_index=0,
            data={"value": 1},
        )
        token0 = recorder.create_token(row_id=row0.row_id)
        row1 = recorder.create_row(
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
            row_index=1,
            data={"value": 2},
        )
        token1 = recorder.create_token(row_id=row1.row_id)

        # Create the batch that will be restored from checkpoint
        old_batch = recorder.create_batch(
            run_id=run.run_id,
            aggregation_node_id=sum_node.node_id,
        )

        # Simulate restored checkpoint with 2 rows already buffered
        # Note: _version field required since Bug #12 checkpoint versioning fix
        restored_buffer_state = {
            "_version": "1.0",
            sum_node.node_id: {
                "tokens": [
                    {
                        "token_id": token0.token_id,
                        "row_id": row0.row_id,
                        "row_data": {"value": 1},
                        "branch_name": None,
                    },
                    {
                        "token_id": token1.token_id,
                        "row_id": row1.row_id,
                        "row_data": {"value": 2},
                        "branch_name": None,
                    },
                ],
                "batch_id": old_batch.batch_id,
            },
        }

        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
            edge_map={},
            route_resolution_map={},
            aggregation_settings=aggregation_settings,
        )

        # Restore buffer state
        processor._aggregation_executor.restore_from_checkpoint(restored_buffer_state)

        transform = SumTransform(sum_node.node_id)
        ctx = PluginContext(run_id=run.run_id, config={})

        # Process 1 more row - should trigger flush (2 restored + 1 new = 3)
        result_list = processor.process_row(
            row_index=2,
            row_data={"value": 3},  # Third value
            transforms=[transform],
            ctx=ctx,
        )

        # Should trigger and get total of all 3 rows
        result = result_list[0]
        assert result.outcome == RowOutcome.COMPLETED
        assert result.final_data == {"total": 6}  # 1 + 2 + 3


class TestProcessorDeaggregation:
    """Tests for deaggregation / multi-row output handling."""

    def test_processor_handles_expanding_transform(self) -> None:
        """Processor creates multiple RowResults for expanding transform."""
        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        class ExpanderTransform(BaseTransform):
            name = "expander"
            creates_tokens = True  # This is a deaggregation transform
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                # Expand each row into 2 rows
                return TransformResult.success_multi(
                    [
                        {**row, "copy": 1},
                        {**row, "copy": 2},
                    ]
                )

        # Setup real recorder
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="1.0")
        source_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="expander",
            node_type="transform",
            plugin_version="1.0.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = ExpanderTransform(transform_node.node_id)

        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
        )

        ctx = PluginContext(run_id=run.run_id, config={})

        # Process a row through the expanding transform
        results = processor.process_row(
            row_index=0,
            row_data={"value": 42},
            transforms=[transform],
            ctx=ctx,
        )

        # Should get 3 results: 1 EXPANDED parent + 2 COMPLETED children
        assert len(results) == 3

        # Find the parent (EXPANDED) and children (COMPLETED)
        expanded = [r for r in results if r.outcome == RowOutcome.EXPANDED]
        completed = [r for r in results if r.outcome == RowOutcome.COMPLETED]

        assert len(expanded) == 1
        assert len(completed) == 2

        # Children should have different token_ids but same row_id
        assert completed[0].token_id != completed[1].token_id
        assert completed[0].row_id == completed[1].row_id

        # Children should have the expanded data
        child_copies = {r.final_data["copy"] for r in completed}
        assert child_copies == {1, 2}

    def test_processor_rejects_multi_row_without_creates_tokens(self) -> None:
        """Processor raises error if transform returns multi-row but creates_tokens=False."""
        import pytest

        from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
        from elspeth.engine.processor import RowProcessor
        from elspeth.engine.spans import SpanFactory

        class BadTransform(BaseTransform):
            name = "bad"
            creates_tokens = False  # NOT allowed to create new tokens
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"fields": "dynamic"}})
                self.node_id = node_id

            def process(self, row: dict[str, Any], ctx: PluginContext) -> TransformResult:
                return TransformResult.success_multi([row, row])  # But returns multi!

        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="1.0")
        source_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="csv",
            node_type="source",
            plugin_version="1.0.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        transform_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="bad",
            node_type="transform",
            plugin_version="1.0.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        transform = BadTransform(transform_node.node_id)

        processor = RowProcessor(
            recorder=recorder,
            span_factory=SpanFactory(),
            run_id=run.run_id,
            source_node_id=NodeID(source_node.node_id),
        )

        ctx = PluginContext(run_id=run.run_id, config={})

        # Should raise because creates_tokens=False but returns multi-row
        with pytest.raises(RuntimeError, match="creates_tokens=False"):
            processor.process_row(
                row_index=0,
                row_data={"value": 1},
                transforms=[transform],
                ctx=ctx,
            )
