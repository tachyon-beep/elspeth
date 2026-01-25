# tests/conftest.py
"""Shared test fixtures and helpers.

This module provides reusable test utilities for creating test plugins that
properly implement the Protocol interfaces required by ELSPETH.

Test Base Classes:
- _TestSchema: Minimal PluginSchema for test fixtures
- _TestSourceBase: Base class for SourceProtocol test implementations
- _TestSinkBase: Base class for SinkProtocol test implementations
- _TestTransformBase: Base class for TransformProtocol test implementations

Hypothesis Configuration:
- "ci" profile: Fast tests for CI (100 examples) - default
- "nightly" profile: Thorough tests (1000 examples)
- "debug" profile: Minimal tests with verbose output (10 examples)

Set profile via environment variable:
    HYPOTHESIS_PROFILE=nightly pytest tests/property/

Test Fixture Philosophy: Validation Bypass Pattern
===================================================

ELSPETH has two distinct plugin instantiation paths:

1. PRODUCTION PATH (PluginManager):
   - Configuration loaded from YAML
   - PluginManager validates config against plugin's validation_schema()
   - ONLY THEN does PluginManager call plugin.__init__() with validated config
   - Plugins can assume __init__ receives valid data

2. TEST PATH (Direct Instantiation):
   - Tests call MyPlugin.__init__() directly
   - NO validation occurs - bypasses PluginManager entirely
   - Tests pass whatever arguments they need for the test scenario

Why Tests Bypass Validation (This is CORRECT):
-----------------------------------------------

Interface tests verify that plugins implement their Protocols correctly:
- Do they have all required attributes? (name, schema, version)
- Do their methods return the right types? (TransformResult, ArtifactDescriptor)
- Do lifecycle hooks work? (on_start, on_complete, close)

Interface tests do NOT verify:
- Configuration validation logic (that's tested separately in config tests)
- Production instantiation flow (that's tested in integration tests)

Benefits of Direct Instantiation in Tests:
-------------------------------------------
1. FASTER: No config parsing, no validation overhead
2. SIMPLER: Test code is just `MySource(data=[...])`, not YAML + manager
3. FOCUSED: Each test controls exact plugin state without config indirection

Example Comparison:
-------------------

# Production path (used by elspeth CLI):
config = ElspethSettings.from_yaml("pipeline.yaml")
manager = PluginManager()
source = manager.instantiate_source(config.source)  # Validates FIRST
# source.__init__ called ONLY if config is valid

# Test path (used by interface tests):
source = ListSource(data=[{"x": 1}])  # Direct instantiation, no validation
# Useful for testing that ListSource.load() works correctly

Both paths are correct for their context. The test base classes in this module
support the direct instantiation pattern by providing Protocol-compliant defaults.
"""

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import pytest
from hypothesis import Phase, Verbosity, settings

from elspeth.contracts import Determinism, PluginSchema, SourceRow
from elspeth.plugins.manager import PluginManager

if TYPE_CHECKING:
    from elspeth.plugins.protocols import (
        GateProtocol,
        SinkProtocol,
        SourceProtocol,
        TransformProtocol,
    )


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def plugin_manager() -> PluginManager:
    """Standard plugin manager with builtin plugins registered.

    Use this fixture in tests that need to build ExecutionGraph from config.
    Ensures all tests use consistent plugin registration.

    Example:
        def test_graph_building(plugin_manager):
            config = ElspethSettings(...)
            plugins = instantiate_plugins_from_config(config)

            graph = ExecutionGraph.from_plugin_instances(

                source=plugins["source"],

                transforms=plugins["transforms"],

                sinks=plugins["sinks"],

                aggregations=plugins["aggregations"],

                gates=list(config.gates),

                output_sink=config.output_sink,

            )
    """
    manager = PluginManager()
    manager.register_builtin_plugins()
    return manager


# =============================================================================
# Hypothesis Configuration
# =============================================================================

# CI profile: Fast tests for continuous integration
settings.register_profile(
    "ci",
    max_examples=100,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    deadline=None,  # Disable deadline for CI (timing varies)
)

# Nightly profile: Thorough testing for scheduled runs
settings.register_profile(
    "nightly",
    max_examples=1000,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    deadline=None,
)

# Debug profile: Minimal examples with verbose output for debugging
settings.register_profile(
    "debug",
    max_examples=10,
    verbosity=Verbosity.verbose,
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    deadline=None,
)

# Load profile from environment, default to "ci"
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "ci"))


# =============================================================================
# Shared Test Base Classes
# =============================================================================
# These provide all required Protocol attributes and methods so test classes
# only need to override what's specific to the test.


class _TestSchema(PluginSchema):
    """Minimal schema for test fixtures.

    Use this when tests don't need specific fields - just pass it as
    input_schema or output_schema to satisfy Protocol requirements.
    """

    pass


class _TestSourceBase:
    """Base class for test sources that implements SourceProtocol.

    Provides all required Protocol attributes and lifecycle methods.
    Child classes must provide:
    - name: str
    - output_schema: type[PluginSchema]
    - load(ctx) -> Iterator[SourceRow]

    NOTE: Validation Bypass Pattern
    --------------------------------
    Test sources instantiated from this base class bypass PluginManager validation.
    This is CORRECT for interface tests:

    - Interface tests verify Protocol compliance (attributes, method signatures)
    - Config validation is tested separately in config-specific tests
    - Direct instantiation is faster and simpler than YAML + PluginManager

    Production path: PluginManager validates config BEFORE calling __init__
    Test path: Tests call __init__ directly with whatever data they need

    Usage:
        class MyTestSource(_TestSourceBase):
            name = "my_source"
            output_schema = MySchema

            def __init__(self, data: list[dict[str, Any]]) -> None:
                self._data = data

            def load(self, ctx: Any) -> Iterator[SourceRow]:
                yield from self.wrap_rows(self._data)
    """

    # Required by SourceProtocol - child classes must override
    name: str
    output_schema: type[PluginSchema]

    # Protocol-required attributes with defaults
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"

    def wrap_rows(self, rows: list[dict[str, Any]]) -> Iterator[SourceRow]:
        """Wrap plain dicts in SourceRow.valid() as required by source protocol."""
        for row in rows:
            yield SourceRow.valid(row)

    def on_start(self, ctx: Any) -> None:
        """Lifecycle hook - no-op for tests."""
        pass

    def on_complete(self, ctx: Any) -> None:
        """Lifecycle hook - no-op for tests."""
        pass

    def close(self) -> None:
        """Cleanup - no-op for tests."""
        pass


class _TestSinkBase:
    """Base class for test sinks that implements SinkProtocol.

    Provides all required Protocol attributes and lifecycle methods.
    Child classes must provide:
    - name: str
    - write(rows, ctx) -> ArtifactDescriptor

    NOTE: Validation Bypass Pattern
    --------------------------------
    Test sinks instantiated from this base class bypass PluginManager validation.
    This is CORRECT for interface tests:

    - Interface tests verify Protocol compliance (attributes, method signatures)
    - Config validation is tested separately in config-specific tests
    - Direct instantiation is faster and simpler than YAML + PluginManager

    Production path: PluginManager validates config BEFORE calling __init__
    Test path: Tests call __init__ directly with whatever data they need

    Usage:
        class MyTestSink(_TestSinkBase):
            name = "my_sink"

            def __init__(self) -> None:
                self.results: list[dict[str, Any]] = []

            def write(self, rows: Any, ctx: Any) -> ArtifactDescriptor:
                self.results.extend(rows)
                return ArtifactDescriptor.for_file(
                    path="memory", size_bytes=0, content_hash=""
                )
    """

    # Required by SinkProtocol - child classes must override
    name: str

    # Protocol-required attributes with defaults
    input_schema: type[PluginSchema] = _TestSchema
    idempotent: bool = True
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"

    def on_start(self, ctx: Any) -> None:
        """Lifecycle hook - no-op for tests."""
        pass

    def on_complete(self, ctx: Any) -> None:
        """Lifecycle hook - no-op for tests."""
        pass

    def flush(self) -> None:
        """Flush buffered data - no-op for tests."""
        pass

    def close(self) -> None:
        """Cleanup - no-op for tests."""
        pass


class _TestTransformBase:
    """Base class for test transforms that implements TransformProtocol.

    Provides all required Protocol attributes and lifecycle methods.
    Child classes must provide:
    - name: str
    - process(row, ctx) -> TransformResult

    NOTE: Validation Bypass Pattern
    --------------------------------
    Test transforms instantiated from this base class bypass PluginManager validation.
    This is CORRECT for interface tests:

    - Interface tests verify Protocol compliance (attributes, method signatures)
    - Config validation is tested separately in config-specific tests
    - Direct instantiation is faster and simpler than YAML + PluginManager

    Production path: PluginManager validates config BEFORE calling __init__
    Test path: Tests call __init__ directly with whatever data they need

    Usage:
        class MyTestTransform(_TestTransformBase):
            name = "my_transform"

            def process(self, row: dict[str, Any], ctx: Any) -> TransformResult:
                return TransformResult.success(row)
    """

    # Required by TransformProtocol - child classes must override
    name: str

    # Protocol-required attributes with defaults
    input_schema: type[PluginSchema] = _TestSchema
    output_schema: type[PluginSchema] = _TestSchema
    node_id: str | None = None
    determinism = Determinism.DETERMINISTIC
    plugin_version = "1.0.0"
    is_batch_aware: bool = False
    creates_tokens: bool = False
    _on_error: str | None = None

    def on_start(self, ctx: Any) -> None:
        """Lifecycle hook - no-op for tests."""
        pass

    def on_complete(self, ctx: Any) -> None:
        """Lifecycle hook - no-op for tests."""
        pass

    def close(self) -> None:
        """Cleanup - no-op for tests."""
        pass


# =============================================================================
# Type Cast Helpers for Tests
# =============================================================================
# These helpers provide type-safe ways to create test fixtures that satisfy
# the strict Protocol requirements. They use cast() internally to tell mypy
# that our test classes satisfy the protocols, even though they have minor
# differences (like more specific output_schema types).


def as_source(source: Any) -> "SourceProtocol":
    """Cast a test source to SourceProtocol.

    Use this when passing test source instances to functions expecting
    SourceProtocol. The cast tells mypy to trust that the test source
    satisfies the protocol.
    """
    return cast("SourceProtocol", source)


def as_transform(transform: Any) -> "TransformProtocol":
    """Cast a test transform to TransformProtocol."""
    return cast("TransformProtocol", transform)


def as_sink(sink: Any) -> "SinkProtocol":
    """Cast a test sink to SinkProtocol."""
    return cast("SinkProtocol", sink)


def as_gate(gate: Any) -> "GateProtocol":
    """Cast a test gate to GateProtocol."""
    return cast("GateProtocol", gate)


# =============================================================================
# Integration Test Fixtures (INFRA-02)
# =============================================================================
# These provide REAL database and recorder instances with FK constraints enabled.
# Use these for integration tests that validate audit trail integrity.


@pytest.fixture
def real_landscape_db(tmp_path):
    """Real LandscapeDB with FK constraints enabled.

    Use this for integration tests that validate:
    - FK constraints are satisfied
    - Unique constraints work correctly
    - Audit trail completeness

    Returns an in-memory SQLite database with all tables created
    and FK constraints ENABLED (enforced).

    Example:
        def test_batch_fk_constraints(real_landscape_db):
            recorder = LandscapeRecorder(real_landscape_db)
            # ... test validates no FK violations ...
    """
    from elspeth.core.landscape.database import LandscapeDB

    # Use in-memory database for fast tests
    # Tables are created automatically during initialization
    db = LandscapeDB.in_memory()
    return db


@pytest.fixture
def real_landscape_recorder(real_landscape_db):
    """Real LandscapeRecorder with FK constraint enforcement.

    Combines real_landscape_db with a recorder instance.
    Use for integration tests that record audit trail data.

    Example:
        def test_call_recording(real_landscape_recorder):
            run = real_landscape_recorder.begin_run(...)
            # ... test validates calls are recorded correctly ...
    """
    from elspeth.core.landscape.recorder import LandscapeRecorder

    return LandscapeRecorder(real_landscape_db)


@pytest.fixture
def real_landscape_recorder_with_payload_store(real_landscape_db, tmp_path):
    """Real LandscapeRecorder with payload store enabled.

    Use for integration tests that validate large payload storage
    (e.g., JSONL batch requests/responses).

    Example:
        def test_batch_payload_recording(real_landscape_recorder_with_payload_store):
            recorder = real_landscape_recorder_with_payload_store
            # ... test validates payloads are stored and retrievable ...
    """
    from elspeth.core.landscape.recorder import LandscapeRecorder
    from elspeth.core.payload_store import FilesystemPayloadStore

    payload_dir = tmp_path / "payloads"
    payload_store = FilesystemPayloadStore(payload_dir)
    return LandscapeRecorder(real_landscape_db, payload_store=payload_store)


# Re-export for convenient import
__all__ = [
    "_TestSchema",
    "_TestSinkBase",
    "_TestSourceBase",
    "_TestTransformBase",
    "as_gate",
    "as_sink",
    "as_source",
    "as_transform",
    "plugin_manager",
    "real_landscape_db",
    "real_landscape_recorder",
    "real_landscape_recorder_with_payload_store",
]
