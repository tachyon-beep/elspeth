# tests_v2/fixtures/pipeline.py
"""Pipeline builder helpers for integration/e2e tests.

Uses ExecutionGraph.from_plugin_instances() — the real production assembly
path. This prevents BUG-LINEAGE-01 from hiding in test infrastructure.

For unit/property tests that need lightweight graph construction,
use make_graph_linear/make_graph_fork from fixtures/factories.py instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder
from tests_v2.fixtures.plugins import CollectSink, ListSource


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
    source = ListSource(source_data, name=source_name)
    transforms = transforms or []
    if sink is None:
        sink = CollectSink(sink_name)
    sinks = {sink_name: sink}

    graph = ExecutionGraph.from_plugin_instances(
        source=source,
        transforms=transforms,
        sinks=sinks,
        aggregations={},
        gates=[],
        default_sink=sink_name,
    )
    return source, transforms, sinks, graph


def build_fork_pipeline(
    source_data: list[dict[str, Any]],
    gate: Any,
    branch_transforms: dict[str, list[Any]],
    sinks: dict[str, CollectSink] | None = None,
    *,
    source_name: str = "list_source",
    default_sink: str = "default",
    coalesce_settings: list[Any] | None = None,
) -> tuple[ListSource, list[Any], dict[str, CollectSink], ExecutionGraph]:
    """Build a fork/join pipeline with gate routing.

    Uses ExecutionGraph.from_plugin_instances() for production-path fidelity.
    """
    source = ListSource(source_data, name=source_name)

    all_transforms: list[Any] = []
    for branch_list in branch_transforms.values():
        all_transforms.extend(branch_list)

    if sinks is None:
        sinks = {default_sink: CollectSink(default_sink)}

    graph = ExecutionGraph.from_plugin_instances(
        source=source,
        transforms=all_transforms,
        sinks=sinks,
        aggregations={},
        gates=[gate],
        default_sink=default_sink,
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
    source = ListSource(source_data, name=source_name)
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
        default_sink=sink_name,
    )
    return source, aggregations, sinks, graph
