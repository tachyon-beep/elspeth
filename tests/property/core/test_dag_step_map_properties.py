"""Property tests for ExecutionGraph step-map numbering.

Step numbering is audit-critical. These tests verify that node-based traversal
preserves the legacy positional numbering contract:
source=0, transforms=1..N, aggregations next, config gates last.
"""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from elspeth.contracts.types import AggregationName, GateName
from elspeth.core.config import AggregationSettings, CoalesceSettings, GateSettings
from elspeth.core.dag import ExecutionGraph
from elspeth.plugins.results import TransformResult
from tests.fixtures.base_classes import _TestTransformBase
from tests.fixtures.plugins import CollectSink, ListSource


class _NoopTransform(_TestTransformBase):
    """Minimal transform used only to construct production-path graphs."""

    def __init__(self, *, name: str, on_success: str | None = None) -> None:
        super().__init__()
        self.name = name
        self._on_success = on_success

    def process(self, row: Any, ctx: Any) -> TransformResult:
        return TransformResult.success(row, success_reason={"action": "noop"})


@st.composite
def _topologies(draw: st.DrawFn) -> tuple[int, int, int, bool]:
    """Generate valid topology parameters for step-map verification."""
    transform_count = draw(st.integers(min_value=1, max_value=10))
    aggregation_count = draw(st.integers(min_value=0, max_value=1))
    gate_count = draw(st.integers(min_value=0, max_value=3))
    with_fork_coalesce = draw(st.booleans())
    if with_fork_coalesce and gate_count == 0:
        gate_count = 1
    return transform_count, aggregation_count, gate_count, with_fork_coalesce


def _build_graph(
    *,
    transform_count: int,
    aggregation_count: int,
    gate_count: int,
    with_fork_coalesce: bool,
) -> tuple[ExecutionGraph, list[str], list[str]]:
    """Build graph through from_plugin_instances() with valid explicit routing."""
    source = ListSource([{"id": 1}], name="source", on_success="results")
    sinks = {"results": CollectSink("results")}

    transforms: list[_NoopTransform] = []
    for i in range(transform_count):
        is_terminal_processing_node = i == transform_count - 1 and aggregation_count == 0 and gate_count == 0
        transforms.append(
            _NoopTransform(
                name=f"t{i}",
                on_success="results" if is_terminal_processing_node else None,
            )
        )

    aggregation_names: list[str] = []
    aggregations: dict[str, tuple[_NoopTransform, AggregationSettings]] = {}
    for i in range(aggregation_count):
        agg_name = f"agg{i}"
        aggregation_names.append(agg_name)
        is_terminal_processing_node = i == aggregation_count - 1 and gate_count == 0
        aggregations[agg_name] = (
            _NoopTransform(
                name=f"{agg_name}_transform",
                on_success="results" if is_terminal_processing_node else None,
            ),
            AggregationSettings(name=agg_name, plugin=f"{agg_name}_plugin", trigger={"count": 1}),
        )

    gate_names: list[str] = []
    gates: list[GateSettings] = []
    for i in range(gate_count):
        gate_name = f"g{i}"
        gate_names.append(gate_name)
        is_terminal = i == gate_count - 1
        is_fork_gate = with_fork_coalesce and i == 0

        if is_fork_gate:
            routes: dict[str, str] = {"split": "fork"}
            if is_terminal:
                routes["done"] = "results"
            else:
                routes["cont"] = "continue"
            gates.append(
                GateSettings(
                    name=gate_name,
                    condition="row['route']",
                    routes=routes,
                    fork_to=["path_a", "path_b"],
                )
            )
        else:
            routes = {"done": "results"} if is_terminal else {"cont": "continue"}
            gates.append(
                GateSettings(
                    name=gate_name,
                    condition="row['route']",
                    routes=routes,
                )
            )

    coalesce_settings: list[CoalesceSettings] | None = None
    if with_fork_coalesce:
        coalesce_settings = [
            CoalesceSettings(
                name="merge_paths",
                branches=["path_a", "path_b"],
                policy="require_all",
                merge="union",
                on_success="results" if gate_count == 1 else None,
            )
        ]

    graph = ExecutionGraph.from_plugin_instances(
        source=source,
        transforms=transforms,
        sinks=sinks,
        aggregations=aggregations,
        gates=gates,
        coalesce_settings=coalesce_settings,
    )

    return graph, aggregation_names, gate_names


class TestStepMapPositionalCompatibility:
    """Property checks that build_step_map preserves legacy numbering."""

    @given(topology=_topologies())
    @settings(max_examples=120, deadline=None)
    def test_build_step_map_matches_legacy_positional_scheme(
        self,
        topology: tuple[int, int, int, bool],
    ) -> None:
        transform_count, aggregation_count, gate_count, with_fork_coalesce = topology
        graph, aggregation_names, gate_names = _build_graph(
            transform_count=transform_count,
            aggregation_count=aggregation_count,
            gate_count=gate_count,
            with_fork_coalesce=with_fork_coalesce,
        )

        actual = graph.build_step_map()

        source_id = graph.get_source()
        assert source_id is not None
        expected = {source_id: 0}

        transform_map = graph.get_transform_id_map()
        for i in range(transform_count):
            expected[transform_map[i]] = i + 1

        aggregation_map = graph.get_aggregation_id_map()
        for i, agg_name in enumerate(aggregation_names):
            expected[aggregation_map[AggregationName(agg_name)]] = transform_count + i + 1

        gate_map = graph.get_config_gate_id_map()
        for i, gate_name in enumerate(gate_names):
            expected[gate_map[GateName(gate_name)]] = transform_count + aggregation_count + i + 1

        assert actual == expected
