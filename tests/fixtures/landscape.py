# tests/fixtures/landscape.py
"""Landscape database and recorder fixtures.

All fixtures are function-scoped for full test isolation.
No module-scoped databases — every test gets a fresh database.

Factory hierarchy:
    make_landscape_db()          → bare LandscapeDB
    make_recorder()              → LandscapeDB + LandscapeRecorder
    make_recorder_with_run()     → LandscapeDB + LandscapeRecorder + run + source node
    register_test_node()         → add additional nodes to an existing run
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from elspeth.contracts import NodeType
from elspeth.contracts.schema import SchemaConfig
from elspeth.core.landscape.database import LandscapeDB
from elspeth.core.landscape.recorder import LandscapeRecorder

# Shared default for schema_config across all factory-created nodes
_OBSERVED_SCHEMA = SchemaConfig.from_dict({"mode": "observed"})


def make_landscape_db() -> LandscapeDB:
    """Factory for in-memory LandscapeDB."""
    return LandscapeDB.in_memory()


def make_recorder(db: LandscapeDB | None = None) -> LandscapeRecorder:
    """Factory for LandscapeRecorder."""
    if db is None:
        db = make_landscape_db()
    return LandscapeRecorder(db)


# =============================================================================
# RecorderSetup — The 80% setup pattern as a single factory call
# =============================================================================


@dataclass
class RecorderSetup:
    """Result from make_recorder_with_run().

    Plain @dataclass — test scaffolding, not audit records.
    Note: db and recorder are mutable objects; frozen=True would only prevent
    reference reassignment without providing an immutability guarantee.
    """

    db: LandscapeDB
    recorder: LandscapeRecorder
    run_id: str
    source_node_id: str


def make_recorder_with_run(
    *,
    run_id: str | None = None,
    source_node_id: str | None = None,
    source_plugin_name: str = "source",
    canonical_version: str = "v1",
) -> RecorderSetup:
    """Create LandscapeDB + Recorder + run + source node in one call.

    Covers the 80% setup pattern: db → recorder → begin_run → register_node(SOURCE).
    Tests needing additional nodes (transforms, sinks, aggregations) can call
    recorder.register_node() on the returned recorder, or use register_test_node().

    Always call this inside individual test methods or setup_method(), never
    setup_class(). It creates a fresh in-memory DB per call for test isolation.

    Args:
        run_id: Explicit run ID for deterministic tests. Auto-generated if None.
        source_node_id: Explicit source node ID. Auto-generated if None.
        source_plugin_name: Plugin name for the source node (default "source").
        canonical_version: Version string for begin_run (default "v1").
            Some tests (e.g., test_processor.py) use "sha256-rfc8785-v1".
    """
    db = make_landscape_db()
    recorder = make_recorder(db)

    # Build kwargs, only passing explicit IDs if provided
    begin_kwargs: dict[str, Any] = {
        "config": {},
        "canonical_version": canonical_version,
    }
    if run_id is not None:
        begin_kwargs["run_id"] = run_id

    run = recorder.begin_run(**begin_kwargs)

    register_kwargs: dict[str, Any] = {
        "run_id": run.run_id,
        "plugin_name": source_plugin_name,
        "node_type": NodeType.SOURCE,
        "plugin_version": "1.0",
        "config": {},
        "schema_config": _OBSERVED_SCHEMA,
    }
    if source_node_id is not None:
        register_kwargs["node_id"] = source_node_id

    node = recorder.register_node(**register_kwargs)

    setup = RecorderSetup(
        db=db,
        recorder=recorder,
        run_id=run.run_id,
        source_node_id=node.node_id,
    )

    # Offensive programming: verify round-trip invariant.
    # If this assertion fails, the factory itself is broken.
    assert setup.run_id == run.run_id, f"Factory bug: returned run_id {setup.run_id!r} != begin_run result {run.run_id!r}"
    assert setup.source_node_id == node.node_id, (
        f"Factory bug: returned source_node_id {setup.source_node_id!r} != register_node result {node.node_id!r}"
    )

    return setup


def register_test_node(
    recorder: LandscapeRecorder,
    run_id: str,
    node_id: str,
    *,
    node_type: NodeType = NodeType.TRANSFORM,
    plugin_name: str = "transform",
) -> str:
    """Register an additional test node with sensible defaults.

    For the 20% variant pattern where tests need 2-5 additional nodes
    after make_recorder_with_run() creates the source.

    Defaults plugin_version="1.0", config={}, schema_config=observed.
    Returns the node_id for convenience.
    """
    node = recorder.register_node(
        run_id=run_id,
        plugin_name=plugin_name,
        node_type=node_type,
        plugin_version="1.0",
        config={},
        node_id=node_id,
        schema_config=_OBSERVED_SCHEMA,
    )
    return node.node_id


# =============================================================================
# Pytest fixtures
# =============================================================================


@pytest.fixture
def landscape_db() -> LandscapeDB:
    """Function-scoped in-memory LandscapeDB — fresh per test."""
    return make_landscape_db()


@pytest.fixture
def recorder(landscape_db: LandscapeDB) -> LandscapeRecorder:
    """Function-scoped LandscapeRecorder."""
    return LandscapeRecorder(landscape_db)


@pytest.fixture
def real_landscape_recorder_with_payload_store(landscape_db: LandscapeDB, tmp_path: Any) -> LandscapeRecorder:
    """LandscapeRecorder with real filesystem payload store."""
    from elspeth.core.payload_store import FilesystemPayloadStore

    payload_dir = tmp_path / "payloads"
    payload_store = FilesystemPayloadStore(payload_dir)
    return LandscapeRecorder(landscape_db, payload_store=payload_store)
