"""
FIX VERIFICATION: elspeth-rapid-nsj
TITLE: Aggregation checkpoint state saved in production

This test VERIFIES the fix for elspeth-rapid-nsj:
- Orchestrator._maybe_checkpoint() now calls processor.get_aggregation_checkpoint_state()
- The aggregation state is passed to create_checkpoint()
- Checkpoints contain aggregation_state_json for crash recovery

The fix ensures buffered rows in aggregation nodes are not lost on crash.
"""

from __future__ import annotations

from typing import Any

import pytest

from elspeth.contracts import (
    ArtifactDescriptor,
    RunStatus,
)
from elspeth.core.config import (
    AggregationSettings,
    CheckpointSettings,
    ElspethSettings,
    SinkSettings,
    SourceSettings,
    TriggerConfig,
)
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.orchestrator import Orchestrator, PipelineConfig
from elspeth.plugins.base import BaseTransform
from elspeth.plugins.results import TransformResult
from tests.conftest import (
    CallbackSource,
    _TestSchema,
    _TestSinkBase,
    as_sink,
    as_source,
    as_transform,
)


class BatchCollectorTransform(BaseTransform):
    """Batch-aware transform that collects rows until flush."""

    name = "batch_collector"
    input_schema = _TestSchema
    output_schema = _TestSchema
    is_batch_aware = True

    def __init__(self) -> None:
        super().__init__({"schema": {"mode": "observed"}})

    def process(self, row: dict[str, Any] | list[dict[str, Any]], ctx: Any) -> TransformResult:
        if isinstance(row, list):
            # Batch mode - aggregate
            total = sum(r.get("value", 0) for r in row)
            return TransformResult.success(
                {"id": row[0].get("id"), "value": total, "count": len(row)},
                success_reason={"action": "batch"},
            )
        else:
            # Single row - passthrough
            return TransformResult.success(dict(row), success_reason={"action": "single"})


class CollectingSink(_TestSinkBase):
    """Sink that collects rows."""

    name = "collecting_sink"

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def on_start(self, ctx: Any) -> None:
        pass

    def on_complete(self, ctx: Any) -> None:
        pass

    def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
        for row in rows:
            self.rows.append(row)
        return ArtifactDescriptor.for_file(
            path="memory://test",
            size_bytes=0,
            content_hash="test",
        )

    def close(self) -> None:
        pass


class TestAggregationCheckpointFixVerification:
    """
    FIX VERIFICATION: Verifies aggregation state IS saved to checkpoints.

    These tests verify the fix for elspeth-rapid-nsj where aggregation
    checkpoint state was never saved during normal pipeline execution.
    """

    @pytest.fixture
    def landscape_db(self) -> LandscapeDB:
        """In-memory database for test isolation."""
        return LandscapeDB.in_memory()

    def test_checkpoint_includes_aggregation_state(
        self,
        landscape_db: LandscapeDB,
        payload_store,
    ) -> None:
        """
        VERIFIES FIX: create_checkpoint() is called WITH aggregation_state

        Steps:
        1. Create pipeline with aggregation (count trigger = 10, high threshold)
        2. Process 5 rows (less than trigger, so rows stay buffered)
        3. Use mock to capture create_checkpoint() calls
        4. VERIFY: aggregation_state is passed to create_checkpoint()
        """
        # Source with 5 rows (less than count trigger of 10)
        callback_source = CallbackSource(
            rows=[
                {"id": 1, "value": 100},
                {"id": 2, "value": 200},
                {"id": 3, "value": 300},
                {"id": 4, "value": 400},
                {"id": 5, "value": 500},
            ],
            output_schema=_TestSchema,
            source_name="buffering_source",
        )
        source = as_source(callback_source)

        transform = as_transform(BatchCollectorTransform())
        collecting_sink = CollectingSink()
        sink = as_sink(collecting_sink)

        # Build graph
        from elspeth.core.dag import ExecutionGraph

        graph = ExecutionGraph.from_plugin_instances(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
            aggregations={},
            gates=[],
            default_sink="output",
            coalesce_settings=None,
        )

        transform_id_map = graph.get_transform_id_map()
        transform_node_id = transform_id_map[0]

        # High count trigger so rows stay buffered
        agg_settings = AggregationSettings(
            name="test_agg",
            plugin="batch_collector",
            trigger=TriggerConfig(
                count=10,  # High count - won't trigger during 5 rows
                timeout_seconds=3600,  # 1 hour - won't trigger
            ),
            output_mode="transform",
        )

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
            gates=[],
            aggregation_settings={
                transform_node_id: agg_settings,
            },
            coalesce_settings={},
        )

        # Enable checkpoint every row
        checkpoint_settings = CheckpointSettings(
            enabled=True,
            frequency="every_row",
        )

        settings = ElspethSettings(
            source=SourceSettings(plugin="buffering_source", options={}),
            sinks={"output": SinkSettings(plugin="collecting_sink", options={})},
            default_sink="output",
            transforms=[],
            gates=[],
            aggregation={},
            checkpoint=checkpoint_settings,
        )

        # Create checkpoint manager and config
        from elspeth.contracts.config.runtime import RuntimeCheckpointConfig
        from elspeth.core.checkpoint import CheckpointManager

        checkpoint_mgr = CheckpointManager(landscape_db)
        checkpoint_config = RuntimeCheckpointConfig.from_settings(checkpoint_settings)

        # Track create_checkpoint calls
        checkpoint_calls: list[dict[str, Any]] = []
        original_create_checkpoint = checkpoint_mgr.create_checkpoint

        def capture_create_checkpoint(*args, **kwargs):
            """Capture the arguments passed to create_checkpoint."""
            checkpoint_calls.append(
                {
                    "args": args,
                    "kwargs": kwargs,
                    "aggregation_state": kwargs.get("aggregation_state"),
                }
            )
            # Call the original
            return original_create_checkpoint(*args, **kwargs)

        checkpoint_mgr.create_checkpoint = capture_create_checkpoint

        # Run pipeline with checkpointing enabled
        orchestrator = Orchestrator(
            db=landscape_db,
            checkpoint_manager=checkpoint_mgr,
            checkpoint_config=checkpoint_config,
        )

        result = orchestrator.run(config, graph=graph, settings=settings, payload_store=payload_store)

        # Verify run completed
        assert result.status == RunStatus.COMPLETED, f"Run failed: {result}"

        # Verify checkpoints were created
        assert len(checkpoint_calls) > 0, "No checkpoint calls captured"

        # FIX VERIFICATION:
        # All create_checkpoint calls should have aggregation_state
        # because Orchestrator._maybe_checkpoint() now passes aggregation state
        calls_with_agg_state = [call for call in checkpoint_calls if call["aggregation_state"] is not None]

        # FIX VERIFICATION: This assertion PASSES when fix is applied
        assert len(calls_with_agg_state) > 0, (
            f"FIX NOT WORKING: Found {len(calls_with_agg_state)} checkpoint calls WITH aggregation_state (expected > 0 after fix)."
        )

        # Verify the aggregation state has expected structure
        for call in calls_with_agg_state:
            agg_state = call["aggregation_state"]
            assert "_version" in agg_state, "Aggregation state should have version field"

    def test_orchestrator_calls_get_aggregation_checkpoint_state(
        self,
        landscape_db: LandscapeDB,
        payload_store,
    ) -> None:
        """
        VERIFIES FIX: get_aggregation_checkpoint_state() IS called in production.

        We verify this by checking that calls to get_aggregation_checkpoint_state()
        appear in the orchestrator checkpoint flow. This is a static verification.
        """
        import ast
        from pathlib import Path

        # Read the orchestrator source
        orchestrator_path = Path(__file__).parent.parent.parent / "src/elspeth/engine/orchestrator_legacy.py"
        source_code = orchestrator_path.read_text()

        # Parse and look for get_aggregation_checkpoint_state calls
        tree = ast.parse(source_code)

        get_checkpoint_state_calls = []
        for node in ast.walk(tree):
            # Check for method call pattern: xxx.get_aggregation_checkpoint_state()
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get_aggregation_checkpoint_state":
                get_checkpoint_state_calls.append(node.lineno)

        # FIX VERIFICATION: This assertion PASSES when fix is applied
        assert len(get_checkpoint_state_calls) > 0, (
            f"FIX NOT WORKING: Found {len(get_checkpoint_state_calls)} get_aggregation_checkpoint_state() calls (expected > 0 after fix)."
        )
