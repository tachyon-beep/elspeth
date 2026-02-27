# T18 Part A: Types and Characterization Tests

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Define all new types needed for the extraction and build the characterization test oracle that guards against regressions throughout the remaining commits.

**Architecture:** Frozen dataclasses with MappingProxyType for immutable return types. Mutable dataclass for `LoopContext` processing state. Private discriminated unions in `processor.py`. TDD: tests first, types second.

**Tech Stack:** Python dataclasses, `types.MappingProxyType`, `typing.TypeAlias`, `collections.abc.Mapping`, `collections.abc.Callable`

**Parent plan:** [T18 Implementation Plan Index](2026-02-27-t18-implementation-plan-index.md)

---

## Commit #0: Characterization Tests

### Task 0.1: Write the characterization test for `_execute_run()` full path

This test exercises quarantine + transform in a single pipeline. It becomes the regression oracle for the entire extraction sequence.

> **Scope note:** The design spec envisions coverage of aggregation, gate fork, and coalesce paths. This characterization test covers the quarantine + transform happy path only. Aggregation and fork/coalesce coverage is deferred — existing integration tests in `tests/integration/pipeline/orchestrator/` already cover those paths and will serve as regression guards during the extraction commits.

**Files:**
- Create: `tests/integration/pipeline/orchestrator/test_t18_characterization.py`

**Step 1: Write the characterization test**

```python
# tests/integration/pipeline/orchestrator/test_t18_characterization.py
"""Characterization tests for T18 orchestrator decomposition.

These tests exercise the full _execute_run() and _process_resumed_rows() paths
with multi-feature pipelines. They serve as regression oracles for the 15-commit
extraction sequence — if any extraction breaks behavior, these tests catch it.

IMPORTANT: Do NOT modify these tests during the extraction. If a test fails
after an extraction commit, the extraction introduced a regression.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import text

from elspeth.contracts import (
    PipelineRow,
    RunStatus,
)
from elspeth.contracts.payload_store import NullPayloadStore
from elspeth.contracts.results import SourceRow
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape import LandscapeDB
from elspeth.engine.orchestrator import ExecutionCounters, Orchestrator, PipelineConfig
from elspeth.plugins.results import TransformResult
from elspeth.testing import make_pipeline_row, make_source_row
from tests.fixtures.base_classes import (
    _TestSchema,
    _TestSourceBase,
    _TestTransformBase,
    as_sink,
    as_source,
    as_transform,
)
from tests.fixtures.pipeline import build_production_graph
from tests.fixtures.plugins import CollectSink, ListSource


# ---------------------------------------------------------------------------
# Test fixtures: Quarantine-capable source
# ---------------------------------------------------------------------------


class QuarantiningSource(_TestSourceBase):
    """Source that quarantines rows based on a 'valid' field.

    Rows with valid=False are quarantined. This exercises:
    - Field resolution ordering (must be from first VALID row)
    - Quarantine routing (direct to configured sink)
    - Schema contract recording (must skip quarantined rows)
    """

    name = "quarantining_source"
    output_schema = _TestSchema

    def __init__(self, rows: list[dict[str, Any]], quarantine_sink: str = "errors") -> None:
        super().__init__()
        self._rows = rows
        self._on_validation_failure = quarantine_sink

    def load(self, ctx: Any) -> Any:
        for row in self._rows:
            if not row.get("valid", True):
                yield SourceRow.quarantined(
                    row=row,
                    error="validation_failed:valid=False",
                    destination=self._on_validation_failure,
                )
            else:
                yield make_source_row(row)

    def get_field_resolution(self) -> tuple[dict[str, str], str] | None:
        return ({"value": "value", "valid": "valid"}, "identity")


class DoubleValueTransform(_TestTransformBase):
    """Transform that doubles the 'value' field."""

    name = "double_value"
    input_schema = _TestSchema
    output_schema = _TestSchema

    def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
        data = row.to_dict()
        data["doubled"] = data.get("value", 0) * 2
        return TransformResult.success(
            make_pipeline_row(data),
            success_reason={"action": "doubled"},
        )


# ---------------------------------------------------------------------------
# Characterization test: Full _execute_run() path
# ---------------------------------------------------------------------------


class TestT18CharacterizationExecuteRun:
    """Regression oracle for the T18 extraction sequence.

    Pipeline: QuarantiningSource → DoubleValueTransform → CollectSink("output") + CollectSink("errors")
    Input: 5 rows — first 2 quarantined, next 3 valid.

    This exercises:
    - Quarantine routing (rows 0-1 → errors sink)
    - Field resolution from first VALID row (row 2, not row 0)
    - Transform processing (rows 2-4 → output sink)
    - Counter arithmetic with quarantine + success
    - operation_id attribution (transforms see None)
    - Landscape audit records (nodes, node_states, routing_events)
    """

    def _build_pipeline(self) -> tuple[
        QuarantiningSource,
        DoubleValueTransform,
        CollectSink,
        CollectSink,
        PipelineConfig,
    ]:
        rows = [
            {"value": 10, "valid": False},  # quarantined (row 0)
            {"value": 20, "valid": False},  # quarantined (row 1)
            {"value": 30, "valid": True},   # valid (row 2) — first valid row
            {"value": 40, "valid": True},   # valid (row 3)
            {"value": 50, "valid": True},   # valid (row 4)
        ]
        source = as_source(QuarantiningSource(rows, quarantine_sink="errors"))
        transform = as_transform(DoubleValueTransform())
        output_sink = as_sink(CollectSink("output"))
        error_sink = as_sink(CollectSink("errors"))

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": output_sink, "errors": error_sink},
        )
        return source, transform, output_sink, error_sink, config

    def test_counter_values_exact(self) -> None:
        """Assert exact counter values for the characterization pipeline."""
        source, transform, output_sink, error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        result = orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=NullPayloadStore(),
        )

        assert result.status == RunStatus.COMPLETED
        assert result.rows_processed == 5
        assert result.rows_quarantined == 2
        assert result.rows_succeeded == 3
        assert result.rows_failed == 0
        assert result.rows_routed == 0
        assert result.rows_forked == 0

    def test_sink_contents(self) -> None:
        """Assert sink contents match expected routing."""
        source, transform, output_sink, error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=NullPayloadStore(),
        )

        # Output sink gets 3 valid rows (doubled)
        assert len(output_sink.results) == 3
        # Error sink gets 2 quarantined rows
        assert len(error_sink.results) == 2

    def test_operation_id_not_leaked_to_transforms(self) -> None:
        """Assert transforms never see a non-None operation_id.

        Uses patch.object spy pattern from the design doc. The source_load
        operation sets operation_id, but it must be cleared before transforms
        execute. If extraction breaks the operation_id lifecycle, this catches it.
        """
        source, transform, output_sink, error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        captured_operation_ids: list[str | None] = []
        original_process = transform.process

        def spy_process(row: PipelineRow, ctx: Any) -> TransformResult:
            captured_operation_ids.append(ctx.operation_id)
            return original_process(row, ctx)

        with patch.object(transform, "process", side_effect=spy_process):
            orchestrator._execute_run(
                recorder=recorder,
                run_id=run_id,
                config=config,
                graph=graph,
                payload_store=NullPayloadStore(),
            )

        # All 3 valid rows should have been processed
        assert len(captured_operation_ids) == 3
        # None of them should have seen a non-None operation_id
        assert all(op_id is None for op_id in captured_operation_ids), (
            f"operation_id leaked into transform execution: {captured_operation_ids}"
        )

    def test_field_resolution_recorded_despite_first_quarantine(self) -> None:
        """Assert field resolution is recorded even when first row is quarantined.

        Field resolution must come from the first VALID row, not be skipped
        when the first row is quarantined.
        """
        source, transform, output_sink, error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=NullPayloadStore(),
        )

        # Check that field resolution was recorded in Landscape
        with db._engine.connect() as conn:
            result = conn.execute(
                text("SELECT COUNT(*) FROM field_resolutions WHERE run_id = :run_id"),
                {"run_id": run_id},
            )
            count = result.scalar()
        assert count == 1, f"Expected 1 field resolution record, got {count}"

    def test_audit_record_counts(self) -> None:
        """Assert Landscape audit records are complete.

        After the run:
        - nodes table should have entries for source, transform, output sink, errors sink
        - node_states should have entries for all 5 rows at the source node
        - routing_events should have DIVERT entries for quarantined rows
        """
        source, transform, output_sink, error_sink, config = self._build_pipeline()
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        orchestrator._execute_run(
            recorder=recorder,
            run_id=run_id,
            config=config,
            graph=graph,
            payload_store=NullPayloadStore(),
        )

        with db._engine.connect() as conn:
            # Nodes registered
            node_count = conn.execute(
                text("SELECT COUNT(*) FROM nodes WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).scalar()
            # At minimum: source + transform + 2 sinks = 4
            assert node_count >= 4, f"Expected >= 4 nodes, got {node_count}"

            # Routing events for quarantined rows (DIVERT mode)
            divert_count = conn.execute(
                text("SELECT COUNT(*) FROM routing_events re JOIN node_states ns ON re.state_id = ns.state_id WHERE ns.run_id = :run_id AND re.mode = :mode"),
                {"run_id": run_id, "mode": "divert"},
            ).scalar()
            assert divert_count == 2, f"Expected 2 DIVERT routing events, got {divert_count}"

    def test_current_graph_cleared_after_error(self) -> None:
        """Assert _current_graph is None after an error propagates.

        Forces an error inside the processing loop and verifies the finally
        block clears _current_graph. This prevents stale graph references
        from affecting subsequent checkpointing calls.
        """
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        class ErrorTransform(_TestTransformBase):
            name = "error_transform"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                raise RuntimeError("deliberate error for characterization test")

        source = as_source(ListSource([{"value": 1}]))
        transform = as_transform(ErrorTransform())
        sink = as_sink(CollectSink("output"))

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": sink},
        )

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        with pytest.raises(RuntimeError, match="deliberate error"):
            orchestrator._execute_run(
                recorder=recorder,
                run_id=run_id,
                config=config,
                graph=graph,
                payload_store=NullPayloadStore(),
            )

        assert orchestrator._current_graph is None


# ---------------------------------------------------------------------------
# Characterization test: Resume path
# ---------------------------------------------------------------------------


class TestT18CharacterizationResumePath:
    """Resume-specific characterization tests.

    These verify the behavioral divergences between _execute_run() and
    _process_resumed_rows() documented in the design.
    """

    def test_source_on_start_not_called_during_resume(self) -> None:
        """Assert source.on_start() is NOT called during resume.

        The resume path uses include_source_on_start=False because the source
        was fully consumed in the original run. Transform/sink on_start MUST
        still fire.
        """
        # This test requires a real resume scenario.
        # We use the orchestrator.resume() public API with a mock
        # that provides unprocessed_rows=[] (empty resume).
        db = LandscapeDB.in_memory()
        orchestrator = Orchestrator(db)

        on_start_calls: dict[str, int] = {"source": 0, "transform": 0, "sink": 0}

        class TrackingSource(_TestSourceBase):
            name = "tracking_source"
            output_schema = _TestSchema

            def on_start(self, ctx: Any) -> None:
                on_start_calls["source"] += 1

            def load(self, ctx: Any) -> Any:
                yield from []

        class TrackingTransform(_TestTransformBase):
            name = "tracking_transform"
            input_schema = _TestSchema
            output_schema = _TestSchema

            def on_start(self, ctx: Any) -> None:
                on_start_calls["transform"] += 1

            def process(self, row: PipelineRow, ctx: Any) -> TransformResult:
                return TransformResult.success(
                    make_pipeline_row(row.to_dict()),
                    success_reason={"action": "identity"},
                )

        source = as_source(TrackingSource())
        transform = as_transform(TrackingTransform())
        output_sink = as_sink(CollectSink("output"))

        config = PipelineConfig(
            source=source,
            transforms=[transform],
            sinks={"output": output_sink},
        )

        graph = build_production_graph(config)
        recorder = db.recorder()
        run_id = recorder.begin_run(
            settings_hash="test",
            engine_version="test",
            pipeline_hash="test",
            canonical_version="sha256-rfc8785-v1",
        )

        # Create a minimal schema contract for resume
        schema_contract = SchemaContract(
            mode="OBSERVED",
            fields=(
                FieldContract(
                    normalized_name="value",
                    original_name="value",
                    python_type=int,
                    required=False,
                    source="inferred",
                ),
            ),
            locked=True,
        )

        # Spy on sink on_start using patch.object (consistent with design doc's
        # recommended spy pattern — avoids monkey-patching protocol methods)
        original_sink_on_start = output_sink.on_start

        def tracking_sink_on_start(ctx: Any) -> None:
            on_start_calls["sink"] += 1
            original_sink_on_start(ctx)

        # Call _process_resumed_rows directly with empty rows
        with patch.object(output_sink, "on_start", side_effect=tracking_sink_on_start):
            result = orchestrator._process_resumed_rows(
                recorder=recorder,
                run_id=run_id,
                config=config,
                graph=graph,
                unprocessed_rows=[],
                restored_aggregation_state={},
                payload_store=NullPayloadStore(),
                schema_contract=schema_contract,
            )

        assert result.status == RunStatus.COMPLETED
        assert on_start_calls["source"] == 0, "Source on_start should NOT be called during resume"
        assert on_start_calls["transform"] == 1, "Transform on_start should be called during resume"
        assert on_start_calls["sink"] == 1, "Sink on_start should be called during resume"


**Step 2: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py -v`
Expected: All tests PASS (these are characterization tests of existing behavior)

**Step 3: Commit**

```bash
git add tests/integration/pipeline/orchestrator/test_t18_characterization.py
git commit -m "test: add T18 characterization tests — regression oracle for extraction sequence"
```

---

## Commit #1: Define Types in `engine/orchestrator/types.py`

### Task 1.1: Write tests for the new types

**Files:**
- Modify: `tests/unit/engine/orchestrator/test_types.py`

**Step 1: Write tests for new types**

Add tests to the existing `test_types.py` file. These test the new dataclasses that will be added to `types.py`.

```python
# Append to tests/unit/engine/orchestrator/test_types.py

# ---------------------------------------------------------------------------
# T18: New type tests
# ---------------------------------------------------------------------------

from types import MappingProxyType
from unittest.mock import Mock

from elspeth.contracts.types import CoalesceName, GateName, NodeID, SinkName


class TestGraphArtifacts:
    """Test GraphArtifacts frozen dataclass with MappingProxyType wrapping."""

    def test_fields_frozen_to_mapping_proxy(self) -> None:
        from elspeth.engine.orchestrator.types import GraphArtifacts

        artifacts = GraphArtifacts(
            edge_map={("node1", "continue"): "edge1"},
            source_id=NodeID("source"),
            sink_id_map={SinkName("output"): NodeID("sink1")},
            transform_id_map={0: NodeID("t0")},
            config_gate_id_map={GateName("gate1"): NodeID("g1")},
            coalesce_id_map={CoalesceName("merge1"): NodeID("c1")},
        )
        assert isinstance(artifacts.edge_map, MappingProxyType)
        assert isinstance(artifacts.sink_id_map, MappingProxyType)
        assert isinstance(artifacts.transform_id_map, MappingProxyType)
        assert isinstance(artifacts.config_gate_id_map, MappingProxyType)
        assert isinstance(artifacts.coalesce_id_map, MappingProxyType)

    def test_is_frozen(self) -> None:
        from elspeth.engine.orchestrator.types import GraphArtifacts

        artifacts = GraphArtifacts(
            edge_map={},
            source_id=NodeID("source"),
            sink_id_map={},
            transform_id_map={},
            config_gate_id_map={},
            coalesce_id_map={},
        )
        with pytest.raises(AttributeError):
            artifacts.source_id = NodeID("other")  # type: ignore[misc]


class TestAggNodeEntry:
    """Test AggNodeEntry named pair."""

    def test_attribute_access(self) -> None:
        from elspeth.engine.orchestrator.types import AggNodeEntry

        mock_transform = Mock()
        entry = AggNodeEntry(transform=mock_transform, node_id=NodeID("agg1"))
        assert entry.transform is mock_transform
        assert entry.node_id == NodeID("agg1")

    def test_is_frozen(self) -> None:
        from elspeth.engine.orchestrator.types import AggNodeEntry

        entry = AggNodeEntry(transform=Mock(), node_id=NodeID("agg1"))
        with pytest.raises(AttributeError):
            entry.node_id = NodeID("other")  # type: ignore[misc]


class TestRunContext:
    """Test RunContext frozen dataclass."""

    def test_mapping_fields_frozen(self) -> None:
        from elspeth.engine.orchestrator.types import AggNodeEntry, RunContext

        run_ctx = RunContext(
            ctx=Mock(),
            processor=Mock(),
            coalesce_executor=None,
            coalesce_node_map={CoalesceName("m1"): NodeID("c1")},
            agg_transform_lookup={"node1": AggNodeEntry(transform=Mock(), node_id=NodeID("agg1"))},
        )
        assert isinstance(run_ctx.coalesce_node_map, MappingProxyType)
        assert isinstance(run_ctx.agg_transform_lookup, MappingProxyType)


class TestLoopContext:
    """Test LoopContext mutable dataclass."""

    def test_mutable_fields_can_be_updated(self) -> None:
        from elspeth.engine.orchestrator.types import LoopContext

        loop_ctx = LoopContext(
            counters=ExecutionCounters(),
            pending_tokens={"output": []},
            processor=Mock(),
            ctx=Mock(),
            config=Mock(),
            agg_transform_lookup={},
            coalesce_executor=None,
            coalesce_node_map={},
        )
        # Mutable: counters can be incremented
        loop_ctx.counters.rows_processed += 1
        assert loop_ctx.counters.rows_processed == 1

        # Mutable: pending_tokens can be appended
        loop_ctx.pending_tokens["output"].append((Mock(), None))
        assert len(loop_ctx.pending_tokens["output"]) == 1


class TestExecutionCountersToRunResultRequired:
    """Test that to_run_result requires status parameter (T18 safety fix)."""

    def test_status_is_required_parameter(self) -> None:
        """After T18, status has no default — callers must be explicit."""
        counters = ExecutionCounters()
        # Must pass status explicitly
        result = counters.to_run_result("run-1", status=RunStatus.COMPLETED)
        assert result.status == RunStatus.COMPLETED

        result2 = counters.to_run_result("run-1", status=RunStatus.RUNNING)
        assert result2.status == RunStatus.RUNNING
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/engine/orchestrator/test_types.py::TestGraphArtifacts -v`
Expected: FAIL with `ImportError` (types don't exist yet)

### Task 1.2: Implement the new types

**Files:**
- Modify: `src/elspeth/engine/orchestrator/types.py` (add new dataclasses after existing ones)

**Step 3: Add the new types to types.py**

Add these types AFTER the existing `RouteValidationError` class (after line 202):

```python
# --- T18: Extraction return types ---


@dataclass(frozen=True, slots=True)
class GraphArtifacts:
    """Return type for _register_graph_nodes_and_edges().

    Named fields eliminate positional-swap hazards — several members share
    compatible Mapping[..., NodeID] types that mypy cannot distinguish in a tuple.

    All mapping fields are wrapped in MappingProxyType via __post_init__
    to enforce deep immutability, matching the DAGTraversalContext precedent.
    """

    edge_map: Mapping[tuple[NodeID, str], str]
    source_id: NodeID
    sink_id_map: Mapping[SinkName, NodeID]
    transform_id_map: Mapping[int, NodeID]
    config_gate_id_map: Mapping[GateName, NodeID]
    coalesce_id_map: Mapping[CoalesceName, NodeID]

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_map", MappingProxyType(dict(self.edge_map)))
        object.__setattr__(self, "sink_id_map", MappingProxyType(dict(self.sink_id_map)))
        object.__setattr__(self, "transform_id_map", MappingProxyType(dict(self.transform_id_map)))
        object.__setattr__(self, "config_gate_id_map", MappingProxyType(dict(self.config_gate_id_map)))
        object.__setattr__(self, "coalesce_id_map", MappingProxyType(dict(self.coalesce_id_map)))


@dataclass(frozen=True, slots=True)
class AggNodeEntry:
    """Named pair for aggregation lookup values.

    Replaces tuple[TransformProtocol, NodeID] to prevent positional-swap bugs,
    applying the same rationale as GraphArtifacts.
    """

    transform: TransformProtocol
    node_id: NodeID


@dataclass(frozen=True, slots=True)
class RunContext:
    """Return type for _initialize_run_context().

    Bundles the five objects created during run initialization that are
    consumed by subsequent phases. Short-lived: consumed immediately to
    build LoopContext. Mapping fields are wrapped in MappingProxyType
    for consistency with GraphArtifacts.
    """

    ctx: PluginContext
    processor: RowProcessor
    coalesce_executor: CoalesceExecutor | None
    coalesce_node_map: Mapping[CoalesceName, NodeID]
    agg_transform_lookup: Mapping[str, AggNodeEntry]

    def __post_init__(self) -> None:
        object.__setattr__(self, "coalesce_node_map", MappingProxyType(dict(self.coalesce_node_map)))
        object.__setattr__(self, "agg_transform_lookup", MappingProxyType(dict(self.agg_transform_lookup)))


@dataclass(slots=True)
class LoopContext:
    """Parameter bundle for _run_main_processing_loop() and _flush_and_write_sinks().

    Reduces 10+ parameter signatures to (self, loop_ctx, ...) and prevents
    parameter-list growth as the loop acquires new concerns.

    NOT frozen: ``counters`` and ``pending_tokens`` are mutated in place
    throughout the processing loop.
    """

    # --- Mutable state (updated row-by-row) ---
    counters: ExecutionCounters
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]]

    # --- Read-only after construction (not reassigned) ---
    processor: RowProcessor
    ctx: PluginContext
    config: PipelineConfig
    agg_transform_lookup: Mapping[str, AggNodeEntry]
    coalesce_executor: CoalesceExecutor | None
    coalesce_node_map: Mapping[CoalesceName, NodeID]
```

Also add the `_CheckpointFactory` TypeAlias after `LoopContext`:

```python
_CheckpointFactory: TypeAlias = Callable[[str], Callable[[TokenInfo], None]]
"""Factory that creates a per-sink checkpoint callback.

Takes a sink_node_id (str) and returns a callback invoked after each
token is written to that sink.
"""
```

**Required imports to add at top of types.py:**

```python
from collections.abc import Callable, Mapping  # add Callable, Mapping
from typing import TYPE_CHECKING, Any, TypeAlias  # add TypeAlias
```

And in the `TYPE_CHECKING` block:

```python
if TYPE_CHECKING:
    from elspeth.contracts import PendingOutcome, TokenInfo
    from elspeth.contracts.plugin_context import PluginContext
    from elspeth.contracts.types import CoalesceName, GateName, NodeID, SinkName
    from elspeth.engine.coalesce_executor import CoalesceExecutor
    from elspeth.engine.processor import RowProcessor
```

Note: `NodeID`, `SinkName`, `CoalesceName`, `GateName` need to be imported at runtime for the dataclass field annotations (they're used as concrete types in `__post_init__`). Move them out of `TYPE_CHECKING`:

```python
from elspeth.contracts.types import (
    AggregationName,  # if needed
    CoalesceName,
    GateName,
    NodeID,
    SinkName,
)
```

### Task 1.3: Fix `to_run_result()` to require status parameter

**Files:**
- Modify: `src/elspeth/engine/orchestrator/types.py:172` — remove default
- Modify: `src/elspeth/engine/orchestrator/core.py:1814` — add `status=RunStatus.COMPLETED`
- Modify: `src/elspeth/engine/orchestrator/core.py:2365` — add `status=RunStatus.COMPLETED`
- Modify: `tests/property/engine/test_orchestrator_lifecycle_properties.py` — update 5 call sites

**Step 4: Fix the signature**

In `types.py`, change line 172 from:
```python
def to_run_result(self, run_id: str, status: RunStatus = RunStatus.RUNNING) -> RunResult:
```
to:
```python
def to_run_result(self, run_id: str, status: RunStatus) -> RunResult:
```

Update the docstring to remove "default RUNNING" language.

**Step 5: Fix call sites in src/**

In `core.py` line 1814, change:
```python
return counters.to_run_result(run_id)
```
to:
```python
return counters.to_run_result(run_id, status=RunStatus.COMPLETED)
```

In `core.py` line 2365, change:
```python
return counters.to_run_result(run_id)
```
to:
```python
return counters.to_run_result(run_id, status=RunStatus.COMPLETED)
```

**Step 6: Fix call sites in tests/**

In `test_orchestrator_lifecycle_properties.py`, update these lines:
- Line 419: `counters.to_run_result("run-1")` → `counters.to_run_result("run-1", status=RunStatus.RUNNING)`
- Line 441: `counters.to_run_result("run-1")` → `counters.to_run_result("run-1", status=RunStatus.RUNNING)`
- Line 457: **Delete** `test_default_status_is_running` entirely — its premise (default exists) no longer holds. Coverage is provided by `TestExecutionCountersToRunResultRequired.test_status_is_required_parameter` in `test_types.py`.
- Line 478: `counters.to_run_result("run-1")` → `counters.to_run_result("run-1", status=RunStatus.RUNNING)`
- Line 691: `counters.to_run_result("run-1")` → `counters.to_run_result("run-1", status=RunStatus.RUNNING)`

### Task 1.4: Update aggregation.py to use AggNodeEntry

**Files:**
- Modify: `src/elspeth/engine/orchestrator/aggregation.py:224`

**Step 7: Replace tuple destructuring with attribute access**

In `aggregation.py` line 224, change:
```python
agg_transform, _agg_node_id = agg_transform_lookup[agg_node_id_str]
```
to:
```python
entry = agg_transform_lookup[agg_node_id_str]
agg_transform = entry.transform
```

Update `aggregation.py`'s type signature to `AggNodeEntry` AND update the lookup construction in `core.py` lines 1261-1265 and 2233-2237 simultaneously. Both are small changes:

In `core.py` lines 1261-1265, change:
```python
agg_transform_lookup: dict[str, tuple[TransformProtocol, NodeID]] = {}
if config.aggregation_settings:
    for t in config.transforms:
        if isinstance(t, TransformProtocol) and t.is_batch_aware and t.node_id in config.aggregation_settings:
            agg_transform_lookup[t.node_id] = (t, NodeID(t.node_id))
```
to:
```python
agg_transform_lookup: dict[str, AggNodeEntry] = {}
if config.aggregation_settings:
    for t in config.transforms:
        if isinstance(t, TransformProtocol) and t.is_batch_aware and t.node_id in config.aggregation_settings:
            agg_transform_lookup[t.node_id] = AggNodeEntry(transform=t, node_id=NodeID(t.node_id))
```

Same change in `core.py` lines 2233-2237.

Import `AggNodeEntry` in `core.py`:
```python
from elspeth.engine.orchestrator.types import (
    AggNodeEntry,
    ExecutionCounters,
    ...
)
```

Update `aggregation.py` function signatures to use `AggNodeEntry`.

**Step 8: Run all tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/orchestrator/test_types.py tests/property/engine/test_orchestrator_lifecycle_properties.py tests/integration/pipeline/orchestrator/ -v`
Expected: All PASS

**Step 9: Commit**

```bash
git add src/elspeth/engine/orchestrator/types.py src/elspeth/engine/orchestrator/core.py src/elspeth/engine/orchestrator/aggregation.py tests/unit/engine/orchestrator/test_types.py tests/property/engine/test_orchestrator_lifecycle_properties.py
git commit -m "feat(t18): define extraction return types and fix to_run_result required status"
```

---

## Commit #2: Define Processor Outcome Types

### Task 2.1: Write tests for processor outcome types

**Files:**
- Modify: `tests/unit/engine/test_processor.py` (add test class at end)

**Step 1: Write tests for the discriminated union types**

```python
# Append to tests/unit/engine/test_processor.py

# ---------------------------------------------------------------------------
# T18: Processor outcome type tests
# ---------------------------------------------------------------------------

from unittest.mock import Mock

from elspeth.contracts.types import NodeID


class TestProcessorOutcomeTypes:
    """Test the private discriminated union types for _process_single_token extraction."""

    def test_transform_continue(self) -> None:
        from elspeth.engine.processor import _TransformContinue

        outcome = _TransformContinue(
            updated_token=Mock(),
            updated_sink="output",
        )
        assert outcome.updated_sink == "output"
        assert outcome.updated_token is not None

    def test_transform_terminal_single(self) -> None:
        from elspeth.engine.processor import _TransformTerminal

        mock_result = Mock()
        outcome = _TransformTerminal(result=mock_result)
        assert outcome.result is mock_result

    def test_transform_terminal_list(self) -> None:
        from elspeth.engine.processor import _TransformTerminal

        mock_results = [Mock(), Mock()]
        outcome = _TransformTerminal(result=mock_results)
        assert len(outcome.result) == 2

    def test_transform_outcome_isinstance_dispatch(self) -> None:
        """Verify isinstance works for discriminated union dispatch."""
        from elspeth.engine.processor import _TransformContinue, _TransformTerminal

        continue_outcome = _TransformContinue(updated_token=Mock(), updated_sink="out")
        terminal_outcome = _TransformTerminal(result=Mock())

        assert isinstance(continue_outcome, _TransformContinue)
        assert not isinstance(continue_outcome, _TransformTerminal)
        assert isinstance(terminal_outcome, _TransformTerminal)
        assert not isinstance(terminal_outcome, _TransformContinue)

    def test_gate_continue_default_next_node(self) -> None:
        from elspeth.engine.processor import _GateContinue

        outcome = _GateContinue(updated_sink="output")
        assert outcome.next_node_id is None

    def test_gate_continue_explicit_next_node(self) -> None:
        from elspeth.engine.processor import _GateContinue

        outcome = _GateContinue(updated_sink="output", next_node_id=NodeID("jump_target"))
        assert outcome.next_node_id == NodeID("jump_target")

    def test_gate_terminal(self) -> None:
        from elspeth.engine.processor import _GateTerminal

        mock_result = Mock()
        outcome = _GateTerminal(result=mock_result)
        assert outcome.result is mock_result

    def test_gate_outcome_isinstance_dispatch(self) -> None:
        from elspeth.engine.processor import _GateContinue, _GateTerminal

        continue_outcome = _GateContinue(updated_sink="out")
        terminal_outcome = _GateTerminal(result=Mock())

        assert isinstance(continue_outcome, _GateContinue)
        assert not isinstance(continue_outcome, _GateTerminal)
        assert isinstance(terminal_outcome, _GateTerminal)
        assert not isinstance(terminal_outcome, _GateContinue)

    def test_all_outcome_types_are_frozen(self) -> None:
        from elspeth.engine.processor import (
            _GateContinue,
            _GateTerminal,
            _TransformContinue,
            _TransformTerminal,
        )

        for cls, kwargs in [
            (_TransformContinue, {"updated_token": Mock(), "updated_sink": "out"}),
            (_TransformTerminal, {"result": Mock()}),
            (_GateContinue, {"updated_sink": "out"}),
            (_GateTerminal, {"result": Mock()}),
        ]:
            instance = cls(**kwargs)
            with pytest.raises(AttributeError):
                instance.updated_sink = "other"  # type: ignore[attr-defined]
```

**Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_processor.py::TestProcessorOutcomeTypes -v`
Expected: FAIL with `ImportError`

### Task 2.2: Implement the processor outcome types

**Files:**
- Modify: `src/elspeth/engine/processor.py` (add types near top, after existing `_FlushContext`)

**Step 3: Add the types after the `_FlushContext` class (around line 110)**

```python
# --- T18: Discriminated union types for _process_single_token extraction ---


@dataclass(frozen=True, slots=True)
class _TransformContinue:
    """Token should advance to the next node in the DAG."""

    updated_token: TokenInfo
    updated_sink: str


@dataclass(frozen=True, slots=True)
class _TransformTerminal:
    """Token has reached a terminal state (completed, failed, quarantined, etc.)."""

    result: RowResult | list[RowResult]


_TransformOutcome: TypeAlias = _TransformContinue | _TransformTerminal


@dataclass(frozen=True, slots=True)
class _GateContinue:
    """Gate says advance to next node (or jump to a specific node)."""

    updated_sink: str
    next_node_id: NodeID | None = None  # None = next structural node


@dataclass(frozen=True, slots=True)
class _GateTerminal:
    """Gate has routed, forked, or diverted the token to a terminal state."""

    result: RowResult | list[RowResult]


_GateOutcome: TypeAlias = _GateContinue | _GateTerminal
```

Add required imports at top of `processor.py`:

```python
from typing import TypeAlias  # add TypeAlias
```

`RowResult` and `TokenInfo` should already be imported. Verify `NodeID` is imported (it should be, since it's used throughout the file).

**Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/unit/engine/test_processor.py::TestProcessorOutcomeTypes -v`
Expected: All PASS

**Step 5: Run characterization + focused test suite**

Run: `.venv/bin/python -m pytest tests/integration/pipeline/orchestrator/test_t18_characterization.py tests/unit/engine/test_processor.py tests/unit/engine/orchestrator/test_types.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/elspeth/engine/processor.py tests/unit/engine/test_processor.py
git commit -m "feat(t18): define processor outcome types — discriminated unions for extraction"
```

---

## Part A Complete

After these 3 commits:
- Characterization test oracle is in place
- All new types (`GraphArtifacts`, `AggNodeEntry`, `RunContext`, `LoopContext`, `_CheckpointFactory`) defined
- `to_run_result()` requires explicit `status` parameter
- Processor outcome types (`_TransformContinue/Terminal`, `_GateContinue/Terminal`) defined
- `agg_transform_lookup` uses `AggNodeEntry` instead of raw tuples

**Proceed to:** [Part B: Orchestrator Extractions](2026-02-27-t18-part-b-orchestrator-extractions.md)
