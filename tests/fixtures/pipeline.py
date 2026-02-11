# tests/fixtures/pipeline.py
"""Pipeline builder helpers for integration/e2e tests.

Uses ExecutionGraph.from_plugin_instances() — the real production assembly
path. This prevents BUG-LINEAGE-01 from hiding in test infrastructure.

For unit/property tests that need lightweight graph construction,
use make_graph_linear/make_graph_fork from fixtures/factories.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from elspeth.core.config import SourceSettings
from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from elspeth.plugins.protocols import SinkProtocol, SourceProtocol
from tests.fixtures.factories import wire_transforms
from tests.fixtures.plugins import CollectSink, ListSource

if TYPE_CHECKING:
    from elspeth.core.config import AggregationSettings, GateSettings
    from elspeth.core.dag import WiredTransform
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
    transforms = transforms or []
    source_connection = f"{source_name}_out"
    source_on_success = source_connection if transforms else sink_name
    source = ListSource(source_data, name=source_name, on_success=source_on_success)
    source_settings = SourceSettings(plugin=source.name, on_success=source_on_success, options={})
    wired_transforms = wire_transforms(
        transforms,
        source_connection=source_connection,
        final_sink=sink_name,
    )

    if sink is None:
        sink = CollectSink(sink_name)
    sinks = {sink_name: sink}

    graph = ExecutionGraph.from_plugin_instances(
        source=cast(SourceProtocol, source),
        source_settings=source_settings,
        transforms=wired_transforms,
        sinks=cast("dict[str, SinkProtocol]", sinks),
        aggregations={},
        gates=[],
    )
    return source, transforms, sinks, graph


def build_fork_pipeline(
    source_data: list[dict[str, Any]],
    gate: GateSettings,
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
    source_connection = f"{source_name}_out"
    source = ListSource(source_data, name=source_name, on_success=source_connection)
    source_settings = SourceSettings(plugin=source.name, on_success=source_connection, options={})

    all_transforms: list[Any] = []
    all_wired_transforms: list[WiredTransform] = []
    for branch_name, branch_list in branch_transforms.items():
        all_transforms.extend(branch_list)
        if not branch_list:
            continue
        branch_names = [f"{branch_name}_{idx}" for idx, _ in enumerate(branch_list)]
        all_wired_transforms.extend(
            wire_transforms(
                branch_list,
                source_connection=branch_name,
                final_sink=sink_name,
                names=branch_names,
            )
        )

    if sinks is None:
        sinks = {sink_name: CollectSink(sink_name)}

    graph = ExecutionGraph.from_plugin_instances(
        source=cast(SourceProtocol, source),
        source_settings=source_settings,
        transforms=all_wired_transforms,
        sinks=cast("dict[str, SinkProtocol]", sinks),
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
    source_connection = aggregation_settings.input
    source = ListSource(source_data, name=source_name, on_success=source_connection)
    source_settings = SourceSettings(plugin=source.name, on_success=source_connection, options={})

    if aggregation_settings.on_success is None:
        aggregation_settings = aggregation_settings.model_copy(update={"on_success": sink_name})
    _set_transform_routing(aggregation_transform, on_success=aggregation_settings.on_success)

    if sink is None:
        sink = CollectSink(sink_name)
    sinks = {sink_name: sink}
    aggregations = {agg_name: (aggregation_transform, aggregation_settings)}

    graph = ExecutionGraph.from_plugin_instances(
        source=cast(SourceProtocol, source),
        source_settings=source_settings,
        transforms=[],
        sinks=cast("dict[str, SinkProtocol]", sinks),
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
    from elspeth.plugins.protocols import TransformProtocol
    from tests.fixtures.base_classes import _TestTransformBase

    row_transforms: list[TransformProtocol] = []
    aggregations: dict[str, tuple[TransformProtocol, AggregationSettings]] = {}

    for transform in config.transforms:
        if isinstance(transform, TransformProtocol):
            row_transforms.append(transform)

    default_sink = next(iter(config.sinks.keys()))
    if row_transforms:
        source_on_success = "source_out"
        final_destination = default_sink
    else:
        source_on_success = default_sink
        final_destination = default_sink

    if config.gates:
        first_gate_input = config.gates[0].input
        final_destination = first_gate_input
        if not row_transforms:
            source_on_success = first_gate_input
    elif config.aggregation_settings:
        first_aggregation_input = next(iter(config.aggregation_settings.values())).input
        final_destination = first_aggregation_input
        if not row_transforms:
            source_on_success = first_aggregation_input

    config.source.on_success = source_on_success
    source_settings = SourceSettings(plugin=config.source.name, on_success=source_on_success, options={})
    wired_row_transforms = wire_transforms(
        row_transforms,
        source_connection=source_on_success,
        final_sink=final_destination,
    )

    for agg_name, agg_settings in config.aggregation_settings.items():

        class _AggTransform(_TestTransformBase):
            name = agg_settings.plugin

            def process(self, row: Any, ctx: Any) -> Any:
                from elspeth.plugins.results import TransformResult

                return TransformResult.success(row, success_reason={"action": "passthrough"})

        agg_transform = _AggTransform()
        if agg_settings.on_success is None:
            agg_settings = agg_settings.model_copy(update={"on_success": default_sink})
        _set_transform_routing(agg_transform, on_success=agg_settings.on_success)
        aggregations[agg_name] = (agg_transform, agg_settings)  # type: ignore[assignment]

    return ExecutionGraph.from_plugin_instances(
        source=config.source,
        source_settings=source_settings,
        transforms=wired_row_transforms,
        sinks=config.sinks,
        aggregations=aggregations,
        gates=list(config.gates),
        coalesce_settings=list(config.coalesce_settings) if config.coalesce_settings else None,
    )


def _set_transform_routing(transform: Any, *, on_success: str | None) -> None:
    """Set on_success for test transforms."""
    transform.on_success = on_success
