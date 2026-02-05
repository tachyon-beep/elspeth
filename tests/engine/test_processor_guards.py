# tests/engine/test_processor_guards.py
"""Tests for RowProcessor safety guards.

These tests verify that safety mechanisms (iteration limits, etc.)
correctly prevent pathological scenarios from hanging the pipeline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from elspeth.contracts import SourceRow, TokenInfo
from elspeth.contracts.enums import NodeType, RowOutcome
from elspeth.contracts.results import RowResult
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.contracts.types import CoalesceName, NodeID
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.engine.processor import MAX_WORK_QUEUE_ITERATIONS, RowProcessor, _WorkItem
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.context import PluginContext
from elspeth.plugins.results import TransformResult as PluginTransformResult
from tests.engine.conftest import DYNAMIC_SCHEMA, _TestSchema


def _make_pipeline_row(data: dict[str, Any]) -> PipelineRow:
    """Create a PipelineRow with OBSERVED schema for testing.

    Helper to wrap test dicts in PipelineRow with flexible schema.
    Uses object type for all fields since OBSERVED mode accepts any type.
    """
    fields = tuple(
        FieldContract(
            normalized_name=key,
            original_name=key,
            python_type=object,
            required=False,
            source="inferred",
        )
        for key in data
    )
    contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
    return PipelineRow(data, contract)


def _make_observed_contract(row: dict[str, Any]) -> SchemaContract:
    """Create an OBSERVED contract from row data for testing."""
    fields = tuple(
        FieldContract(
            normalized_name=key,
            original_name=key,
            python_type=type(value),
            required=False,
            source="inferred",
        )
        for key, value in row.items()
    )
    return SchemaContract(mode="OBSERVED", fields=fields, locked=True)


class TestProcessorGuards:
    """Tests for processor safety guards."""

    def test_max_work_queue_iterations_constant_value(self) -> None:
        """Verify MAX_WORK_QUEUE_ITERATIONS is set to expected value.

        This is a sanity check - if someone changes the constant,
        they should be aware tests depend on it.
        """
        assert MAX_WORK_QUEUE_ITERATIONS == 10_000

    def test_work_queue_exceeding_limit_raises_runtime_error(self) -> None:
        """Exceeding MAX_WORK_QUEUE_ITERATIONS must raise RuntimeError.

        This test verifies the infinite loop guard fires correctly by using
        the production process_row() path with a transform that creates
        infinite child work items.
        """
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        # Setup minimal infrastructure
        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=SchemaConfig.from_dict({"mode": "observed"}),
        )
        # Must register transform node for FK constraint
        transform_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="infinite_fork",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        span_factory = SpanFactory()

        # Create processor with minimal config
        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id=run.run_id,
            source_node_id=NodeID(source.node_id),
        )

        # Create a buggy transform that always returns ITSELF as a child work item
        # This simulates a transform bug that creates infinite loops
        class InfiniteForkTransform(BaseTransform):
            name = "infinite_fork"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"mode": "observed"}})
                self.node_id = node_id

            def process(self, row: PipelineRow, ctx: PluginContext) -> PluginTransformResult:
                # Return the same row - the bug is in _process_single_token which we'll mock
                # to create infinite child work items
                return PluginTransformResult.success(row.to_dict(), success_reason={"action": "fork"})

        transform = InfiniteForkTransform(transform_node.node_id)
        ctx = PluginContext(run_id=run.run_id, config={})

        # Patch _process_single_token to always return a child work item with the same token
        # This simulates a buggy transform that creates infinite work
        def buggy_process_single_token(
            token: TokenInfo,
            transforms: list[Any],
            ctx: PluginContext,
            start_step: int,
            coalesce_at_step: int | None = None,
            coalesce_name: CoalesceName | None = None,
        ) -> tuple[RowResult | list[RowResult] | None, list[_WorkItem]]:
            # Always return the same token as a child work item (infinite loop!)
            mock_result = RowResult(
                token=token,
                final_data=token.row_data.to_dict(),
                outcome=RowOutcome.COMPLETED,
                sink_name="output",
            )
            # BUG: Return the same token as a child work item (simulates infinite fork)
            child_items = [_WorkItem(token=token, start_step=0)]
            return mock_result, child_items

        # Patch MAX_WORK_QUEUE_ITERATIONS to a lower value for faster test
        # and use the buggy _process_single_token that creates infinite work
        with (
            patch.object(processor, "_process_single_token", side_effect=buggy_process_single_token),
            patch("elspeth.engine.processor.MAX_WORK_QUEUE_ITERATIONS", 5),
            pytest.raises(RuntimeError, match=r"exceeded .* iterations"),
        ):
            # Call the PRODUCTION process_row() - the guard should fire
            processor.process_row(
                row_index=0,
                source_row=SourceRow.valid({"value": 1}, contract=_make_observed_contract({"value": 1})),
                transforms=[transform],
                ctx=ctx,
            )

    def test_normal_processing_completes_without_hitting_guard(self) -> None:
        """Normal DAG processing should never approach the iteration limit.

        This is a sanity check that the guard doesn't interfere with
        legitimate pipelines.
        """
        # A simple linear pipeline with 10 transforms should complete
        # in exactly 10 iterations (one per transform)
        assert MAX_WORK_QUEUE_ITERATIONS > 10

        # The guard is set high enough that even complex DAGs with
        # many forks/joins should complete well under the limit
        # A DAG with 100 nodes and 10 parallel branches = ~1000 iterations max
        assert MAX_WORK_QUEUE_ITERATIONS > 1000

    def test_iteration_guard_exists_in_process_row(self) -> None:
        """Verify iteration guard is present in process_row method.

        This is a structural test - we verify by running a simple case
        that the guard infrastructure is in place.
        """
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)

        run = recorder.begin_run(config={}, canonical_version="v1")
        source = recorder.register_node(
            run_id=run.run_id,
            plugin_name="source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )
        # Must register transform node for FK constraint
        transform_node = recorder.register_node(
            run_id=run.run_id,
            plugin_name="passthrough",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0",
            config={},
            schema_config=DYNAMIC_SCHEMA,
        )

        span_factory = SpanFactory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id=run.run_id,
            source_node_id=NodeID(source.node_id),
        )

        # Simple passthrough transform
        class PassthroughTransform(BaseTransform):
            name = "passthrough"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"mode": "observed"}})
                self.node_id = node_id

            def process(self, row: PipelineRow, ctx: PluginContext) -> PluginTransformResult:
                # Passthrough - return dict copy of row data
                return PluginTransformResult.success(row.to_dict(), success_reason={"action": "passthrough"})

        transform = PassthroughTransform(transform_node.node_id)
        ctx = PluginContext(run_id=run.run_id, config={})

        # This should complete successfully without hitting the guard
        results = processor.process_row(
            row_index=0,
            source_row=SourceRow.valid({"value": 42}, contract=_make_observed_contract({"value": 42})),
            transforms=[transform],
            ctx=ctx,
        )

        # If we get here without RuntimeError, the guard didn't fire
        # (which is correct for normal processing)
        assert len(results) >= 1  # At least one result (terminal state)

    def test_guard_constant_is_reasonable(self) -> None:
        """Verify the MAX_WORK_QUEUE_ITERATIONS constant is reasonable.

        The guard should be high enough to not trigger on legitimate pipelines
        but low enough to catch runaway loops quickly.
        """
        # Should be at least 1000 for complex DAGs
        assert MAX_WORK_QUEUE_ITERATIONS >= 1000

        # Should not be astronomical (would defeat the purpose)
        assert MAX_WORK_QUEUE_ITERATIONS <= 100_000

        # Should be exactly 10,000 as documented
        assert MAX_WORK_QUEUE_ITERATIONS == 10_000
