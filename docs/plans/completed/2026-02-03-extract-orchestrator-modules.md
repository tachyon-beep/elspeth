# Extract orchestrator.py into Modules Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract the 3,148-line `orchestrator.py` into a package of focused modules while preserving the public API.

**Architecture:** Convert `engine/orchestrator.py` into `engine/orchestrator/` package with:
- `__init__.py` - Re-exports (preserves public API)
- `types.py` - PipelineConfig, RunResult, RouteValidationError, AggregationFlushResult
- `validation.py` - Route/sink validation functions
- `export.py` - Landscape export functionality
- `aggregation.py` - Aggregation timeout/flush handling
- `core.py` - Orchestrator class, `__init__`, `run()`, `resume()`

**Tech Stack:** Python 3.12+, no new dependencies (pure refactoring)

---

## Pre-Flight Checks

Before starting, verify:
```bash
# All tests pass
.venv/bin/python -m pytest tests/ -x -q

# Type checking passes
.venv/bin/python -m mypy src/elspeth/engine/orchestrator.py

# Note the current line count
wc -l src/elspeth/engine/orchestrator.py  # Should be ~3148

# IMPORTANT: Capture import time baseline for regression detection
# Record this value and compare after Task 5
echo "Import time baseline:"
time python -c "from elspeth.engine.orchestrator import Orchestrator"
```

---

## Task 1: Create Package Structure with Types Module

**Files:**
- Create: `src/elspeth/engine/orchestrator/` directory
- Create: `src/elspeth/engine/orchestrator/types.py`
- Rename: `src/elspeth/engine/orchestrator.py` → `src/elspeth/engine/orchestrator_legacy.py`
- Create: `src/elspeth/engine/orchestrator/__init__.py`

**CRITICAL: Step order matters. Rename BEFORE creating __init__.py that imports from it.**

**Step 1: Create the orchestrator package directory**

```bash
mkdir -p src/elspeth/engine/orchestrator
```

**Step 2: Rename old orchestrator.py to orchestrator_legacy.py**

```bash
mv src/elspeth/engine/orchestrator.py src/elspeth/engine/orchestrator_legacy.py
```

**Step 3: Create types.py with dataclasses, exception, and AggregationFlushResult**

Extract `PipelineConfig`, `RunResult`, `RouteValidationError`, and `RowPlugin` from orchestrator_legacy.py (lines 65-135). Also add `AggregationFlushResult` to replace the 9-element tuple anti-pattern.

```python
# src/elspeth/engine/orchestrator/types.py
"""Pipeline configuration and result types.

These types define the interface for pipeline execution:
- PipelineConfig: Input configuration for a run
- RunResult: Output statistics from a run
- RouteValidationError: Configuration validation failure
- AggregationFlushResult: Result of flushing aggregation buffers

IMPORTANT: Import Cycle Prevention
----------------------------------
This module is a LEAF MODULE - it must NOT import from other orchestrator
submodules (validation.py, export.py, aggregation.py, core.py).

Other modules import FROM here (e.g., validation.py imports RouteValidationError).
If types.py were to import from those modules, a circular import would occur.

Keep types.py as pure data definitions with minimal dependencies.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.config import AggregationSettings, CoalesceSettings, GateSettings
    from elspeth.plugins.protocols import SinkProtocol, SourceProtocol

from elspeth.contracts import RunStatus
# Import protocols at runtime (not TYPE_CHECKING) because RowPlugin type alias
# is used in runtime annotations and isinstance() checks
from elspeth.plugins.protocols import GateProtocol, TransformProtocol

# Type alias for row-processing plugins in the transforms pipeline
# NOTE: BaseAggregation was DELETED - aggregation is now handled by
# batch-aware transforms (is_batch_aware=True on TransformProtocol)
RowPlugin = TransformProtocol | GateProtocol
"""Union of all row-processing plugin types for pipeline transforms list."""


@dataclass
class PipelineConfig:
    """Configuration for a pipeline run.

    All plugin fields are now properly typed for IDE support and
    static type checking.

    Attributes:
        source: Source plugin instance
        transforms: List of transform/gate plugin instances (processed first)
        sinks: Dict of sink_name -> sink plugin instance
        config: Additional run configuration
        gates: Config-driven gates (processed AFTER transforms, BEFORE sinks)
        aggregation_settings: Dict of node_id -> AggregationSettings
        coalesce_settings: List of coalesce configurations for merging fork paths
    """

    source: "SourceProtocol"
    transforms: list[Any]  # list[RowPlugin] - Any to avoid circular import at runtime
    sinks: dict[str, "SinkProtocol"]
    config: dict[str, Any] = field(default_factory=dict)
    gates: list["GateSettings"] = field(default_factory=list)
    aggregation_settings: dict[str, "AggregationSettings"] = field(default_factory=dict)
    coalesce_settings: list["CoalesceSettings"] = field(default_factory=list)


@dataclass
class RunResult:
    """Result of a pipeline run."""

    run_id: str
    status: RunStatus
    rows_processed: int
    rows_succeeded: int
    rows_failed: int
    rows_routed: int
    rows_quarantined: int = 0
    rows_forked: int = 0
    rows_coalesced: int = 0
    rows_coalesce_failed: int = 0  # Coalesce failures (quorum_not_met, incomplete_branches)
    rows_expanded: int = 0  # Deaggregation parent tokens
    rows_buffered: int = 0  # Passthrough mode buffered tokens
    routed_destinations: dict[str, int] = field(default_factory=dict)  # sink_name -> count


@dataclass(frozen=True, slots=True)
class AggregationFlushResult:
    """Result of flushing aggregation buffers.

    Replaces the 9-element tuple return type with named fields for clarity
    and type safety. Using frozen dataclass prevents accidental mutation.
    """

    rows_succeeded: int = 0
    rows_failed: int = 0
    rows_routed: int = 0
    rows_quarantined: int = 0
    rows_coalesced: int = 0
    rows_forked: int = 0
    rows_expanded: int = 0
    rows_buffered: int = 0
    routed_destinations: dict[str, int] = field(default_factory=dict)

    def __add__(self, other: "AggregationFlushResult") -> "AggregationFlushResult":
        """Combine two results by summing all counters."""
        combined_destinations: Counter[str] = Counter(self.routed_destinations)
        combined_destinations.update(other.routed_destinations)
        return AggregationFlushResult(
            rows_succeeded=self.rows_succeeded + other.rows_succeeded,
            rows_failed=self.rows_failed + other.rows_failed,
            rows_routed=self.rows_routed + other.rows_routed,
            rows_quarantined=self.rows_quarantined + other.rows_quarantined,
            rows_coalesced=self.rows_coalesced + other.rows_coalesced,
            rows_forked=self.rows_forked + other.rows_forked,
            rows_expanded=self.rows_expanded + other.rows_expanded,
            rows_buffered=self.rows_buffered + other.rows_buffered,
            routed_destinations=dict(combined_destinations),
        )


class RouteValidationError(Exception):
    """Raised when route configuration is invalid.

    This error is raised at pipeline initialization, before any rows are
    processed. It indicates a configuration problem that would cause
    failures during processing.
    """

    pass
```

**Step 4: Create minimal __init__.py that imports from types and legacy**

```python
# src/elspeth/engine/orchestrator/__init__.py
"""Orchestrator package: Full run lifecycle management.

This package has been refactored from a single 3000+ line module into
focused modules while preserving the public API.

Public API (unchanged):
- Orchestrator: Main class for running pipelines
- PipelineConfig: Configuration dataclass
- RunResult: Result dataclass
- RouteValidationError: Validation exception
"""

from elspeth.engine.orchestrator.types import (
    AggregationFlushResult,
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)

__all__ = [
    "AggregationFlushResult",
    "Orchestrator",
    "PipelineConfig",
    "RouteValidationError",
    "RowPlugin",
    "RunResult",
]

# Orchestrator import deferred - will be added in Task 5
# For now, import from the old location to maintain compatibility
from elspeth.engine.orchestrator_legacy import Orchestrator  # type: ignore[attr-defined]
```

**Step 5: Update orchestrator_legacy.py imports to use new types**

At the top of `orchestrator_legacy.py`, after the existing imports, add:
```python
# Import types from new location (refactoring in progress)
from elspeth.engine.orchestrator.types import (
    AggregationFlushResult,
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)
```

And **remove** the local definitions of these classes (lines 65-135 approximately):
- Remove `RowPlugin = TransformProtocol | GateProtocol` type alias
- Remove `class PipelineConfig` dataclass
- Remove `class RunResult` dataclass
- Remove `class RouteValidationError` exception

**Step 6: Run tests to verify nothing broke**

```bash
.venv/bin/python -m pytest tests/engine/ -x -q
```
Expected: All tests pass (types are still available via the package __init__.py)

**Step 7: Commit**

```bash
git add src/elspeth/engine/orchestrator/
git add src/elspeth/engine/orchestrator_legacy.py
git commit -m "refactor(engine): create orchestrator package with types module

Extract PipelineConfig, RunResult, RouteValidationError to types.py.
Add AggregationFlushResult dataclass to replace 9-element tuple anti-pattern.
Temporary orchestrator_legacy.py maintains compatibility during refactor."
```

---

## Task 1.5: Add AggregationFlushResult Tests

**CRITICAL:** The AggregationFlushResult dataclass replaces a 9-element tuple. Field ordering errors would be **silent** - counts could swap between `rows_succeeded` and `rows_failed` without obvious test failures. This task adds explicit verification before proceeding with further extraction.

**Files:**
- Create: `tests/engine/orchestrator/test_types.py`

**Step 1: Create test file with field mapping and immutability tests**

```python
# tests/engine/orchestrator/test_types.py
"""Tests for orchestrator types module.

These tests verify the AggregationFlushResult dataclass:
1. All fields are accessible by name (prevents field omission)
2. Fields map to correct values (prevents ordering bugs)
3. Frozen dataclass is immutable (prevents mutation bugs)
4. __add__ operator is commutative (prevents ordering-dependent bugs)
"""

import pytest
from dataclasses import FrozenInstanceError

from elspeth.engine.orchestrator.types import AggregationFlushResult


class TestAggregationFlushResult:
    """Test AggregationFlushResult dataclass correctness."""

    def test_all_fields_accessible_by_name(self) -> None:
        """Verify each field is accessible - catches field omission during refactor."""
        result = AggregationFlushResult(
            rows_succeeded=1,
            rows_failed=2,
            rows_routed=3,
            rows_quarantined=4,
            rows_coalesced=5,
            rows_forked=6,
            rows_expanded=7,
            rows_buffered=8,
            routed_destinations={"sink1": 9},
        )
        # All fields must be accessible by name
        assert result.rows_succeeded == 1
        assert result.rows_failed == 2
        assert result.rows_routed == 3
        assert result.rows_quarantined == 4
        assert result.rows_coalesced == 5
        assert result.rows_forked == 6
        assert result.rows_expanded == 7
        assert result.rows_buffered == 8
        assert result.routed_destinations == {"sink1": 9}

    def test_frozen_dataclass_immutability(self) -> None:
        """Verify frozen=True prevents mutation - catches accidental mutability."""
        result = AggregationFlushResult(rows_succeeded=5)

        with pytest.raises(FrozenInstanceError):
            result.rows_succeeded = 10  # type: ignore[misc]

    def test_default_values(self) -> None:
        """Verify default values are 0 for counts and empty dict for destinations."""
        result = AggregationFlushResult()

        assert result.rows_succeeded == 0
        assert result.rows_failed == 0
        assert result.rows_routed == 0
        assert result.rows_quarantined == 0
        assert result.rows_coalesced == 0
        assert result.rows_forked == 0
        assert result.rows_expanded == 0
        assert result.rows_buffered == 0
        assert result.routed_destinations == {}

    def test_addition_operator_sums_all_fields(self) -> None:
        """Verify __add__ correctly sums all fields."""
        result1 = AggregationFlushResult(
            rows_succeeded=1, rows_failed=2, rows_routed=3,
            rows_quarantined=4, rows_coalesced=5, rows_forked=6,
            rows_expanded=7, rows_buffered=8,
            routed_destinations={"sink1": 10},
        )
        result2 = AggregationFlushResult(
            rows_succeeded=10, rows_failed=20, rows_routed=30,
            rows_quarantined=40, rows_coalesced=50, rows_forked=60,
            rows_expanded=70, rows_buffered=80,
            routed_destinations={"sink1": 5, "sink2": 15},
        )

        combined = result1 + result2

        assert combined.rows_succeeded == 11
        assert combined.rows_failed == 22
        assert combined.rows_routed == 33
        assert combined.rows_quarantined == 44
        assert combined.rows_coalesced == 55
        assert combined.rows_forked == 66
        assert combined.rows_expanded == 77
        assert combined.rows_buffered == 88
        assert combined.routed_destinations == {"sink1": 15, "sink2": 15}

    def test_addition_operator_commutative(self) -> None:
        """Verify a + b == b + a (commutativity)."""
        result1 = AggregationFlushResult(
            rows_succeeded=5, rows_failed=3,
            routed_destinations={"sink1": 10},
        )
        result2 = AggregationFlushResult(
            rows_succeeded=7, rows_failed=2,
            routed_destinations={"sink2": 20},
        )

        combined_ab = result1 + result2
        combined_ba = result2 + result1

        # All fields should be equal regardless of order
        assert combined_ab.rows_succeeded == combined_ba.rows_succeeded
        assert combined_ab.rows_failed == combined_ba.rows_failed
        assert combined_ab.routed_destinations == combined_ba.routed_destinations

    def test_addition_with_zero_result(self) -> None:
        """Verify adding zero-result is identity operation."""
        result = AggregationFlushResult(
            rows_succeeded=5, rows_failed=3,
            routed_destinations={"sink1": 10},
        )
        zero = AggregationFlushResult()

        combined = result + zero

        assert combined.rows_succeeded == 5
        assert combined.rows_failed == 3
        assert combined.routed_destinations == {"sink1": 10}
```

**Step 2: Create the test directory if needed**

```bash
mkdir -p tests/engine/orchestrator
touch tests/engine/orchestrator/__init__.py
```

**Step 3: Run the new tests**

```bash
.venv/bin/python -m pytest tests/engine/orchestrator/test_types.py -v
```
Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/engine/orchestrator/
git commit -m "test(engine): add AggregationFlushResult field mapping tests

Verify dataclass fields are correctly named, immutable, and __add__ is commutative.
These tests catch silent field ordering bugs during tuple→dataclass migration."
```

---

## Task 2: Extract Validation Functions

**Files:**
- Create: `src/elspeth/engine/orchestrator/validation.py`
- Modify: `src/elspeth/engine/orchestrator_legacy.py`

**Step 1: Create validation.py with the three validation functions**

Extract `_validate_route_destinations`, `_validate_transform_error_sinks`, `_validate_source_quarantine_destination` (lines 302-443).

```python
# src/elspeth/engine/orchestrator/validation.py
"""Route and sink validation for pipeline configuration.

These functions run at pipeline initialization, BEFORE any rows are processed,
to catch configuration errors early.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.contracts.types import GateName, NodeID
    from elspeth.core.config import GateSettings
    from elspeth.plugins.protocols import SourceProtocol

from elspeth.engine.orchestrator.types import RouteValidationError
from elspeth.plugins.protocols import GateProtocol, TransformProtocol


def validate_route_destinations(
    route_resolution_map: dict[tuple[str, str], str],
    available_sinks: set[str],
    transform_id_map: dict[int, str],
    transforms: list[Any],
    config_gate_id_map: dict[str, str] | None = None,
    config_gates: list[Any] | None = None,
) -> None:
    """Validate all route destinations reference existing sinks.

    Called at pipeline initialization, BEFORE any rows are processed.
    This catches config errors early instead of failing mid-run.

    Args:
        route_resolution_map: Maps (gate_node_id, route_label) -> destination
        available_sinks: Set of sink names from PipelineConfig
        transform_id_map: Maps transform sequence -> node_id
        transforms: List of transform plugins
        config_gate_id_map: Maps config gate name -> node_id
        config_gates: List of config gate settings

    Raises:
        RouteValidationError: If any route references a non-existent sink
    """
    # Build reverse lookup: node_id -> gate name
    # All gates in transforms and config_gates MUST have entries in their ID maps
    # (graph construction bug if missing)
    node_id_to_gate_name: dict[str, str] = {}
    for seq, transform in enumerate(transforms):
        if isinstance(transform, GateProtocol):
            # Graph must have ID for every transform - crash if missing
            node_id = transform_id_map[seq]
            node_id_to_gate_name[node_id] = transform.name

    # Add config gates to the lookup
    if config_gate_id_map and config_gates:
        from elspeth.contracts.types import GateName
        for gate_config in config_gates:
            # Graph must have ID for every config gate - crash if missing
            node_id = config_gate_id_map[GateName(gate_config.name)]
            node_id_to_gate_name[node_id] = gate_config.name

    # Check each route destination
    for (gate_node_id, route_label), destination in route_resolution_map.items():
        # "continue" means proceed to next transform, not a sink
        if destination == "continue":
            continue

        # "fork" means fork to multiple paths, not a sink
        if destination == "fork":
            continue

        # destination should be a sink name
        if destination not in available_sinks:
            # Every gate in route_resolution_map MUST have a name mapping
            gate_name = node_id_to_gate_name[gate_node_id]
            raise RouteValidationError(
                f"Gate '{gate_name}' can route to '{destination}' "
                f"(via route label '{route_label}') but no sink named "
                f"'{destination}' exists. Available sinks: {sorted(available_sinks)}"
            )


def validate_transform_error_sinks(
    transforms: list[Any],
    available_sinks: set[str],
) -> None:
    """Validate all transform on_error destinations reference existing sinks.

    Called at pipeline initialization, BEFORE any rows are processed.
    This catches config errors early instead of failing mid-run with KeyError.

    Args:
        transforms: List of transform plugins
        available_sinks: Set of sink names from PipelineConfig

    Raises:
        RouteValidationError: If any transform on_error references a non-existent sink
    """
    for transform in transforms:
        # Only TransformProtocol has _on_error; GateProtocol uses routing, not error sinks
        if not isinstance(transform, TransformProtocol):
            continue

        # Access _on_error directly - defined in TransformProtocol
        on_error = transform._on_error

        if on_error is None:
            # No error routing configured - that's fine
            continue

        if on_error == "discard":
            # "discard" is a special value, not a sink name
            continue

        # on_error should reference an existing sink
        if on_error not in available_sinks:
            raise RouteValidationError(
                f"Transform '{transform.name}' has on_error='{on_error}' "
                f"but no sink named '{on_error}' exists. "
                f"Available sinks: {sorted(available_sinks)}. "
                f"Use 'discard' to drop error rows without routing."
            )


def validate_source_quarantine_destination(
    source: "SourceProtocol",
    available_sinks: set[str],
) -> None:
    """Validate source quarantine destination references an existing sink.

    Called at pipeline initialization, BEFORE any rows are processed.
    This catches config errors early instead of silently dropping quarantined
    rows at runtime (P2-2026-01-19-source-quarantine-silent-drop).

    Args:
        source: Source plugin instance
        available_sinks: Set of sink names from PipelineConfig

    Raises:
        RouteValidationError: If source on_validation_failure references
            a non-existent sink
    """
    # _on_validation_failure is required by SourceProtocol
    on_validation_failure = source._on_validation_failure

    if on_validation_failure == "discard":
        # "discard" is a special value, not a sink name
        return

    # on_validation_failure should reference an existing sink
    if on_validation_failure not in available_sinks:
        raise RouteValidationError(
            f"Source '{source.name}' has on_validation_failure='{on_validation_failure}' "
            f"but no sink named '{on_validation_failure}' exists. "
            f"Available sinks: {sorted(available_sinks)}. "
            f"Use 'discard' to drop invalid rows without routing."
        )
```

**Step 2: Update orchestrator_legacy.py to use validation module**

Replace the three `_validate_*` methods in the Orchestrator class with delegation:

```python
# In orchestrator_legacy.py, add import at top:
from elspeth.engine.orchestrator.validation import (
    validate_route_destinations,
    validate_source_quarantine_destination,
    validate_transform_error_sinks,
)

# Replace the method bodies (keep methods as thin wrappers for now):
def _validate_route_destinations(
    self,
    route_resolution_map: dict[tuple[NodeID, str], str],
    available_sinks: set[str],
    transform_id_map: dict[int, NodeID],
    transforms: list[RowPlugin],
    config_gate_id_map: dict[GateName, NodeID] | None = None,
    config_gates: list[GateSettings] | None = None,
) -> None:
    """Delegate to validation module."""
    validate_route_destinations(
        route_resolution_map,
        available_sinks,
        transform_id_map,
        transforms,
        config_gate_id_map,
        config_gates,
    )

def _validate_transform_error_sinks(
    self,
    transforms: list[RowPlugin],
    available_sinks: set[str],
    _transform_id_map: dict[int, NodeID],  # Kept for API consistency, not used
) -> None:
    """Delegate to validation module.

    Note: _transform_id_map is kept for API consistency with _validate_route_destinations
    but is intentionally unused - transform error sinks don't need node IDs for validation.
    """
    validate_transform_error_sinks(transforms, available_sinks)

def _validate_source_quarantine_destination(
    self,
    source: SourceProtocol,
    available_sinks: set[str],
) -> None:
    """Delegate to validation module."""
    validate_source_quarantine_destination(source, available_sinks)
```

**Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/engine/ -x -q
```
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/validation.py
git add src/elspeth/engine/orchestrator_legacy.py
git commit -m "refactor(engine): extract validation functions to validation.py

Move route/sink validation logic to dedicated module.
Orchestrator methods now delegate to module functions."
```

---

## Task 3: Extract Export Functions

**Files:**
- Create: `src/elspeth/engine/orchestrator/export.py`
- Modify: `src/elspeth/engine/orchestrator_legacy.py`

**Step 1: Create export.py with export functions**

Extract `_export_landscape`, `_export_csv_multifile`, `_reconstruct_schema_from_json`, `_json_schema_to_python_type` (lines 1808-2080).

```python
# src/elspeth/engine/orchestrator/export.py
"""Landscape export functionality.

Handles post-run export of audit trail to configured sinks in JSON or CSV format.
Also includes schema reconstruction for pipeline resume.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.config import ElspethSettings
    from elspeth.core.landscape import LandscapeDB
    from elspeth.plugins.context import PluginContext


def export_landscape(
    db: "LandscapeDB",
    run_id: str,
    settings: "ElspethSettings",
    sinks: dict[str, Any],
) -> None:
    """Export audit trail to configured sink after run completion.

    For JSON format: writes all records to a single sink (records are
    heterogeneous but JSON handles that naturally).

    For CSV format: writes separate files per record_type to a directory,
    since CSV requires homogeneous schemas per file.

    Args:
        db: Landscape database connection
        run_id: The completed run ID
        settings: Full settings containing export configuration
        sinks: Dict of sink_name -> sink instance from PipelineConfig

    Raises:
        ValueError: If signing requested but ELSPETH_SIGNING_KEY not set,
                   or if configured sink not found
    """
    from elspeth.core.landscape.exporter import LandscapeExporter
    from elspeth.plugins.context import PluginContext

    export_config = settings.landscape.export

    # Get signing key from environment if signing enabled
    signing_key: bytes | None = None
    if export_config.sign:
        try:
            key_str = os.environ["ELSPETH_SIGNING_KEY"]
        except KeyError:
            raise ValueError("ELSPETH_SIGNING_KEY environment variable required for signed export") from None
        signing_key = key_str.encode("utf-8")

    # Create exporter
    exporter = LandscapeExporter(db, signing_key=signing_key)

    # Get target sink config
    sink_name = export_config.sink
    if sink_name not in sinks:
        raise ValueError(f"Export sink '{sink_name}' not found in sinks")
    sink = sinks[sink_name]

    # Create context for sink writes
    # Note: landscape=None is intentional - export doesn't record to landscape
    ctx = PluginContext(run_id=run_id, config={}, landscape=None)

    if export_config.format == "csv":
        # Multi-file CSV export: one file per record type
        # CSV export writes files directly (not via sink.write), so we need
        # the path from sink config. CSV format requires file-based sink.
        if "path" not in sink.config:
            raise ValueError(
                f"CSV export requires file-based sink with 'path' in config, but sink '{sink_name}' has no path configured"
            )
        artifact_path: str = sink.config["path"]
        _export_csv_multifile(
            exporter=exporter,
            run_id=run_id,
            artifact_path=artifact_path,
            sign=export_config.sign,
            ctx=ctx,
        )
    else:
        # JSON export: batch all records for single write
        records = list(exporter.export_run(run_id, sign=export_config.sign))
        if records:
            # Capture ArtifactDescriptor for audit trail (future use)
            _artifact_descriptor = sink.write(records, ctx)
        sink.flush()
        sink.close()


def _export_csv_multifile(
    exporter: Any,  # LandscapeExporter (avoid circular import in type hint)
    run_id: str,
    artifact_path: str,
    sign: bool,
    ctx: "PluginContext",  # Reserved for future use
) -> None:
    """Export audit trail as multiple CSV files (one per record type).

    Creates a directory at the artifact path, then writes
    separate CSV files for each record type (run.csv, nodes.csv, etc.).

    Args:
        exporter: LandscapeExporter instance
        run_id: The completed run ID
        artifact_path: Path from sink config (validated by caller)
        sign: Whether to sign records
        ctx: Plugin context for sink operations (reserved for future use)
    """
    from elspeth.core.landscape.formatters import CSVFormatter

    export_dir = Path(artifact_path)
    if export_dir.suffix:
        # Remove file extension if present, treat as directory
        export_dir = export_dir.with_suffix("")

    export_dir.mkdir(parents=True, exist_ok=True)

    # Get records grouped by type
    grouped = exporter.export_run_grouped(run_id, sign=sign)
    formatter = CSVFormatter()

    # Write each record type to its own CSV file
    for record_type, records in grouped.items():
        if not records:
            continue

        csv_path = export_dir / f"{record_type}.csv"

        # Flatten all records for CSV
        flat_records = [formatter.format(r) for r in records]

        # Get union of all keys (some records may have optional fields)
        all_keys: set[str] = set()
        for rec in flat_records:
            all_keys.update(rec.keys())
        fieldnames = sorted(all_keys)  # Sorted for determinism

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for rec in flat_records:
                writer.writerow(rec)


def reconstruct_schema_from_json(schema_dict: dict[str, Any]) -> type:
    """Reconstruct Pydantic schema class from JSON schema dict.

    Handles complete Pydantic JSON schema including:
    - Primitive types: string, integer, number, boolean
    - datetime: string with format="date-time"
    - Decimal: anyOf with number/string (for precision preservation)
    - Arrays: type="array" with items schema
    - Nested objects: type="object" with properties schema

    Args:
        schema_dict: Pydantic JSON schema dict (from model_json_schema())

    Returns:
        Dynamically created Pydantic model class

    Raises:
        ValueError: If schema is malformed, empty, or contains unsupported types
    """
    from pydantic import create_model

    from elspeth.contracts import PluginSchema

    # Extract field definitions from Pydantic JSON schema
    # This is OUR data (from Landscape DB) - crash if malformed
    if "properties" not in schema_dict:
        raise ValueError(
            "Resume failed: Schema JSON has no 'properties' field. This indicates a malformed schema. Cannot reconstruct types."
        )
    properties = schema_dict["properties"]

    if not properties:
        raise ValueError(
            "Resume failed: Schema has zero fields defined. "
            "Cannot resume with empty schema - this would silently discard all row data. "
            "The original source schema must have at least one field."
        )

    # "required" is optional in JSON Schema spec - empty list is valid default
    if "required" in schema_dict:
        required_fields = set(schema_dict["required"])
    else:
        required_fields = set()

    # Build field definitions for create_model
    field_definitions: dict[str, Any] = {}

    for field_name, field_info in properties.items():
        # Determine Python type from JSON schema
        field_type = _json_schema_to_python_type(field_name, field_info)

        # Handle optional vs required fields
        if field_name in required_fields:
            field_definitions[field_name] = (field_type, ...)  # Required field
        else:
            field_definitions[field_name] = (field_type, None)  # Optional field

    # Recreate the schema class dynamically
    return create_model("RestoredSourceSchema", __base__=PluginSchema, **field_definitions)


def _json_schema_to_python_type(field_name: str, field_info: dict[str, Any]) -> type:
    """Map Pydantic JSON schema field to Python type.

    Handles Pydantic's type mapping including special cases:
    - datetime: {"type": "string", "format": "date-time"}
    - Decimal: {"anyOf": [{"type": "number"}, {"type": "string"}]}
    - list[T]: {"type": "array", "items": {...}}
    - dict: {"type": "object"} without properties

    Args:
        field_name: Field name (for error messages)
        field_info: JSON schema field definition

    Returns:
        Python type for Pydantic field

    Raises:
        ValueError: If field type is not supported (prevents silent degradation)
    """
    # Check for datetime first (string with format annotation)
    # "format" is optional in JSON Schema, so check with "in" first
    if "type" in field_info and field_info["type"] == "string" and "format" in field_info and field_info["format"] == "date-time":
        return datetime

    # Check for Decimal (anyOf pattern)
    if "anyOf" in field_info:
        # Pydantic emits: {"anyOf": [{"type": "number"}, {"type": "string"}]}
        # This indicates Decimal (accepts both for parsing flexibility)
        any_of_types = field_info["anyOf"]
        # Only consider items that have "type" key, then access directly
        type_strs = {item["type"] for item in any_of_types if "type" in item}
        if {"number", "string"}.issubset(type_strs):
            return Decimal

    # Get basic type - required for all non-anyOf fields
    if "type" not in field_info:
        raise ValueError(
            f"Resume failed: Field '{field_name}' has no 'type' in schema. "
            f"Schema definition: {field_info}. "
            f"Cannot determine Python type for field."
        )
    field_type_str = field_info["type"]

    # Handle array types
    if field_type_str == "array":
        # "items" is optional in JSON Schema arrays
        if "items" not in field_info:
            # Generic list without item type constraint
            return list
        # For typed arrays, we'd need recursive handling
        # For now, return list (Pydantic will validate items at parse time)
        return list

    # Handle nested object types
    if field_type_str == "object":
        # Generic dict (no specific structure)
        return dict

    # Handle primitive types
    primitive_type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }

    if field_type_str in primitive_type_map:
        return primitive_type_map[field_type_str]

    # Unknown type - CRASH instead of silent degradation
    raise ValueError(
        f"Resume failed: Field '{field_name}' has unsupported type '{field_type_str}'. "
        f"Supported types: string, integer, number, boolean, date-time, Decimal, array, object. "
        f"Schema definition: {field_info}. "
        f"This is a bug in schema reconstruction - please report this."
    )
```

**Step 2: Update orchestrator_legacy.py to use export module**

Add import and delegate:

```python
# Add import at top:
from elspeth.engine.orchestrator.export import (
    export_landscape,
    reconstruct_schema_from_json,
)

# Replace method bodies:
def _export_landscape(
    self,
    run_id: str,
    settings: ElspethSettings,
    sinks: dict[str, Any],
) -> None:
    """Delegate to export module."""
    export_landscape(self._db, run_id, settings, sinks)

def _reconstruct_schema_from_json(self, schema_dict: dict[str, Any]) -> type:
    """Delegate to export module."""
    return reconstruct_schema_from_json(schema_dict)

# Remove _json_schema_to_python_type and _export_csv_multifile (now private in export.py)
```

**Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/engine/ tests/integration/ -x -q
```
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/export.py
git add src/elspeth/engine/orchestrator_legacy.py
git commit -m "refactor(engine): extract export functions to export.py

Move landscape export and schema reconstruction to dedicated module."
```

---

## Task 4: Extract Aggregation Handling Functions

**Files:**
- Create: `src/elspeth/engine/orchestrator/aggregation.py`
- Modify: `src/elspeth/engine/orchestrator_legacy.py`

**Step 1: Create aggregation.py with all aggregation functions**

Extract `_check_aggregation_timeouts`, `_flush_remaining_aggregation_buffers`, `_find_aggregation_transform`, `_handle_incomplete_batches` (lines 2720-3148).

```python
# src/elspeth/engine/orchestrator/aggregation.py
"""Aggregation timeout and flush handling.

These functions manage the lifecycle of aggregation buffers:
- Checking and triggering timeouts during processing
- Flushing remaining buffers at end of source
- Handling incomplete batches during resume
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.contracts import PendingOutcome, TokenInfo
    from elspeth.contracts.types import NodeID
    from elspeth.core.landscape import LandscapeRecorder
    from elspeth.engine.processor import RowProcessor
    from elspeth.plugins.context import PluginContext
    from elspeth.plugins.protocols import TransformProtocol

from elspeth.contracts import PendingOutcome, RowOutcome
from elspeth.contracts.enums import TriggerType
from elspeth.contracts.types import NodeID
from elspeth.engine.orchestrator.types import AggregationFlushResult, PipelineConfig


def find_aggregation_transform(
    config: PipelineConfig,
    agg_node_id_str: str,
    agg_name: str,
) -> tuple["TransformProtocol", int]:
    """Find the batch-aware transform for an aggregation node.

    Args:
        config: Pipeline configuration with transforms
        agg_node_id_str: The aggregation node ID as string
        agg_name: Human-readable aggregation name (for error messages)

    Returns:
        Tuple of (transform, step_index) where step_index is the 0-indexed
        position in the pipeline

    Raises:
        RuntimeError: If no batch-aware transform found for the aggregation
    """
    from elspeth.plugins.protocols import TransformProtocol

    agg_transform: TransformProtocol | None = None
    agg_step = len(config.transforms)

    for i, t in enumerate(config.transforms):
        if isinstance(t, TransformProtocol) and t.node_id == agg_node_id_str and t.is_batch_aware:
            agg_transform = t
            agg_step = i
            break

    if agg_transform is None:
        raise RuntimeError(
            f"No batch-aware transform found for aggregation '{agg_name}' "
            f"(node_id={agg_node_id_str}). This indicates a bug in graph construction "
            f"or pipeline configuration. "
            f"Available transforms: {[t.node_id for t in config.transforms]}"
        )

    return agg_transform, agg_step


def handle_incomplete_batches(
    recorder: "LandscapeRecorder",
    run_id: str,
) -> None:
    """Find and handle incomplete batches for recovery.

    - EXECUTING batches: Mark as failed (crash interrupted), then retry
    - FAILED batches: Retry with incremented attempt
    - DRAFT batches: Leave as-is (collection continues)

    Args:
        recorder: LandscapeRecorder for database operations
        run_id: Run being recovered
    """
    from elspeth.contracts.enums import BatchStatus

    incomplete = recorder.get_incomplete_batches(run_id)

    for batch in incomplete:
        if batch.status == BatchStatus.EXECUTING:
            # Crash interrupted mid-execution, mark failed then retry
            recorder.update_batch_status(batch.batch_id, BatchStatus.FAILED)
            recorder.retry_batch(batch.batch_id)
        elif batch.status == BatchStatus.FAILED:
            # Previous failure, retry
            recorder.retry_batch(batch.batch_id)
        # DRAFT batches continue normally (collection resumes)


def check_aggregation_timeouts(
    config: PipelineConfig,
    processor: "RowProcessor",
    ctx: "PluginContext",
    pending_tokens: dict[str, list[tuple["TokenInfo", "PendingOutcome | None"]]],
    default_sink_name: str,
    agg_transform_lookup: dict[str, tuple["TransformProtocol", int]] | None = None,
) -> AggregationFlushResult:
    """Check and flush any aggregations whose timeout has expired.

    Called BEFORE processing each row to ensure timeouts fire during active
    processing, not just at end-of-source. Checking BEFORE buffering ensures
    timed-out batches don't include the newly arriving row.

    Bug fix: P1-2026-01-22-aggregation-timeout-idle-never-fires
    Before this fix, should_flush() was only called from buffer_row(),
    meaning timeouts never fired during idle periods between rows.

    KNOWN LIMITATION (True Idle):
    Timeouts fire when the next row arrives, not during "true idle" periods.
    If no rows arrive, buffered data will not flush until either:
    1. A new row arrives (triggering this timeout check), or
    2. The source completes (triggering flush_remaining_aggregation_buffers)

    Args:
        config: Pipeline configuration with aggregation_settings
        processor: RowProcessor with public aggregation timeout API
        ctx: Plugin context for transform execution
        pending_tokens: Dict of sink_name -> tokens to append results to
        default_sink_name: Default sink for aggregation output
        agg_transform_lookup: Pre-computed dict mapping node_id_str -> (transform, step).
            If None, lookup is computed on each call (less efficient).

    Returns:
        AggregationFlushResult with counts of processed rows by outcome
    """
    rows_succeeded = 0
    rows_failed = 0
    rows_routed = 0
    rows_quarantined = 0
    rows_coalesced = 0
    rows_forked = 0
    rows_expanded = 0
    rows_buffered = 0
    routed_destinations: Counter[str] = Counter()

    for agg_node_id_str, agg_settings in config.aggregation_settings.items():
        agg_node_id = NodeID(agg_node_id_str)

        # Use public facade method to check timeout (no private member access)
        should_flush, trigger_type = processor.check_aggregation_timeout(agg_node_id)

        if not should_flush:
            continue

        # Skip if not a timeout trigger - count triggers are handled in buffer_row
        if trigger_type != TriggerType.TIMEOUT:
            continue

        # Check if there are buffered rows
        buffered_count = processor.get_aggregation_buffer_count(agg_node_id)
        if buffered_count == 0:
            continue

        # Get transform and step from pre-computed lookup (O(1)) or compute (O(n))
        if agg_transform_lookup and agg_node_id_str in agg_transform_lookup:
            agg_transform, agg_step = agg_transform_lookup[agg_node_id_str]
        else:
            # Fallback: use helper method if lookup not provided
            agg_transform, agg_step = find_aggregation_transform(config, agg_node_id_str, agg_settings.name)

        # Use handle_timeout_flush for proper output_mode handling
        # This correctly routes through remaining transforms and gates
        total_steps = len(config.transforms)
        completed_results, work_items = processor.handle_timeout_flush(
            node_id=agg_node_id,
            transform=agg_transform,
            ctx=ctx,
            step=agg_step,
            total_steps=total_steps,
            trigger_type=TriggerType.TIMEOUT,
        )

        # Handle completed results (no more transforms - go to sink)
        for result in completed_results:
            if result.outcome == RowOutcome.FAILED:
                rows_failed += 1
            else:
                # Route to appropriate sink based on branch_name if set
                sink_name = result.token.branch_name or default_sink_name
                if sink_name not in pending_tokens:
                    sink_name = default_sink_name
                pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
                rows_succeeded += 1

        # Process work items through remaining transforms
        # These tokens need to continue through the pipeline
        for work_item in work_items:
            # Determine start_step: if coalesce is set, use it directly
            # Otherwise, add 1 to current position to get next transform
            if work_item.coalesce_at_step is not None:
                continuation_start = work_item.coalesce_at_step
            else:
                continuation_start = work_item.start_step + 1
            downstream_results = processor.process_token(
                token=work_item.token,
                transforms=config.transforms,
                ctx=ctx,
                start_step=continuation_start,
                coalesce_at_step=work_item.coalesce_at_step,
                coalesce_name=work_item.coalesce_name,
            )

            for result in downstream_results:
                if result.outcome == RowOutcome.FAILED:
                    rows_failed += 1
                elif result.outcome == RowOutcome.COMPLETED:
                    # Route to appropriate sink
                    sink_name = result.token.branch_name or default_sink_name
                    if sink_name not in pending_tokens:
                        sink_name = default_sink_name
                    pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
                    rows_succeeded += 1
                elif result.outcome == RowOutcome.ROUTED:
                    # Gate routed to named sink - MUST enqueue or row is lost
                    # GateExecutor contract: ROUTED outcome always has sink_name set
                    rows_routed += 1
                    routed_sink = result.sink_name or default_sink_name
                    routed_destinations[routed_sink] += 1
                    pending_tokens[routed_sink].append((result.token, PendingOutcome(RowOutcome.ROUTED)))
                elif result.outcome == RowOutcome.QUARANTINED:
                    # Row quarantined by downstream transform - already recorded
                    rows_quarantined += 1
                elif result.outcome == RowOutcome.COALESCED:
                    # Merged token from terminal coalesce - route to output sink
                    # This handles the case where coalesce is the last step
                    rows_coalesced += 1
                    rows_succeeded += 1
                    pending_tokens[default_sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))
                elif result.outcome == RowOutcome.FORKED:
                    # Parent token split into multiple paths - children counted separately
                    rows_forked += 1
                elif result.outcome == RowOutcome.EXPANDED:
                    # Deaggregation parent token - children counted separately
                    rows_expanded += 1
                elif result.outcome == RowOutcome.BUFFERED:
                    # Passthrough mode buffered token (into downstream aggregation)
                    rows_buffered += 1
                # CONSUMED_IN_BATCH is handled within process_token

    return AggregationFlushResult(
        rows_succeeded=rows_succeeded,
        rows_failed=rows_failed,
        rows_routed=rows_routed,
        rows_quarantined=rows_quarantined,
        rows_coalesced=rows_coalesced,
        rows_forked=rows_forked,
        rows_expanded=rows_expanded,
        rows_buffered=rows_buffered,
        routed_destinations=dict(routed_destinations),
    )


def flush_remaining_aggregation_buffers(
    config: PipelineConfig,
    processor: "RowProcessor",
    ctx: "PluginContext",
    pending_tokens: dict[str, list[tuple["TokenInfo", "PendingOutcome | None"]]],
    default_sink_name: str,
    run_id: str,
    recorder: "LandscapeRecorder",
    checkpoint_callback: Any | None = None,  # Callable[[str, str, dict], None] | None
) -> AggregationFlushResult:
    """Flush remaining aggregation buffers at end-of-source.

    Without this, rows buffered but not yet flushed (e.g., 50 rows
    when trigger is count=100) would be silently lost.

    Uses handle_timeout_flush with END_OF_SOURCE trigger to properly handle
    all output_mode semantics (single, passthrough, transform) and route
    tokens through remaining transforms if any exist after the aggregation.

    Args:
        config: Pipeline configuration with aggregation_settings
        processor: RowProcessor with public aggregation facades
        ctx: Plugin context for transform execution
        pending_tokens: Dict of sink_name -> tokens to append results to
        default_sink_name: Default sink for aggregation output
        run_id: Current run ID (for checkpointing)
        recorder: LandscapeRecorder for recording outcomes
        checkpoint_callback: Optional callback for checkpointing:
            callback(run_id, token_id, node_id, aggregation_state)

    Returns:
        AggregationFlushResult with counts of processed rows by outcome

    Raises:
        RuntimeError: If no batch-aware transform found for an aggregation
                     (indicates bug in graph construction or pipeline config)
    """
    rows_succeeded = 0
    rows_failed = 0
    rows_routed = 0
    rows_quarantined = 0
    rows_coalesced = 0
    rows_forked = 0
    rows_expanded = 0
    rows_buffered = 0
    routed_destinations: Counter[str] = Counter()
    total_steps = len(config.transforms)

    for agg_node_id_str, agg_settings in config.aggregation_settings.items():
        agg_node_id = NodeID(agg_node_id_str)

        # Use public facade (not private member)
        buffered_count = processor.get_aggregation_buffer_count(agg_node_id)
        if buffered_count == 0:
            continue

        # Use helper method for transform lookup
        agg_transform, agg_step = find_aggregation_transform(config, agg_node_id_str, agg_settings.name)

        # Use handle_timeout_flush with END_OF_SOURCE trigger
        # This properly handles output_mode and routes through remaining transforms
        completed_results, work_items = processor.handle_timeout_flush(
            node_id=agg_node_id,
            transform=agg_transform,
            ctx=ctx,
            step=agg_step,
            total_steps=total_steps,
            trigger_type=TriggerType.END_OF_SOURCE,
        )

        # Handle completed results (terminal tokens - go to sink)
        for result in completed_results:
            if result.outcome == RowOutcome.FAILED:
                rows_failed += 1
            else:
                # Route to appropriate sink based on branch_name if set
                sink_name = result.token.branch_name or default_sink_name
                if sink_name not in pending_tokens:
                    sink_name = default_sink_name
                pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
                rows_succeeded += 1

                # Checkpoint if callback provided
                if checkpoint_callback is not None:
                    agg_state = processor.get_aggregation_checkpoint_state()
                    checkpoint_callback(run_id, result.token.token_id, agg_state)

        # Process work items through remaining transforms
        # These tokens need to continue through the pipeline
        for work_item in work_items:
            # Determine start_step: if coalesce is set, use it directly
            # Otherwise, add 1 to current position to get next transform
            if work_item.coalesce_at_step is not None:
                continuation_start = work_item.coalesce_at_step
            else:
                continuation_start = work_item.start_step + 1
            downstream_results = processor.process_token(
                token=work_item.token,
                transforms=config.transforms,
                ctx=ctx,
                start_step=continuation_start,
                coalesce_at_step=work_item.coalesce_at_step,
                coalesce_name=work_item.coalesce_name,
            )

            for result in downstream_results:
                if result.outcome == RowOutcome.FAILED:
                    rows_failed += 1
                elif result.outcome == RowOutcome.COMPLETED:
                    # Route to appropriate sink
                    sink_name = result.token.branch_name or default_sink_name
                    if sink_name not in pending_tokens:
                        sink_name = default_sink_name
                    pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
                    rows_succeeded += 1

                    # Checkpoint if callback provided
                    if checkpoint_callback is not None:
                        agg_state = processor.get_aggregation_checkpoint_state()
                        checkpoint_callback(run_id, result.token.token_id, agg_state)
                elif result.outcome == RowOutcome.ROUTED:
                    # Gate routed to named sink - MUST enqueue or row is lost
                    rows_routed += 1
                    routed_sink = result.sink_name or default_sink_name
                    routed_destinations[routed_sink] += 1
                    pending_tokens[routed_sink].append((result.token, PendingOutcome(RowOutcome.ROUTED)))

                    # Checkpoint if callback provided
                    if checkpoint_callback is not None:
                        agg_state = processor.get_aggregation_checkpoint_state()
                        checkpoint_callback(run_id, result.token.token_id, agg_state)
                elif result.outcome == RowOutcome.QUARANTINED:
                    # Row quarantined by downstream transform - already recorded
                    rows_quarantined += 1
                elif result.outcome == RowOutcome.COALESCED:
                    # Merged token from terminal coalesce - route to output sink
                    rows_coalesced += 1
                    rows_succeeded += 1
                    pending_tokens[default_sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))

                    # Checkpoint if callback provided
                    if checkpoint_callback is not None:
                        agg_state = processor.get_aggregation_checkpoint_state()
                        checkpoint_callback(run_id, result.token.token_id, agg_state)
                elif result.outcome == RowOutcome.FORKED:
                    # Parent token split into multiple paths - children counted separately
                    rows_forked += 1
                elif result.outcome == RowOutcome.EXPANDED:
                    # Deaggregation parent token - children counted separately
                    rows_expanded += 1
                elif result.outcome == RowOutcome.BUFFERED:
                    # Passthrough mode buffered token (into downstream aggregation)
                    rows_buffered += 1
                # CONSUMED_IN_BATCH is handled within process_token

    return AggregationFlushResult(
        rows_succeeded=rows_succeeded,
        rows_failed=rows_failed,
        rows_routed=rows_routed,
        rows_quarantined=rows_quarantined,
        rows_coalesced=rows_coalesced,
        rows_forked=rows_forked,
        rows_expanded=rows_expanded,
        rows_buffered=rows_buffered,
        routed_destinations=dict(routed_destinations),
    )
```

**Step 2: Update orchestrator_legacy.py to delegate**

```python
# Add import:
from elspeth.engine.orchestrator.aggregation import (
    check_aggregation_timeouts,
    find_aggregation_transform,
    flush_remaining_aggregation_buffers,
    handle_incomplete_batches,
)
from elspeth.engine.orchestrator.types import AggregationFlushResult

# Update methods to delegate (example for _check_aggregation_timeouts):
def _check_aggregation_timeouts(
    self,
    config: PipelineConfig,
    processor: RowProcessor,
    ctx: PluginContext,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
    default_sink_name: str,
    agg_transform_lookup: dict[str, tuple[TransformProtocol, int]] | None = None,
) -> AggregationFlushResult:
    """Delegate to aggregation module."""
    return check_aggregation_timeouts(
        config, processor, ctx, pending_tokens, default_sink_name, agg_transform_lookup
    )

def _find_aggregation_transform(
    self,
    config: PipelineConfig,
    agg_node_id_str: str,
    agg_name: str,
) -> tuple[TransformProtocol, int]:
    """Delegate to aggregation module."""
    return find_aggregation_transform(config, agg_node_id_str, agg_name)

def _handle_incomplete_batches(
    self,
    recorder: LandscapeRecorder,
    run_id: str,
) -> None:
    """Delegate to aggregation module."""
    handle_incomplete_batches(recorder, run_id)

def _flush_remaining_aggregation_buffers(
    self,
    config: PipelineConfig,
    processor: RowProcessor,
    ctx: PluginContext,
    pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
    default_sink_name: str,
    run_id: str,
    recorder: LandscapeRecorder,
    checkpoint: bool = True,
    last_node_id: str | None = None,
) -> AggregationFlushResult:
    """Delegate to aggregation module."""
    # Create checkpoint callback if enabled
    #
    # IMPORTANT: State Capture Pattern
    # ---------------------------------
    # The closure captures `last_node_id` from the enclosing scope.
    # This is INTENTIONAL and SAFE because:
    # 1. `last_node_id` is passed as a parameter to THIS method (value, not reference)
    # 2. The value is frozen at closure creation time
    # 3. The closure is called within the same method invocation (no async drift)
    #
    # If last_node_id were a mutable object or read from self.* after closure
    # creation, we would risk recording incorrect checkpoint state (audit violation).
    #
    checkpoint_callback = None
    if checkpoint and last_node_id is not None:
        # Capture last_node_id by closure - value is frozen at this point
        captured_node_id = last_node_id  # Explicit capture for clarity
        def checkpoint_callback(run_id: str, token_id: str, agg_state: dict) -> None:
            self._maybe_checkpoint(
                run_id=run_id,
                token_id=token_id,
                node_id=captured_node_id,  # Use captured value, not last_node_id
                aggregation_state=agg_state,
            )

    return flush_remaining_aggregation_buffers(
        config, processor, ctx, pending_tokens, default_sink_name,
        run_id, recorder, checkpoint_callback
    )
```

**IMPORTANT: Update call sites to use AggregationFlushResult**

In `run()` and `_execute_run()`, change from tuple destructuring:
```python
# OLD (tuple):
(succeeded, failed, routed, quarantined, coalesced, forked, expanded, buffered, destinations) = \
    self._check_aggregation_timeouts(...)

# NEW (dataclass):
flush_result = self._check_aggregation_timeouts(...)
rows_succeeded += flush_result.rows_succeeded
rows_failed += flush_result.rows_failed
rows_routed += flush_result.rows_routed
rows_quarantined += flush_result.rows_quarantined
rows_coalesced += flush_result.rows_coalesced
rows_forked += flush_result.rows_forked
rows_expanded += flush_result.rows_expanded
rows_buffered += flush_result.rows_buffered
for dest, count in flush_result.routed_destinations.items():
    routed_destinations[dest] += count
```

**Step 3: Run tests**

```bash
.venv/bin/python -m pytest tests/engine/ tests/integration/ -x -q
```

**Step 4: Commit**

```bash
git add src/elspeth/engine/orchestrator/aggregation.py
git add src/elspeth/engine/orchestrator_legacy.py
git commit -m "refactor(engine): extract aggregation handling to aggregation.py

Move timeout checking and flush logic to dedicated module.
Replace 9-element tuple with AggregationFlushResult dataclass for type safety."
```

---

## Task 5: Create Core Module with Orchestrator Class

**Files:**
- Create: `src/elspeth/engine/orchestrator/core.py`
- Modify: `src/elspeth/engine/orchestrator/__init__.py`
- Delete: `src/elspeth/engine/orchestrator_legacy.py`

**CONSIDERATION: Fail-Fast Signing Key Validation**

Currently, signing key validation (`ELSPETH_SIGNING_KEY`) happens during export - AFTER the entire pipeline run completes. This means a missing signing key is discovered only after all processing is done.

For better fail-fast behavior, consider adding validation to `Orchestrator.__init__` or `run()` when `settings.landscape.export.sign=True`:

```python
# In Orchestrator.__init__ or run(), after settings are available:
if settings and settings.landscape.export.enabled and settings.landscape.export.sign:
    if "ELSPETH_SIGNING_KEY" not in os.environ:
        raise ValueError(
            "ELSPETH_SIGNING_KEY required when landscape.export.sign=true. "
            "Set the environment variable or disable signed export."
        )
```

This is optional but recommended for production deployments.

**Step 1: Create core.py with the Orchestrator class**

Move the Orchestrator class from orchestrator_legacy.py. The class keeps `__init__`, `run()`, `resume()`, `_execute_run()`, and `_process_resumed_rows()` as main methods, with other private methods delegating to the extracted modules.

**Key structure for core.py:**

```python
# src/elspeth/engine/orchestrator/core.py
"""Core Orchestrator class for pipeline execution.

This module contains the main Orchestrator class that coordinates:
- Run initialization
- Source loading
- Row processing
- Sink writing
- Run completion
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

# Standard imports from original orchestrator.py
from elspeth import __version__ as ENGINE_VERSION
from elspeth.contracts import BatchPendingError, ExportStatus, NodeType, PendingOutcome, RowOutcome, RunStatus, TokenInfo
from elspeth.contracts.cli import ProgressEvent
from elspeth.contracts.config import RuntimeRetryConfig
from elspeth.contracts.enums import TriggerType
from elspeth.contracts.errors import OrchestrationInvariantError
from elspeth.contracts.events import (
    PhaseAction,
    PhaseCompleted,
    PhaseError,
    PhaseStarted,
    PipelinePhase,
    RunCompletionStatus,
    RunSummary,
)
from elspeth.contracts.types import (
    AggregationName,
    BranchName,
    CoalesceName,
    GateName,
    NodeID,
    SinkName,
)
from elspeth.core.canonical import stable_hash
from elspeth.core.config import AggregationSettings, CoalesceSettings, GateSettings
from elspeth.core.dag import ExecutionGraph
from elspeth.core.landscape import LandscapeDB, LandscapeRecorder
from elspeth.core.operations import track_operation
from elspeth.engine.processor import RowProcessor
from elspeth.engine.retry import RetryManager
from elspeth.engine.spans import SpanFactory
from elspeth.plugins.context import PluginContext
from elspeth.plugins.protocols import GateProtocol, SinkProtocol, SourceProtocol, TransformProtocol

# Import from submodules
from elspeth.engine.orchestrator.aggregation import (
    check_aggregation_timeouts,
    find_aggregation_transform,
    flush_remaining_aggregation_buffers,
    handle_incomplete_batches,
)
from elspeth.engine.orchestrator.export import (
    export_landscape,
    reconstruct_schema_from_json,
)
from elspeth.engine.orchestrator.types import (
    AggregationFlushResult,
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)
from elspeth.engine.orchestrator.validation import (
    validate_route_destinations,
    validate_source_quarantine_destination,
    validate_transform_error_sinks,
)

if TYPE_CHECKING:
    from elspeth.contracts import ResumePoint
    from elspeth.contracts.config.runtime import RuntimeCheckpointConfig, RuntimeConcurrencyConfig
    from elspeth.contracts.events import TelemetryEvent
    from elspeth.contracts.payload_store import PayloadStore
    from elspeth.core.checkpoint import CheckpointManager
    from elspeth.core.config import ElspethSettings
    from elspeth.core.events import EventBusProtocol
    from elspeth.core.rate_limit import RateLimitRegistry
    from elspeth.engine.clock import Clock
    from elspeth.telemetry import TelemetryManager


class Orchestrator:
    """Orchestrates full pipeline runs.

    Manages the complete lifecycle:
    1. Begin run in Landscape
    2. Register all nodes (and set node_id on each plugin instance)
    3. Load rows from source
    4. Process rows through transforms
    5. Write to sinks
    6. Complete run

    The Orchestrator sets node_id on each plugin instance AFTER registering
    it with Landscape. This is part of the plugin protocol contract - all
    plugins define node_id: str | None and the orchestrator populates it.
    """

    def __init__(
        self,
        db: LandscapeDB,
        *,
        event_bus: EventBusProtocol = None,  # type: ignore[assignment]
        canonical_version: str = "sha256-rfc8785-v1",
        checkpoint_manager: CheckpointManager | None = None,
        checkpoint_config: RuntimeCheckpointConfig | None = None,
        clock: Clock | None = None,
        rate_limit_registry: RateLimitRegistry | None = None,
        concurrency_config: RuntimeConcurrencyConfig | None = None,
        telemetry_manager: TelemetryManager | None = None,
    ) -> None:
        # ... (copy __init__ implementation from orchestrator_legacy.py)
        pass

    def run(
        self,
        config: PipelineConfig,
        graph: ExecutionGraph | None = None,
        settings: ElspethSettings | None = None,
        batch_checkpoints: dict[str, dict[str, Any]] | None = None,
        *,
        payload_store: PayloadStore,
    ) -> RunResult:
        # ... (copy run implementation from orchestrator_legacy.py)
        # Uses imported helpers via delegation methods below
        pass

    def resume(
        self,
        resume_point: ResumePoint,
        config: PipelineConfig,
        graph: ExecutionGraph,
        *,
        payload_store: PayloadStore,
        settings: ElspethSettings | None = None,
    ) -> RunResult:
        # ... (copy resume implementation from orchestrator_legacy.py)
        pass

    def _execute_run(
        self,
        config: PipelineConfig,
        run_id: str,
        recorder: LandscapeRecorder,
        graph: ExecutionGraph,
        source_id: NodeID,
        transform_id_map: dict[int, NodeID],
        sink_id_map: dict[SinkName, NodeID],
        config_gate_id_map: dict[GateName, NodeID],
        last_node_id: NodeID,
        settings: ElspethSettings | None,
        payload_store: PayloadStore,
        retry_manager: RetryManager | None = None,
        batch_checkpoints: dict[str, dict[str, Any]] | None = None,
    ) -> RunResult:
        # ... (copy _execute_run implementation)
        # This is the main execution loop (~800 lines)
        pass

    def _process_resumed_rows(
        self,
        # ... parameters
    ) -> RunResult:
        # ... (copy _process_resumed_rows implementation)
        pass

    # ==== Telemetry helpers (kept in core - small) ====

    def _emit_telemetry(self, event: TelemetryEvent) -> None:
        """Emit telemetry event if manager is configured."""
        if self._telemetry is not None:
            self._telemetry.handle_event(event)

    def _flush_telemetry(self) -> None:
        """Flush telemetry events if manager is configured."""
        if self._telemetry is not None:
            self._telemetry.flush()

    # ==== Checkpoint helpers (kept in core - uses self._checkpoint_manager) ====

    def _maybe_checkpoint(
        self,
        run_id: str,
        token_id: str,
        node_id: str,
        aggregation_state: dict[str, Any] | None = None,
    ) -> None:
        # ... (copy implementation)
        pass

    def _delete_checkpoints(self, run_id: str) -> None:
        # ... (copy implementation)
        pass

    # ==== Cleanup helper (kept in core - uses self._events) ====

    def _cleanup_transforms(self, config: PipelineConfig) -> None:
        # ... (copy implementation)
        pass

    # ==== Delegation methods to extracted modules ====

    def _validate_route_destinations(
        self,
        route_resolution_map: dict[tuple[NodeID, str], str],
        available_sinks: set[str],
        transform_id_map: dict[int, NodeID],
        transforms: list[RowPlugin],
        config_gate_id_map: dict[GateName, NodeID] | None = None,
        config_gates: list[GateSettings] | None = None,
    ) -> None:
        validate_route_destinations(
            route_resolution_map, available_sinks, transform_id_map,
            transforms, config_gate_id_map, config_gates
        )

    def _validate_transform_error_sinks(
        self,
        transforms: list[RowPlugin],
        available_sinks: set[str],
        _transform_id_map: dict[int, NodeID],
    ) -> None:
        validate_transform_error_sinks(transforms, available_sinks)

    def _validate_source_quarantine_destination(
        self,
        source: SourceProtocol,
        available_sinks: set[str],
    ) -> None:
        validate_source_quarantine_destination(source, available_sinks)

    def _export_landscape(
        self,
        run_id: str,
        settings: ElspethSettings,
        sinks: dict[str, Any],
    ) -> None:
        export_landscape(self._db, run_id, settings, sinks)

    def _reconstruct_schema_from_json(self, schema_dict: dict[str, Any]) -> type:
        return reconstruct_schema_from_json(schema_dict)

    def _check_aggregation_timeouts(
        self,
        config: PipelineConfig,
        processor: RowProcessor,
        ctx: PluginContext,
        pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
        default_sink_name: str,
        agg_transform_lookup: dict[str, tuple[TransformProtocol, int]] | None = None,
    ) -> AggregationFlushResult:
        return check_aggregation_timeouts(
            config, processor, ctx, pending_tokens, default_sink_name, agg_transform_lookup
        )

    def _find_aggregation_transform(
        self,
        config: PipelineConfig,
        agg_node_id_str: str,
        agg_name: str,
    ) -> tuple[TransformProtocol, int]:
        return find_aggregation_transform(config, agg_node_id_str, agg_name)

    def _handle_incomplete_batches(
        self,
        recorder: LandscapeRecorder,
        run_id: str,
    ) -> None:
        handle_incomplete_batches(recorder, run_id)

    def _flush_remaining_aggregation_buffers(
        self,
        config: PipelineConfig,
        processor: RowProcessor,
        ctx: PluginContext,
        pending_tokens: dict[str, list[tuple[TokenInfo, PendingOutcome | None]]],
        default_sink_name: str,
        run_id: str,
        recorder: LandscapeRecorder,
        checkpoint: bool = True,
        last_node_id: str | None = None,
    ) -> AggregationFlushResult:
        # See Task 4 for detailed documentation on checkpoint callback state capture pattern
        checkpoint_callback = None
        if checkpoint and last_node_id is not None:
            captured_node_id = last_node_id  # Explicit capture for audit trail integrity
            def checkpoint_callback(rid: str, tid: str, agg_state: dict) -> None:
                self._maybe_checkpoint(run_id=rid, token_id=tid, node_id=captured_node_id, aggregation_state=agg_state)
        return flush_remaining_aggregation_buffers(
            config, processor, ctx, pending_tokens, default_sink_name,
            run_id, recorder, checkpoint_callback
        )

    # ==== Other helpers kept in core ====

    def _assign_plugin_node_ids(self, ...) -> None:
        # ... (copy implementation - small, uses only self)
        pass

    def _compute_coalesce_step_map(self, ...) -> dict[str, int]:
        # ... (copy implementation - small, pure function)
        pass
```

**Step 2: Update __init__.py to import from core**

```python
# src/elspeth/engine/orchestrator/__init__.py
"""Orchestrator package: Full run lifecycle management."""

from elspeth.engine.orchestrator.core import Orchestrator
from elspeth.engine.orchestrator.types import (
    AggregationFlushResult,
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)

__all__ = [
    "AggregationFlushResult",
    "Orchestrator",
    "PipelineConfig",
    "RouteValidationError",
    "RowPlugin",
    "RunResult",
]
```

**Step 3: Delete orchestrator_legacy.py**

```bash
rm src/elspeth/engine/orchestrator_legacy.py
```

**Step 4: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -x
```

**Step 5: Verify line counts**

```bash
wc -l src/elspeth/engine/orchestrator/*.py
```
Expected (approximate):
```
  30 src/elspeth/engine/orchestrator/__init__.py
 120 src/elspeth/engine/orchestrator/types.py
 120 src/elspeth/engine/orchestrator/validation.py
 200 src/elspeth/engine/orchestrator/export.py
 350 src/elspeth/engine/orchestrator/aggregation.py
1800 src/elspeth/engine/orchestrator/core.py
2620 total
```

If core.py exceeds 1500 lines, consider extracting `_execute_run()` to a separate `execution.py` module.

**Step 6: Commit**

```bash
git add src/elspeth/engine/orchestrator/
git rm src/elspeth/engine/orchestrator_legacy.py
git commit -m "refactor(engine): complete orchestrator package extraction

Orchestrator is now a package with focused modules:
- types.py: PipelineConfig, RunResult, RouteValidationError, AggregationFlushResult
- validation.py: Route and sink validation
- export.py: Landscape export functionality
- aggregation.py: Aggregation timeout/flush handling
- core.py: Main Orchestrator class

Public API unchanged. AggregationFlushResult replaces 9-tuple anti-pattern."
```

---

## Task 6: Update engine/__init__.py and Run Type Checks

**Files:**
- Verify: `src/elspeth/engine/__init__.py` (should work without changes)

**Step 1: Verify engine __init__.py imports work**

The current engine/__init__.py already imports from `elspeth.engine.orchestrator` which will now resolve to the package:

```python
from elspeth.engine.orchestrator import (
    Orchestrator,
    PipelineConfig,
    RouteValidationError,
    RunResult,
)
```

No changes needed if the package __init__.py exports correctly.

**Step 2: Run mypy on the entire engine package**

```bash
.venv/bin/python -m mypy src/elspeth/engine/
```
Expected: No new errors

**Step 3: Run full test suite with coverage**

```bash
.venv/bin/python -m pytest tests/ --cov=src/elspeth/engine/orchestrator -x
```
Expected: All tests pass, coverage shows new modules are exercised

**Step 4: Verify import time regression**

Compare against baseline from Pre-Flight Checks:
```bash
echo "Import time after refactor:"
time python -c "from elspeth.engine.orchestrator import Orchestrator"
```

If import time increased by >2x from baseline, investigate:
- Circular import resolution overhead
- Missing lazy imports
- Unnecessary eager imports in __init__.py

**Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(engine): resolve any type errors from orchestrator refactor"
```

---

## Task 7: Final Verification and Cleanup

**Step 1: Verify legacy file is deleted (CRITICAL - No Legacy Code Policy)**

```bash
# CRITICAL: Verify orchestrator_legacy.py does not exist
# This is a BLOCKING check - do NOT proceed if this file exists
if [ -f src/elspeth/engine/orchestrator_legacy.py ]; then
    echo "ERROR: orchestrator_legacy.py still exists!"
    echo "This violates the No Legacy Code Policy."
    echo "All migration tasks (1-5) must complete before merge."
    exit 1
fi
echo "✓ Legacy file correctly deleted"
```

**Step 1a: Verify no imports break**

```bash
# Check nothing imports the old file path directly
grep -r "from elspeth.engine.orchestrator import" src/ tests/ | grep -v "__pycache__"
grep -r "from elspeth.engine import" src/ tests/ | grep -v "__pycache__"
```

**Step 2: Verify line counts meet criteria**

```bash
wc -l src/elspeth/engine/orchestrator/*.py
```

**Step 3: Run linting**

```bash
.venv/bin/python -m ruff check src/elspeth/engine/orchestrator/
.venv/bin/python -m ruff check --fix src/elspeth/engine/orchestrator/
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore(engine): final cleanup after orchestrator refactor"
```

**Step 5: Close the bead**

```bash
bd close g16 --reason="Orchestrator extracted to package with focused modules. All tests pass."
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Circular imports | TYPE_CHECKING guards, careful module ordering, runtime imports where needed |
| Broken public API | Re-export everything from __init__.py, delegation methods preserve signatures |
| Test failures | Run tests after each extraction task |
| Import time regression | Use lazy imports if needed (defer to Task 6) |
| Tuple position errors | AggregationFlushResult dataclass replaces 9-tuple with named fields |

## Rollback Plan

If issues discovered after merge:
```bash
git revert HEAD~N  # Revert N commits
# Or restore from git history
git checkout HEAD~N -- src/elspeth/engine/orchestrator.py
```

---

## Summary

| Task | Description | Lines Extracted |
|------|-------------|-----------------|
| 1 | Create package + types.py + AggregationFlushResult | ~120 |
| 1.5 | Add AggregationFlushResult field mapping tests | ~100 (tests) |
| 2 | Extract validation.py | ~120 |
| 3 | Extract export.py | ~200 |
| 4 | Extract aggregation.py | ~350 |
| 5 | Create core.py | ~1800 |
| 6 | Update imports, type check, verify import time | - |
| 7 | Final verification (including legacy file check) | - |

**Total: 8 tasks, ~2600 lines across 5 modules (down from 3148 in one file)**

**Key improvements from plan review (2026-02-03):**
1. Fixed Task 1 step ordering (rename before creating __init__.py)
2. Added AggregationFlushResult dataclass to replace fragile 9-element tuple
3. **NEW: Task 1.5** - Explicit tests for AggregationFlushResult field mapping and immutability
4. **NEW: Pre-flight import time baseline** - Detect import time regression after refactor
5. **NEW: Legacy file check in Task 7** - Explicit verification orchestrator_legacy.py is deleted
6. **NEW: Checkpoint callback state capture documentation** - Prevent audit trail corruption
7. **NEW: types.py leaf module warning** - Prevent circular import cycles
8. **NEW: Fail-fast signing key validation consideration** - Optional improvement for production
9. Complete aggregation.py code shown (all 4 functions)
10. Task 5 has clear structure showing delegation pattern
11. Accurate line count estimates
12. Documented the `_transform_id_map` unused parameter situation
