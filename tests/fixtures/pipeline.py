# tests/fixtures/pipeline.py
"""Pipeline builder helpers for integration/e2e tests.

Uses ExecutionGraph.from_plugin_instances() — the real production assembly
path. This prevents BUG-LINEAGE-01 from hiding in test infrastructure.

For unit/property tests that need lightweight graph construction,
use make_graph_linear/make_graph_fork from fixtures/factories.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from tests.fixtures.plugins import CollectSink, ListSource

if TYPE_CHECKING:
    from elspeth.engine.orchestrator import PipelineConfig


@dataclass
class PipelineResult:
    """Result from run_pipeline() helper."""

    run_id: str
    sink_results: dict[str, list[dict[str, Any]]]
    landscape_db: LandscapeDB
    recorder: LandscapeRecorder


def build_linear_pipeline(
    source_data: list[dict[str, Any]],
    transforms: list[Any] | None = None,
    sink: CollectSink | None = None,
    *,
    source_name: str = "list_source",
    sink_name: str = "default",
) -> tuple[ListSource, list[Any], dict[str, CollectSink], ExecutionGraph]:
    """Build a linear pipeline: source -> transforms -> sink.

    Uses ExecutionGraph.from_plugin_instances() for production-path fidelity.

    Returns:
        (source, transforms, sinks_dict, graph)
    """
    source = ListSource(source_data, name=source_name, on_success=sink_name)
    transforms = transforms or []
    if sink is None:
        sink = CollectSink(sink_name)
    sinks = {sink_name: sink}

    # Set on_success on the terminal transform (last non-gate transform)
    _set_terminal_on_success(transforms, sink_name)

    graph = ExecutionGraph.from_plugin_instances(
        source=source,
        transforms=transforms,
        sinks=sinks,
        aggregations={},
        gates=[],
    )
    return source, transforms, sinks, graph


def build_fork_pipeline(
    source_data: list[dict[str, Any]],
    gate: Any,
    branch_transforms: dict[str, list[Any]],
    sinks: dict[str, CollectSink] | None = None,
    *,
    source_name: str = "list_source",
    sink_name: str = "default",
    coalesce_settings: list[Any] | None = None,
) -> tuple[ListSource, list[Any], dict[str, CollectSink], ExecutionGraph]:
    """Build a fork/join pipeline with gate routing.

    Uses ExecutionGraph.from_plugin_instances() for production-path fidelity.
    """
    source = ListSource(source_data, name=source_name, on_success=sink_name)

    all_transforms: list[Any] = []
    for branch_list in branch_transforms.values():
        all_transforms.extend(branch_list)

    if sinks is None:
        sinks = {sink_name: CollectSink(sink_name)}

    graph = ExecutionGraph.from_plugin_instances(
        source=source,
        transforms=all_transforms,
        sinks=sinks,
        aggregations={},
        gates=[gate],
        coalesce_settings=coalesce_settings,
    )
    return source, all_transforms, sinks, graph


def build_aggregation_pipeline(
    source_data: list[dict[str, Any]],
    aggregation_transform: Any,
    aggregation_settings: Any,
    sink: CollectSink | None = None,
    *,
    source_name: str = "list_source",
    sink_name: str = "default",
    agg_name: str = "batch",
) -> tuple[ListSource, dict[str, tuple[Any, Any]], dict[str, CollectSink], ExecutionGraph]:
    """Build an aggregation pipeline.

    Uses ExecutionGraph.from_plugin_instances() for production-path fidelity.
    """
    source = ListSource(source_data, name=source_name, on_success=sink_name)
    if sink is None:
        sink = CollectSink(sink_name)
    sinks = {sink_name: sink}
    aggregations = {agg_name: (aggregation_transform, aggregation_settings)}

    graph = ExecutionGraph.from_plugin_instances(
        source=source,
        transforms=[],
        sinks=sinks,
        aggregations=aggregations,
        gates=[],
    )
    return source, aggregations, sinks, graph


def build_production_graph(
    config: PipelineConfig,
) -> ExecutionGraph:
    """Build graph from PipelineConfig using production code path.

    Replaces tests/engine/orchestrator_test_helpers.build_production_graph.
    Uses ExecutionGraph.from_plugin_instances() — the real assembly path.
    """
    from elspeth.core.config import AggregationSettings
    from elspeth.plugins.protocols import TransformProtocol
    from tests.fixtures.base_classes import _TestTransformBase

    row_transforms: list[TransformProtocol] = []
    aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]] = {}

    for transform in config.transforms:
        if isinstance(transform, TransformProtocol):
            row_transforms.append(transform)

    for agg_name, agg_settings in config.aggregation_settings.items():

        class _AggTransform(_TestTransformBase):
            name = agg_settings.plugin

            def process(self, row: dict[str, Any], ctx: Any) -> Any:
                from elspeth.plugins.results import TransformResult

                return TransformResult.success(row, success_reason={"action": "test"})

        agg_transform = _AggTransform()
        # Propagate on_success from aggregation options to the transform instance
        # (production code does this during plugin instantiation; test infrastructure
        # must replicate the wiring since it creates transforms directly)
        on_success = agg_settings.options.get("on_success")
        if on_success:
            agg_transform._on_success = on_success
        aggregations[agg_name] = (agg_transform, agg_settings)  # type: ignore[assignment]

    return ExecutionGraph.from_plugin_instances(
        source=config.source,
        transforms=row_transforms,
        sinks=config.sinks,
        aggregations=aggregations,
        gates=list(config.gates),
        coalesce_settings=list(config.coalesce_settings) if config.coalesce_settings else None,
    )


def _set_terminal_on_success(transforms: list[Any], sink_name: str) -> None:
    """Set on_success on the terminal transform in a linear pipeline.

    The terminal transform is the last non-gate transform in the list.
    This is a test helper — production code sets on_success via config.
    """
    from elspeth.plugins.protocols import GateProtocol

    # Find the last non-gate transform
    for i in range(len(transforms) - 1, -1, -1):
        if not isinstance(transforms[i], GateProtocol):
            transforms[i]._on_success = sink_name
            return
