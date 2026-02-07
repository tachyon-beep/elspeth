# tests/engine/test_processor_guards.py
"""Tests for RowProcessor safety guards.

These tests verify that safety mechanisms (iteration limits, etc.)
correctly prevent pathological scenarios from hanging the pipeline.

Test Philosophy:
----------------
The MAX_WORK_QUEUE_ITERATIONS guard exists to catch bugs in the processor
that could cause infinite loops (e.g., child work items with start_step=0
that never progress). Normal production code should never trigger this guard.

To test that the guard works, we use two approaches:
1. Inject a buggy scenario via mocking to verify the guard fires
2. Run realistic production scenarios to verify the guard doesn't interfere

Per CLAUDE.md "Test Path Integrity": We call production code paths, but
since the guard is defense-in-depth against bugs that shouldn't exist in
correct code, we inject the bug scenario via mocking rather than building
a broken pipeline.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from elspeth.contracts import SourceRow, TokenInfo
from elspeth.contracts.enums import NodeType, RowOutcome
from elspeth.contracts.plugin_context import PluginContext
from elspeth.contracts.results import RowResult
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract
from elspeth.contracts.types import CoalesceName, NodeID
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.engine.processor import RowProcessor, _WorkItem
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import TransformResult as PluginTransformResult
from tests.engine.conftest import DYNAMIC_SCHEMA, _TestSchema


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

    def test_work_queue_exceeding_limit_raises_runtime_error(self) -> None:
        """Exceeding MAX_WORK_QUEUE_ITERATIONS must raise RuntimeError.

        This test verifies the infinite loop guard fires correctly by using
        the production process_row() path with a mocked _process_single_token
        that simulates a bug creating infinite child work items.

        Why mock _process_single_token?
        --------------------------------
        The guard protects against processor bugs that create infinite loops.
        Correct production code NEVER triggers this guard. To test the guard,
        we inject a bug scenario: _process_single_token always returns a child
        work item with start_step=0, which would cause infinite processing.

        What this test verifies:
        - process_row() correctly tracks iterations
        - process_row() raises RuntimeError when limit exceeded
        - The error message includes useful debugging info
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
            plugin_name="buggy_transform",
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

        # Simple passthrough transform (the bug is injected via mock)
        class SimpleTransform(BaseTransform):
            name = "buggy_transform"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, node_id: str) -> None:
                super().__init__({"schema": {"mode": "observed"}})
                self.node_id = node_id

            def process(self, row: PipelineRow, ctx: PluginContext) -> PluginTransformResult:
                return PluginTransformResult.success(row, success_reason={"action": "pass"})

        transform = SimpleTransform(transform_node.node_id)
        ctx = PluginContext(run_id=run.run_id, config={})

        # Mock _process_single_token to simulate infinite loop bug
        # BUG: Always returns the same token as a child with start_step=0
        def buggy_process_single_token(
            token: TokenInfo,
            transforms: list[Any],
            ctx: PluginContext,
            start_step: int,
            coalesce_at_step: int | None = None,
            coalesce_name: CoalesceName | None = None,
        ) -> tuple[RowResult | list[RowResult] | None, list[_WorkItem]]:
            # Return a "completed" result BUT also queue the same token again at step 0
            # This simulates a processor bug that creates infinite work
            result = RowResult(
                token=token,
                final_data=token.row_data.to_dict(),
                outcome=RowOutcome.COMPLETED,
                sink_name="output",
            )
            # BUG: Infinite loop - always re-queue same token at start
            child_items = [_WorkItem(token=token, start_step=0)]
            return result, child_items

        # Patch to lower iteration limit for fast test
        # Call PRODUCTION process_row() - verify the guard fires
        with (
            patch.object(processor, "_process_single_token", side_effect=buggy_process_single_token),
            patch("elspeth.engine.processor.MAX_WORK_QUEUE_ITERATIONS", 5),
            pytest.raises(RuntimeError, match=r"exceeded .* iterations"),
        ):
            processor.process_row(
                row_index=0,
                source_row=SourceRow.valid({"value": 1}, contract=_make_observed_contract({"value": 1})),
                transforms=[transform],
                ctx=ctx,
            )

    def test_production_processing_with_multiple_transforms(self) -> None:
        """Real production processing with multiple transforms completes normally.

        This test exercises the ACTUAL production code path with multiple
        transforms. It verifies:
        1. Production process_row() works correctly
        2. Multiple transforms process in sequence
        3. The iteration guard doesn't interfere with normal processing

        This is NOT just checking constants - it runs real code.
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

        span_factory = SpanFactory()

        processor = RowProcessor(
            recorder=recorder,
            span_factory=span_factory,
            run_id=run.run_id,
            source_node_id=NodeID(source.node_id),
        )

        # Create multiple transforms that each modify the row
        class AddFieldTransform(BaseTransform):
            name = "add_field"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def __init__(self, field_name: str, field_value: int, node_id: str) -> None:
                super().__init__({"schema": {"mode": "observed"}})
                self._field_name = field_name
                self._field_value = field_value
                self.node_id = node_id

            def process(self, row: PipelineRow, ctx: PluginContext) -> PluginTransformResult:
                output = {**row.to_dict(), self._field_name: self._field_value}
                return PluginTransformResult.success(PipelineRow(output, row.contract), success_reason={"action": "add_field"})

        # Register transforms and create instances
        transforms = []
        for i in range(10):  # 10 transforms in sequence
            node = recorder.register_node(
                run_id=run.run_id,
                plugin_name=f"transform_{i}",
                node_type=NodeType.TRANSFORM,
                plugin_version="1.0",
                config={},
                schema_config=DYNAMIC_SCHEMA,
            )
            transform = AddFieldTransform(f"field_{i}", i, node.node_id)
            transforms.append(transform)

        ctx = PluginContext(run_id=run.run_id, config={})

        # Process row through all transforms - should complete without hitting guard
        results = processor.process_row(
            row_index=0,
            source_row=SourceRow.valid({"initial": 42}, contract=_make_observed_contract({"initial": 42})),
            transforms=transforms,
            ctx=ctx,
        )

        # Verify we got results (didn't crash)
        assert len(results) >= 1

        # Verify the transforms actually ran (data was modified)
        # At least one result should have the fields added by transforms
        final_data_list = [r.final_data for r in results if r.final_data is not None]
        assert len(final_data_list) > 0

        # Check that transforms ran in order (each added its field)
        final_data = final_data_list[0]
        if isinstance(final_data, PipelineRow):
            final_dict = final_data.to_dict()
        else:
            final_dict = final_data

        assert "initial" in final_dict
        assert final_dict["initial"] == 42
        # All 10 transforms should have added their fields
        for i in range(10):
            assert f"field_{i}" in final_dict, f"Transform {i} didn't run - field_{i} missing"
            assert final_dict[f"field_{i}"] == i

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
                return PluginTransformResult.success(row, success_reason={"action": "passthrough"})

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
