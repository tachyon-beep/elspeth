# tests/fixtures/factories.py
"""Test-only factories and re-exports from elspeth.testing.

Layer 1 (elspeth.testing): Production-type factories — no mocks, no fakes.
Layer 2 (this file):        Test infrastructure — mocks, graph builders, DB population.

Usage:
    from tests.fixtures.factories import make_row, make_context, make_graph_linear
    # make_row comes from elspeth.testing (re-exported)
    # make_context and make_graph_linear are test-only (defined here)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock
from uuid import uuid4

if TYPE_CHECKING:
    from elspeth.contracts.plugin_context import PluginContext
    from elspeth.core.dag import ExecutionGraph, WiredTransform
    from elspeth.plugins.protocols import TransformProtocol

# --- Re-export all production factories for single-import convenience ---
from elspeth.testing import (  # noqa: F401
    make_artifact,
    make_contract,
    make_contract_audit_record,
    make_error,
    make_error_reason,
    make_exception_result,
    make_execution_counters,
    make_external_call_completed,
    make_failure_info,
    make_field,
    make_flush_result,
    make_gate_continue,
    make_gate_fork,
    make_gate_route,
    make_phase_completed,
    make_phase_started,
    make_pipeline_config,
    make_pipeline_row,
    make_row,
    make_row_result,
    make_run_result,
    make_run_summary,
    make_source_row,
    make_source_row_quarantined,
    make_success,
    make_success_multi,
    make_success_reason,
    make_token_completed,
    make_token_info,
    make_transform_completed,
    make_transform_error_token,
    make_validation_error_token,
)

# =============================================================================
# PluginContext — Uses Mock(), so test-only
# =============================================================================


def make_context(
    *,
    run_id: str = "test-run",
    state_id: str = "state-123",
    token: Any | None = None,
    config: dict[str, Any] | None = None,
    landscape: Any | None = None,
) -> PluginContext:
    """Build a PluginContext with sensible test defaults.

    Usage:
        ctx = make_context()                            # Minimal (mock landscape)
        ctx = make_context(state_id="state-retry-3")    # Custom state_id
        ctx = make_context(landscape=recorder)           # Real landscape recorder
    """
    from elspeth.contracts.plugin_context import PluginContext

    if landscape is None:
        landscape = Mock()
        landscape.record_external_call = Mock()
        landscape.record_call = Mock()

    if token is None:
        token = make_token_info()

    return PluginContext(
        run_id=run_id,
        landscape=landscape,
        state_id=state_id,
        config=config or {},
        token=token,
    )


# =============================================================================
# ExecutionGraph — Manual construction for unit tests ONLY
# =============================================================================
#
# TIER RULES (BUG-LINEAGE-01 prevention):
#
#   unit/         → make_graph_linear(), make_graph_fork() are OK.
#                   These test graph algorithms in isolation (cycle detection,
#                   topo sort, visualization) where fake plugin names are fine.
#
#   property/     → make_graph_linear(), make_graph_fork() are OK.
#                   Property tests verify graph invariants (acyclicity, single
#                   source) and don't need real plugin wiring.
#
#   integration/  → MUST use ExecutionGraph.from_plugin_instances().
#   e2e/            These tiers test the real pipeline assembly path. Manual
#   performance/    construction would hide mapping bugs (BUG-LINEAGE-01).
#
# If you're writing an integration test and tempted to use make_graph_linear(),
# that's a sign your test setup should go through the full plugin instantiation
# path instead. See fixtures/pipeline.py for helpers that do this correctly.
# =============================================================================


def make_graph_linear(
    *node_names: str,
    source_plugin: str = "test-source",
    sink_plugin: str = "test-sink",
    transform_plugin: str = "test-transform",
) -> ExecutionGraph:
    """Build a linear ExecutionGraph: source -> t1 -> t2 -> ... -> sink.

    WARNING: For unit/property tests only. Integration+ tests MUST use
    ExecutionGraph.from_plugin_instances() to exercise the real assembly path.

    Usage:
        graph = make_graph_linear()                        # source -> sink
        graph = make_graph_linear("enrich", "classify")    # source -> t1 -> t2 -> sink
    """
    from elspeth.contracts.enums import NodeType
    from elspeth.core.dag import ExecutionGraph

    graph = ExecutionGraph()
    source = "source-node"
    sink = "sink-node"

    graph.add_node(source, node_type=NodeType.SOURCE, plugin_name=source_plugin, config={})

    prev = source
    for name in node_names:
        graph.add_node(name, node_type=NodeType.TRANSFORM, plugin_name=transform_plugin, config={})
        graph.add_edge(prev, name, label="continue")
        prev = name

    graph.add_node(sink, node_type=NodeType.SINK, plugin_name=sink_plugin, config={})
    graph.add_edge(prev, sink, label="continue")

    return graph


def make_graph_fork(
    branches: dict[str, list[str]],
    *,
    gate_name: str = "gate-node",
    coalesce_name: str = "coalesce-node",
) -> ExecutionGraph:
    """Build a fork/join ExecutionGraph.

    WARNING: For unit/property tests only. Integration+ tests MUST use
    ExecutionGraph.from_plugin_instances() to exercise the real assembly path.

    Usage:
        graph = make_graph_fork({
            "path_a": ["transform_a1", "transform_a2"],
            "path_b": ["transform_b1"],
        })
    """
    from elspeth.contracts.enums import NodeType
    from elspeth.core.dag import ExecutionGraph

    graph = ExecutionGraph()
    source = "source-node"
    sink = "sink-node"

    graph.add_node(source, node_type=NodeType.SOURCE, plugin_name="test-source", config={})
    graph.add_node(gate_name, node_type=NodeType.GATE, plugin_name="test-gate", config={})
    graph.add_edge(source, gate_name, label="continue")

    # Add coalesce node once (before the loop to avoid duplicate adds)
    graph.add_node(coalesce_name, node_type=NodeType.COALESCE, plugin_name="coalesce", config={})

    for branch_label, transforms in branches.items():
        prev = gate_name
        for t_name in transforms:
            graph.add_node(t_name, node_type=NodeType.TRANSFORM, plugin_name="test-transform", config={})
            graph.add_edge(prev, t_name, label=branch_label if prev == gate_name else "continue")
            prev = t_name
        graph.add_edge(prev, coalesce_name, label="continue")

    graph.add_node(sink, node_type=NodeType.SINK, plugin_name="test-sink", config={})
    graph.add_edge(coalesce_name, sink, label="continue")

    return graph


def _set_transform_routing(
    transform: TransformProtocol,
    *,
    on_success: str | None,
    on_error: str | None,
) -> None:
    """Set routing fields on test transforms with protocol-compatible fallback."""
    try:
        transform.on_success = on_success
    except AttributeError:
        transform._on_success = on_success

    try:
        transform.on_error = on_error
    except AttributeError:
        transform._on_error = on_error


def wire_transforms(
    transforms: list[TransformProtocol],
    *,
    source_connection: str = "source_out",
    final_sink: str = "output",
    names: list[str] | None = None,
) -> list[WiredTransform]:
    """Create WiredTransform entries with deterministic sequential wiring.

    This is a test helper that mirrors production config-driven routing:
    source_connection -> t0 -> t1 -> ... -> tN -> final_sink.
    """
    from elspeth.core.config import TransformSettings
    from elspeth.core.dag import WiredTransform

    if names is not None and len(names) != len(transforms):
        raise ValueError(f"names length ({len(names)}) must match transforms length ({len(transforms)})")

    wired: list[WiredTransform] = []
    total = len(transforms)
    for index, transform in enumerate(transforms):
        input_connection = source_connection if index == 0 else f"conn_{index - 1}_{index}"
        on_success = final_sink if index == total - 1 else f"conn_{index}_{index + 1}"
        node_name = names[index] if names is not None else f"{transform.name}_{index}"
        on_error = getattr(transform, "on_error", None)

        settings = TransformSettings(
            name=node_name,
            plugin=transform.name,
            input=input_connection,
            on_success=on_success,
            on_error=on_error,
            options={},
        )
        _set_transform_routing(transform, on_success=on_success, on_error=on_error)
        wired.append(WiredTransform(plugin=transform, settings=settings))

    return wired


# =============================================================================
# Run/Landscape Setup — Eliminate begin_run()/complete_run() boilerplate
# =============================================================================


def make_run_id() -> str:
    """Generate a unique run ID for test isolation."""
    return f"test-run-{uuid4().hex[:12]}"


def make_run_record(
    recorder: Any,
    *,
    config: dict[str, Any] | None = None,
    canonical_version: str = "sha256-rfc8785-v1",
) -> Any:
    """Begin a run and return the RunRecord.

    Usage:
        run = make_run_record(recorder)
        assert run.run_id is not None
    """
    return recorder.begin_run(
        config=config or {},
        canonical_version=canonical_version,
    )


def populate_run(
    recorder: Any,
    db: Any,
    *,
    row_count: int = 5,
    fail_rows: set[int] | None = None,
    graph: Any | None = None,
) -> dict[str, Any]:
    """Create a complete run with rows, tokens, and outcomes.

    Returns dict with run_id, row_ids, token_ids for assertions.

    Usage:
        result = populate_run(recorder, db, row_count=10, fail_rows={3, 7})
        assert len(result["row_ids"]) == 10
        assert result["row_ids"][3] in result["failed_row_ids"]
    """
    from elspeth.contracts.enums import (
        Determinism,
        NodeType,
        RowOutcome,
        RunStatus,
    )
    from elspeth.core.landscape.schema import (
        nodes_table,
        rows_table,
        runs_table,
        token_outcomes_table,
        tokens_table,
    )

    fail_rows = fail_rows or set()
    run_id = make_run_id()
    now = datetime.now(UTC)

    if graph is None:
        graph = make_graph_linear()

    row_ids = [f"row-{i:03d}" for i in range(row_count)]
    token_ids = [f"tok-{i:03d}" for i in range(row_count)]
    failed_row_ids = {row_ids[i] for i in fail_rows}

    with db.engine.connect() as conn:
        conn.execute(
            runs_table.insert().values(
                run_id=run_id,
                started_at=now,
                config_hash="test",
                settings_json="{}",
                canonical_version="sha256-rfc8785-v1",
                status=RunStatus.COMPLETED,
            )
        )
        conn.execute(
            nodes_table.insert().values(
                node_id="source-node",
                run_id=run_id,
                plugin_name="test",
                node_type=NodeType.SOURCE,
                plugin_version="1.0",
                determinism=Determinism.DETERMINISTIC,
                config_hash="x",
                config_json="{}",
                registered_at=now,
            )
        )
        conn.execute(
            nodes_table.insert().values(
                node_id="sink-node",
                run_id=run_id,
                plugin_name="test",
                node_type=NodeType.SINK,
                plugin_version="1.0",
                determinism=Determinism.DETERMINISTIC,
                config_hash="x",
                config_json="{}",
                registered_at=now,
            )
        )
        for i in range(row_count):
            conn.execute(
                rows_table.insert().values(
                    row_id=row_ids[i],
                    run_id=run_id,
                    source_node_id="source-node",
                    row_index=i,
                    source_data_hash=f"hash{i}",
                    created_at=now,
                )
            )
            conn.execute(
                tokens_table.insert().values(
                    token_id=token_ids[i],
                    row_id=row_ids[i],
                    created_at=now,
                )
            )
            outcome = RowOutcome.FAILED if i in fail_rows else RowOutcome.COMPLETED
            conn.execute(
                token_outcomes_table.insert().values(
                    outcome_id=f"outcome-{i:03d}",
                    run_id=run_id,
                    token_id=token_ids[i],
                    outcome=outcome.value,
                    is_terminal=1,
                    recorded_at=now,
                    sink_name="sink-node",
                )
            )
        conn.commit()

    return {
        "run_id": run_id,
        "row_ids": row_ids,
        "token_ids": token_ids,
        "failed_row_ids": failed_row_ids,
        "graph": graph,
    }


# =============================================================================
# Coalesce / Batch Checkpoint — Structural dict factories
# =============================================================================


def make_coalesce_context(
    *,
    policy: str = "manual",
    merge_strategy: str = "union",
    expected_branches: list[str] | None = None,
    branches_arrived: list[str] | None = None,
    wait_duration_ms: float = 150.0,
) -> dict[str, Any]:
    """Build a coalesce context_after dict.

    This dict has a well-defined 8-key schema in coalesce_executor.py:562-580
    but no TypedDict enforcement.
    """
    branches = expected_branches or ["a", "b"]
    arrived = branches_arrived or branches
    return {
        "coalesce_context": {
            "policy": policy,
            "merge_strategy": merge_strategy,
            "expected_branches": branches,
            "branches_arrived": arrived,
            "branches_lost": {},
            "arrival_order": [{"branch": b, "arrival_offset_ms": float(i * 50)} for i, b in enumerate(arrived)],
            "wait_duration_ms": wait_duration_ms,
        }
    }


def make_batch_checkpoint(
    *,
    batch_id: str = "batch-123",
    row_count: int = 3,
) -> dict[str, Any]:
    """Build a batch checkpoint dict.

    Matches the implicit schema in azure_batch.py:160-180.
    """
    return {
        "batch_id": batch_id,
        "submitted_at": datetime.now(UTC).isoformat(),
        "row_mapping": {f"custom_{i}": {"id": i, "text": f"row-{i}"} for i in range(row_count)},
        "template_errors": [],
        "requests": {f"custom_{i}": {"model": "gpt-4", "messages": []} for i in range(row_count)},
    }
