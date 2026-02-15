from __future__ import annotations

import json
from typing import Literal

import pytest

from elspeth.contracts import Determinism, NodeType, RoutingMode
from elspeth.contracts.schema import SchemaConfig
from elspeth.contracts.schema_contract import FieldContract, SchemaContract
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder

_DYNAMIC_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def _setup(*, run_id: str = "run-1") -> tuple[LandscapeDB, LandscapeRecorder]:
    db = LandscapeDB.in_memory()
    recorder = LandscapeRecorder(db)
    recorder.begin_run(config={}, canonical_version="v1", run_id=run_id)
    return db, recorder


def _make_contract(
    *,
    mode: Literal["FIXED", "FLEXIBLE", "OBSERVED"] = "OBSERVED",
    fields: tuple[FieldContract, ...] = (),
    locked: bool = False,
) -> SchemaContract:
    return SchemaContract(mode=mode, fields=fields, locked=locked)


def _make_field(
    name: str,
    python_type: type = str,
    *,
    required: bool = True,
    source: Literal["declared", "inferred"] = "inferred",
) -> FieldContract:
    return FieldContract(
        normalized_name=name,
        original_name=name,
        python_type=python_type,
        required=required,
        source=source,
    )


# ---------------------------------------------------------------------------
# register_node
# ---------------------------------------------------------------------------


class TestRegisterNode:
    """Tests for GraphRecordingMixin.register_node."""

    def test_creates_node_with_config_hash_and_json(self) -> None:
        _db, recorder = _setup()
        config = {"key": "value", "nested": {"a": 1}}
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config=config,
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.config_hash is not None
        assert len(node.config_hash) > 0
        stored_config = json.loads(node.config_json)
        assert stored_config == config

    def test_generates_node_id_when_not_provided(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.node_id is not None
        assert len(node.node_id) > 0

    def test_uses_explicit_node_id(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="my-explicit-node",
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.node_id == "my-explicit-node"

    def test_stores_sequence_in_pipeline(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="field_mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            sequence=3,
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.sequence_in_pipeline == 3

    def test_sequence_none_by_default(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.sequence_in_pipeline is None

    def test_stores_determinism(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="llm_classifier",
            node_type=NodeType.TRANSFORM,
            plugin_version="2.0.0",
            config={},
            determinism=Determinism.EXTERNAL_CALL,
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.determinism == Determinism.EXTERNAL_CALL

    def test_determinism_defaults_to_deterministic(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="field_mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.determinism == Determinism.DETERMINISTIC

    @pytest.mark.parametrize(
        "determinism",
        [
            Determinism.DETERMINISTIC,
            Determinism.SEEDED,
            Determinism.NON_DETERMINISTIC,
            Determinism.EXTERNAL_CALL,
            Determinism.IO_READ,
            Determinism.IO_WRITE,
        ],
    )
    def test_all_determinism_variants(self, determinism: Determinism) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="test_plugin",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            determinism=determinism,
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.determinism == determinism

    def test_stores_node_type(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="threshold_gate",
            node_type=NodeType.GATE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.node_type == NodeType.GATE

    @pytest.mark.parametrize(
        "node_type",
        [
            NodeType.SOURCE,
            NodeType.TRANSFORM,
            NodeType.GATE,
            NodeType.AGGREGATION,
            NodeType.COALESCE,
            NodeType.SINK,
        ],
    )
    def test_all_node_type_variants(self, node_type: NodeType) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="test_plugin",
            node_type=node_type,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.node_type == node_type

    def test_stores_plugin_name_and_version(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="3.2.1",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.plugin_name == "csv"
        assert node.plugin_version == "3.2.1"

    def test_stores_run_id(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.run_id == "run-1"

    def test_schema_mode_from_schema_config(self) -> None:
        _db, recorder = _setup()
        schema = SchemaConfig.from_dict({"mode": "observed"})
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=schema,
        )
        assert node.schema_mode == "observed"

    def test_stores_schema_hash_when_provided(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_hash="abc123hash",
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.schema_hash == "abc123hash"

    def test_schema_hash_none_by_default(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.schema_hash is None

    def test_registered_at_is_set(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.registered_at is not None

    def test_two_nodes_get_distinct_ids(self) -> None:
        _db, recorder = _setup()
        node_a = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        node_b = recorder.register_node(
            run_id="run-1",
            plugin_name="field_mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node_a.node_id != node_b.node_id

    def test_config_hash_changes_with_different_config(self) -> None:
        _db, recorder = _setup()
        node_a = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "a.csv"},
            schema_config=_DYNAMIC_SCHEMA,
        )
        node_b = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "b.csv"},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node_a.config_hash != node_b.config_hash

    def test_config_hash_stable_for_same_config(self) -> None:
        _db, recorder = _setup()
        node_a = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "a.csv"},
            node_id="node-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        node_b = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "a.csv"},
            node_id="node-b",
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node_a.config_hash == node_b.config_hash

    def test_empty_config(self) -> None:
        _db, recorder = _setup()
        node = recorder.register_node(
            run_id="run-1",
            plugin_name="null_source",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            schema_config=_DYNAMIC_SCHEMA,
        )
        assert node.config_hash is not None
        stored = json.loads(node.config_json)
        assert stored == {}


# ---------------------------------------------------------------------------
# register_edge
# ---------------------------------------------------------------------------


class TestRegisterEdge:
    """Tests for GraphRecordingMixin.register_edge."""

    def test_creates_edge(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="xfm",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        assert edge.from_node_id == "src"
        assert edge.to_node_id == "xfm"
        assert edge.run_id == "run-1"

    def test_generates_edge_id_when_not_provided(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        assert edge.edge_id is not None
        assert len(edge.edge_id) > 0

    def test_uses_explicit_edge_id(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
            edge_id="my-edge-id",
        )
        assert edge.edge_id == "my-edge-id"

    def test_stores_label(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="1.0.0",
            config={},
            node_id="gate",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="gate",
            to_node_id="sink",
            label="high_risk",
            mode=RoutingMode.MOVE,
        )
        assert edge.label == "high_risk"

    def test_stores_default_mode(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="1.0.0",
            config={},
            node_id="gate",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="gate",
            to_node_id="sink",
            label="route_to_sink",
            mode=RoutingMode.COPY,
        )
        assert edge.default_mode == RoutingMode.COPY

    def test_created_at_is_set(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        assert edge.created_at is not None

    def test_two_edges_get_distinct_ids(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="xfm",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge_a = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="xfm",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_b = recorder.register_edge(
            run_id="run-1",
            from_node_id="xfm",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        assert edge_a.edge_id != edge_b.edge_id

    @pytest.mark.parametrize(
        "mode",
        [RoutingMode.MOVE, RoutingMode.COPY, RoutingMode.DIVERT],
    )
    def test_all_routing_mode_variants(self, mode: RoutingMode) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="sink",
            label="continue",
            mode=mode,
        )
        assert edge.default_mode == mode


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


class TestGetNode:
    """Tests for GraphRecordingMixin.get_node with composite PK."""

    def test_roundtrip(self) -> None:
        _db, recorder = _setup()
        original = recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "data.csv"},
            node_id="src-node",
            sequence=0,
            schema_config=_DYNAMIC_SCHEMA,
        )
        fetched = recorder.get_node("src-node", "run-1")
        assert fetched is not None
        assert fetched.node_id == original.node_id
        assert fetched.run_id == original.run_id
        assert fetched.plugin_name == "csv"
        assert fetched.node_type == NodeType.SOURCE
        assert fetched.plugin_version == "1.0.0"
        assert fetched.sequence_in_pipeline == 0

    def test_returns_none_for_unknown_node(self) -> None:
        _db, recorder = _setup()
        result = recorder.get_node("nonexistent", "run-1")
        assert result is None

    def test_returns_none_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        result = recorder.get_node("src", "run-999")
        assert result is None

    def test_same_node_id_in_different_runs(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-A")
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-B")

        recorder.register_node(
            run_id="run-A",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "a.csv"},
            node_id="shared-id",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-B",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="2.0.0",
            config={"path": "b.csv"},
            node_id="shared-id",
            schema_config=_DYNAMIC_SCHEMA,
        )

        fetched_a = recorder.get_node("shared-id", "run-A")
        fetched_b = recorder.get_node("shared-id", "run-B")

        assert fetched_a is not None
        assert fetched_b is not None
        assert fetched_a.plugin_version == "1.0.0"
        assert fetched_b.plugin_version == "2.0.0"
        assert fetched_a.run_id == "run-A"
        assert fetched_b.run_id == "run-B"

    def test_returns_none_for_both_unknown(self) -> None:
        _db, recorder = _setup()
        result = recorder.get_node("nonexistent", "no-such-run")
        assert result is None


# ---------------------------------------------------------------------------
# get_nodes
# ---------------------------------------------------------------------------


class TestGetNodes:
    """Tests for GraphRecordingMixin.get_nodes ordering and completeness."""

    def test_returns_all_nodes_for_run(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            sequence=0,
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            sequence=1,
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv_sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            sequence=2,
            schema_config=_DYNAMIC_SCHEMA,
        )
        nodes = recorder.get_nodes("run-1")
        assert len(nodes) == 3

    def test_ordered_by_sequence(self) -> None:
        _db, recorder = _setup()
        # Register out of order
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            sequence=5,
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            sequence=0,
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            sequence=2,
            schema_config=_DYNAMIC_SCHEMA,
        )
        nodes = recorder.get_nodes("run-1")
        sequences = [n.sequence_in_pipeline for n in nodes]
        assert sequences == [0, 2, 5]

    def test_null_sequence_sorted_last(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            sequence=0,
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="unsequenced",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="no-seq",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            sequence=1,
            schema_config=_DYNAMIC_SCHEMA,
        )
        nodes = recorder.get_nodes("run-1")
        assert nodes[0].sequence_in_pipeline == 0
        assert nodes[1].sequence_in_pipeline == 1
        assert nodes[2].sequence_in_pipeline is None

    def test_empty_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        nodes = recorder.get_nodes("no-such-run")
        assert nodes == []

    def test_does_not_return_nodes_from_other_runs(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-A")
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-B")

        recorder.register_node(
            run_id="run-A",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-B",
            plugin_name="json",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src-b",
            schema_config=_DYNAMIC_SCHEMA,
        )

        nodes_a = recorder.get_nodes("run-A")
        nodes_b = recorder.get_nodes("run-B")

        assert len(nodes_a) == 1
        assert nodes_a[0].node_id == "src-a"
        assert len(nodes_b) == 1
        assert nodes_b[0].node_id == "src-b"

    def test_multiple_nodes_preserves_attributes(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={"path": "data.csv"},
            node_id="src",
            sequence=0,
            determinism=Determinism.IO_READ,
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="2.0.0",
            config={"threshold": 0.5},
            node_id="gate",
            sequence=1,
            determinism=Determinism.DETERMINISTIC,
            schema_config=_DYNAMIC_SCHEMA,
        )
        nodes = recorder.get_nodes("run-1")
        assert len(nodes) == 2
        src_node = nodes[0]
        gate_node = nodes[1]
        assert src_node.plugin_name == "csv"
        assert src_node.node_type == NodeType.SOURCE
        assert src_node.determinism == Determinism.IO_READ
        assert gate_node.plugin_name == "gate"
        assert gate_node.node_type == NodeType.GATE
        assert gate_node.determinism == Determinism.DETERMINISTIC

    def test_null_sequence_nodes_deterministic_ordering(self) -> None:
        """Bug qfxc: multiple NULL-sequence nodes must have deterministic order."""
        _db, recorder = _setup()
        # Register multiple nodes with NULL sequence — order must be stable
        recorder.register_node(
            run_id="run-1",
            plugin_name="pluginC",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="node-c",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="pluginA",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="node-a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="pluginB",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="node-b",
            schema_config=_DYNAMIC_SCHEMA,
        )

        # Call get_nodes() twice and verify identical ordering
        nodes_first = recorder.get_nodes("run-1")
        nodes_second = recorder.get_nodes("run-1")

        ids_first = [n.node_id for n in nodes_first]
        ids_second = [n.node_id for n in nodes_second]
        assert ids_first == ids_second

        # All nodes have NULL sequence — tiebreaker is (registered_at, node_id)
        for n in nodes_first:
            assert n.sequence_in_pipeline is None


# ---------------------------------------------------------------------------
# get_edges
# ---------------------------------------------------------------------------


class TestGetEdges:
    """Tests for GraphRecordingMixin.get_edges."""

    def test_returns_all_edges_for_run(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="xfm",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="xfm",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        recorder.register_edge(
            run_id="run-1",
            from_node_id="xfm",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edges = recorder.get_edges("run-1")
        assert len(edges) == 2

    def test_empty_list_when_no_edges(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edges = recorder.get_edges("run-1")
        assert edges == []

    def test_empty_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        edges = recorder.get_edges("no-such-run")
        assert edges == []

    def test_does_not_return_edges_from_other_runs(self) -> None:
        db = LandscapeDB.in_memory()
        recorder = LandscapeRecorder(db)
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-A")
        recorder.begin_run(config={}, canonical_version="v1", run_id="run-B")

        recorder.register_node(
            run_id="run-A",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-A",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_edge(
            run_id="run-A",
            from_node_id="src",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
        )

        edges_a = recorder.get_edges("run-A")
        edges_b = recorder.get_edges("run-B")
        assert len(edges_a) == 1
        assert edges_b == []

    def test_edges_ordered_by_creation(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="xfm1",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm1",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="xfm2",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm2",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge_1 = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="xfm1",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_2 = recorder.register_edge(
            run_id="run-1",
            from_node_id="xfm1",
            to_node_id="xfm2",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edge_3 = recorder.register_edge(
            run_id="run-1",
            from_node_id="xfm2",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        edges = recorder.get_edges("run-1")
        edge_ids = [e.edge_id for e in edges]
        assert edge_ids == [edge_1.edge_id, edge_2.edge_id, edge_3.edge_id]


# ---------------------------------------------------------------------------
# get_edge
# ---------------------------------------------------------------------------


class TestGetEdge:
    """Tests for GraphRecordingMixin.get_edge -- Tier 1 audit integrity."""

    def test_roundtrip(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        original = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="sink",
            label="continue",
            mode=RoutingMode.MOVE,
            edge_id="edge-1",
        )
        fetched = recorder.get_edge("edge-1")
        assert fetched.edge_id == original.edge_id
        assert fetched.from_node_id == "src"
        assert fetched.to_node_id == "sink"
        assert fetched.label == "continue"
        assert fetched.default_mode == RoutingMode.MOVE
        assert fetched.run_id == "run-1"

    def test_raises_value_error_for_unknown_edge(self) -> None:
        _db, recorder = _setup()
        with pytest.raises(ValueError, match="Audit integrity violation"):
            recorder.get_edge("nonexistent-edge")

    def test_raises_value_error_message_includes_edge_id(self) -> None:
        _db, recorder = _setup()
        with pytest.raises(ValueError, match="nonexistent-xyz"):
            recorder.get_edge("nonexistent-xyz")


# ---------------------------------------------------------------------------
# get_edge_map
# ---------------------------------------------------------------------------


class TestGetEdgeMap:
    """Tests for GraphRecordingMixin.get_edge_map."""

    def test_returns_correct_mapping(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="1.0.0",
            config={},
            node_id="gate",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink_a",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink_a",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink_b",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink_b",
            schema_config=_DYNAMIC_SCHEMA,
        )
        edge_a = recorder.register_edge(
            run_id="run-1",
            from_node_id="gate",
            to_node_id="sink_a",
            label="high_risk",
            mode=RoutingMode.MOVE,
        )
        edge_b = recorder.register_edge(
            run_id="run-1",
            from_node_id="gate",
            to_node_id="sink_b",
            label="low_risk",
            mode=RoutingMode.MOVE,
        )
        edge_map = recorder.get_edge_map("run-1")
        assert edge_map[("gate", "high_risk")] == edge_a.edge_id
        assert edge_map[("gate", "low_risk")] == edge_b.edge_id

    def test_empty_for_no_edges(self) -> None:
        _db, recorder = _setup()
        edge_map = recorder.get_edge_map("run-1")
        assert edge_map == {}

    def test_empty_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        edge_map = recorder.get_edge_map("no-such-run")
        assert edge_map == {}

    def test_multiple_source_nodes_with_different_labels(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="gate",
            node_type=NodeType.GATE,
            plugin_version="1.0.0",
            config={},
            node_id="gate",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="xfm",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            schema_config=_DYNAMIC_SCHEMA,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="sink",
            node_type=NodeType.SINK,
            plugin_version="1.0.0",
            config={},
            node_id="sink",
            schema_config=_DYNAMIC_SCHEMA,
        )
        e1 = recorder.register_edge(
            run_id="run-1",
            from_node_id="src",
            to_node_id="gate",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        e2 = recorder.register_edge(
            run_id="run-1",
            from_node_id="gate",
            to_node_id="xfm",
            label="continue",
            mode=RoutingMode.MOVE,
        )
        e3 = recorder.register_edge(
            run_id="run-1",
            from_node_id="gate",
            to_node_id="sink",
            label="escalate",
            mode=RoutingMode.MOVE,
        )
        edge_map = recorder.get_edge_map("run-1")
        assert len(edge_map) == 3
        assert edge_map[("src", "continue")] == e1.edge_id
        assert edge_map[("gate", "continue")] == e2.edge_id
        assert edge_map[("gate", "escalate")] == e3.edge_id


# ---------------------------------------------------------------------------
# get_node_contracts
# ---------------------------------------------------------------------------


class TestGetNodeContracts:
    """Tests for GraphRecordingMixin.get_node_contracts."""

    def test_returns_none_none_when_no_contracts_set(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp, out = recorder.get_node_contracts("run-1", "src")
        assert inp is None
        assert out is None

    def test_returns_none_none_for_unknown_node(self) -> None:
        _db, recorder = _setup()
        inp, out = recorder.get_node_contracts("run-1", "nonexistent")
        assert inp is None
        assert out is None

    def test_returns_none_none_for_unknown_run(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp, out = recorder.get_node_contracts("run-999", "src")
        assert inp is None
        assert out is None

    def test_returns_input_contract_when_provided(self) -> None:
        _db, recorder = _setup()
        input_contract = _make_contract(
            mode="FIXED",
            fields=(
                _make_field("customer_id", str, source="declared"),
                _make_field("amount", float, source="declared"),
            ),
            locked=True,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            input_contract=input_contract,
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp, out = recorder.get_node_contracts("run-1", "xfm")
        assert inp is not None
        assert out is None

    def test_returns_output_contract_when_provided(self) -> None:
        _db, recorder = _setup()
        output_contract = _make_contract(
            mode="OBSERVED",
            fields=(_make_field("result", str),),
            locked=True,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            output_contract=output_contract,
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp, out = recorder.get_node_contracts("run-1", "xfm")
        assert inp is None
        assert out is not None

    def test_returns_both_contracts_when_provided(self) -> None:
        _db, recorder = _setup()
        input_contract = _make_contract(
            mode="FIXED",
            fields=(_make_field("customer_id", str, source="declared"),),
            locked=True,
        )
        output_contract = _make_contract(
            mode="OBSERVED",
            fields=(_make_field("result", str),),
            locked=True,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            input_contract=input_contract,
            output_contract=output_contract,
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp, out = recorder.get_node_contracts("run-1", "xfm")
        assert inp is not None
        assert out is not None

    def test_roundtrip_preserves_contract_fields(self) -> None:
        _db, recorder = _setup()
        input_contract = _make_contract(
            mode="FIXED",
            fields=(
                _make_field("id", int, required=True, source="declared"),
                _make_field("name", str, required=False, source="declared"),
            ),
            locked=True,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            input_contract=input_contract,
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp, _ = recorder.get_node_contracts("run-1", "xfm")
        assert inp is not None
        assert inp.mode == "FIXED"
        assert inp.locked is True
        assert len(inp.fields) == 2
        field_names = {fc.normalized_name for fc in inp.fields}
        assert field_names == {"id", "name"}


# ---------------------------------------------------------------------------
# update_node_output_contract
# ---------------------------------------------------------------------------


class TestUpdateNodeOutputContract:
    """Tests for GraphRecordingMixin.update_node_output_contract."""

    def test_sets_output_contract_on_node_without_one(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        _, out = recorder.get_node_contracts("run-1", "src")
        assert out is None

        new_contract = _make_contract(
            mode="OBSERVED",
            fields=(
                _make_field("id", int),
                _make_field("name", str),
            ),
            locked=True,
        )
        recorder.update_node_output_contract("run-1", "src", new_contract)

        _, out = recorder.get_node_contracts("run-1", "src")
        assert out is not None

    def test_overwrites_existing_output_contract(self) -> None:
        _db, recorder = _setup()
        original_contract = _make_contract(
            mode="OBSERVED",
            fields=(_make_field("old_field", str),),
            locked=True,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            output_contract=original_contract,
            schema_config=_DYNAMIC_SCHEMA,
        )
        _, out_before = recorder.get_node_contracts("run-1", "xfm")
        assert out_before is not None
        assert len(out_before.fields) == 1

        updated_contract = _make_contract(
            mode="OBSERVED",
            fields=(
                _make_field("new_field", int),
                _make_field("other", float),
            ),
            locked=True,
        )
        recorder.update_node_output_contract("run-1", "xfm", updated_contract)

        _, out_after = recorder.get_node_contracts("run-1", "xfm")
        assert out_after is not None
        assert len(out_after.fields) == 2

    def test_does_not_affect_input_contract(self) -> None:
        _db, recorder = _setup()
        input_contract = _make_contract(
            mode="FIXED",
            fields=(_make_field("x", int, source="declared"),),
            locked=True,
        )
        recorder.register_node(
            run_id="run-1",
            plugin_name="mapper",
            node_type=NodeType.TRANSFORM,
            plugin_version="1.0.0",
            config={},
            node_id="xfm",
            input_contract=input_contract,
            schema_config=_DYNAMIC_SCHEMA,
        )
        inp_before, _ = recorder.get_node_contracts("run-1", "xfm")
        assert inp_before is not None

        output_contract = _make_contract(
            mode="OBSERVED",
            fields=(_make_field("y", str),),
            locked=True,
        )
        recorder.update_node_output_contract("run-1", "xfm", output_contract)

        inp_after, out_after = recorder.get_node_contracts("run-1", "xfm")
        assert inp_after is not None
        assert out_after is not None
        # Input contract unchanged
        assert len(inp_after.fields) == 1
        assert inp_after.fields[0].normalized_name == "x"

    def test_roundtrip_preserves_updated_fields(self) -> None:
        _db, recorder = _setup()
        recorder.register_node(
            run_id="run-1",
            plugin_name="csv",
            node_type=NodeType.SOURCE,
            plugin_version="1.0.0",
            config={},
            node_id="src",
            schema_config=_DYNAMIC_SCHEMA,
        )
        contract = _make_contract(
            mode="OBSERVED",
            fields=(
                _make_field("alpha", str),
                _make_field("beta", int),
                _make_field("gamma", float),
            ),
            locked=True,
        )
        recorder.update_node_output_contract("run-1", "src", contract)

        _, out = recorder.get_node_contracts("run-1", "src")
        assert out is not None
        assert out.mode == "OBSERVED"
        assert out.locked is True
        assert len(out.fields) == 3
        field_names = [fc.normalized_name for fc in out.fields]
        assert "alpha" in field_names
        assert "beta" in field_names
        assert "gamma" in field_names
