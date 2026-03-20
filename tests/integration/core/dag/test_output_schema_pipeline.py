"""Integration test for output schema contract enforcement through from_plugin_instances().

Tests the full production path:
  real/mock transform constructor → _output_schema_config populated →
  from_plugin_instances() → DAG builder → NodeInfo propagation →
  validate_edge_compatibility() field resolution.

Group 1: Real RAGRetrievalTransform proves end-to-end contract propagation.
Group 2: Mock transforms exercise edge validation scenarios.

Prerequisite: Output schema contract enforcement (Tasks 1-3 from the
enforcement plan) must be implemented — _validate_output_schema_contract
must exist in the DAG builder.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from elspeth.contracts.schema import SchemaConfig
from elspeth.core.config import SourceSettings
from elspeth.core.dag import ExecutionGraph
from elspeth.plugins.transforms.rag.transform import RAGRetrievalTransform


class MockSource:
    """Minimal source implementing enough of SourceProtocol for the builder."""

    name = "mock_source"
    output_schema = None
    config: ClassVar[dict[str, Any]] = {"schema": {"mode": "observed"}}
    _on_validation_failure = "discard"
    on_success = "output"


class MockSink:
    """Minimal sink implementing enough of SinkProtocol for the builder."""

    name = "mock_sink"
    input_schema = None
    config: ClassVar[dict[str, Any]] = {}


_SENTINEL = object()


class MockFieldAddingTransform:
    """Mock transform with configurable output fields and required inputs."""

    input_schema = None
    output_schema = None
    on_error: str | None = None
    on_success: str | None = "output"

    def __init__(
        self,
        name: str,
        *,
        guaranteed_fields: tuple[str, ...] = (),
        declared_output_fields: frozenset[str] = frozenset(),
        required_input_fields: list[str] | None = None,
        output_schema_config_override: Any = _SENTINEL,
    ) -> None:
        self.name = name
        self.declared_output_fields = declared_output_fields

        if output_schema_config_override is not _SENTINEL:
            self._output_schema_config = output_schema_config_override
        elif guaranteed_fields:
            self._output_schema_config = SchemaConfig(
                mode="observed",
                fields=None,
                guaranteed_fields=guaranteed_fields,
            )
        else:
            self._output_schema_config = None

        # config must have required_input_fields as a TOP-LEVEL key
        self.config: dict[str, Any] = {"schema": {"mode": "observed"}}
        if required_input_fields is not None:
            self.config["required_input_fields"] = required_input_fields


@pytest.fixture(autouse=True)
def _set_fingerprint_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure ELSPETH_FINGERPRINT_KEY is set for transforms that may need it."""
    monkeypatch.setenv("ELSPETH_FINGERPRINT_KEY", "test-key-for-pipeline-integration")


class TestRealTransformPropagation:
    """Prove the full chain with a real transform through from_plugin_instances()."""

    def test_rag_output_schema_propagates_through_pipeline(self) -> None:
        """RAG _output_schema_config flows through builder into NodeInfo."""
        from tests.fixtures.factories import wire_transforms
        from tests.fixtures.plugins import CollectSink, ListSource

        rag = RAGRetrievalTransform(
            {
                "output_prefix": "sci",
                "query_field": "question",
                "provider": "chroma",
                "provider_config": {"collection": "test-col", "mode": "ephemeral"},
                "schema_config": {"mode": "observed"},
            }
        )

        source_connection = "list_source_out"
        sink_name = "output"
        source = ListSource([], name="list_source", on_success=source_connection)
        source_settings = SourceSettings(
            plugin=source.name,
            on_success=source_connection,
            options={},
        )
        sink = CollectSink(sink_name)
        wired_transforms = wire_transforms(
            [rag],
            source_connection=source_connection,
            final_sink=sink_name,
        )

        graph = ExecutionGraph.from_plugin_instances(
            source=source,
            source_settings=source_settings,
            transforms=wired_transforms,
            sinks={sink_name: sink},
            aggregations={},
            gates=[],
        )

        # Find the RAG transform node
        rag_nodes = [n for n in graph.get_nodes() if n.plugin_name == "rag_retrieval"]
        assert len(rag_nodes) == 1
        node_info = rag_nodes[0]

        # Verify _output_schema_config was propagated to NodeInfo
        assert node_info.output_schema_config is not None

        # Verify graph methods resolve the guaranteed fields
        guaranteed = graph.get_effective_guaranteed_fields(node_info.node_id)
        expected = frozenset({"sci__rag_context", "sci__rag_score", "sci__rag_count", "sci__rag_sources"})
        assert expected.issubset(guaranteed), f"Expected {expected} to be a subset of {guaranteed}"
