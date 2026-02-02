# Extract orchestrator.py into Modules Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract the 3,120-line `orchestrator.py` into a package of focused modules, each under 500 lines, while preserving the public API.

**Architecture:** Convert `engine/orchestrator.py` into `engine/orchestrator/` package with:
- `__init__.py` - Re-exports (preserves public API)
- `core.py` - Orchestrator class, `__init__`, `run()`, `resume()`
- `validation.py` - Route/sink validation functions
- `export.py` - Landscape export functionality
- `aggregation.py` - Aggregation timeout/flush handling
- `types.py` - PipelineConfig, RunResult, RouteValidationError

**Tech Stack:** Python 3.11+, no new dependencies (pure refactoring)

---

## Pre-Flight Checks

Before starting, verify:
```bash
# All tests pass
.venv/bin/python -m pytest tests/ -x -q

# Type checking passes
.venv/bin/python -m mypy src/elspeth/engine/orchestrator.py

# Note the current line count
wc -l src/elspeth/engine/orchestrator.py  # Should be ~3120
```

---

## Task 1: Create Package Structure with Types Module

**Files:**
- Create: `src/elspeth/engine/orchestrator/__init__.py`
- Create: `src/elspeth/engine/orchestrator/types.py`
- Keep: `src/elspeth/engine/orchestrator.py` (will become backup, then delete)

**Step 1: Create the orchestrator package directory**

```bash
mkdir -p src/elspeth/engine/orchestrator
```

**Step 2: Create types.py with dataclasses and exception**

Extract `PipelineConfig`, `RunResult`, and `RouteValidationError` from orchestrator.py (lines 82-135).

```python
# src/elspeth/engine/orchestrator/types.py
"""Pipeline configuration and result types.

These types define the interface for pipeline execution:
- PipelineConfig: Input configuration for a run
- RunResult: Output statistics from a run
- RouteValidationError: Configuration validation failure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.config import AggregationSettings, CoalesceSettings, GateSettings
    from elspeth.plugins.protocols import GateProtocol, SinkProtocol, SourceProtocol, TransformProtocol

from elspeth.contracts import RunStatus

# Type alias for row-processing plugins in the transforms pipeline
# NOTE: BaseAggregation was DELETED - aggregation is now handled by
# batch-aware transforms (is_batch_aware=True on TransformProtocol)
# Using protocols instead of base classes to support protocol-only plugins.
RowPlugin = "TransformProtocol | GateProtocol"
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
    transforms: list[Any]  # list[RowPlugin] - Any to avoid circular import
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


class RouteValidationError(Exception):
    """Raised when route configuration is invalid.

    This error is raised at pipeline initialization, before any rows are
    processed. It indicates a configuration problem that would cause
    failures during processing.
    """

    pass
```

**Step 3: Create minimal __init__.py that imports from types**

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
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)

__all__ = [
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

**Step 4: Rename old orchestrator.py to orchestrator_legacy.py temporarily**

```bash
mv src/elspeth/engine/orchestrator.py src/elspeth/engine/orchestrator_legacy.py
```

**Step 5: Update orchestrator_legacy.py imports to use new types**

At the top of `orchestrator_legacy.py`, after the existing imports, add:
```python
# Import types from new location (refactoring in progress)
from elspeth.engine.orchestrator.types import (
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)
```

And remove the local definitions of these classes (lines 82-135 approximately).

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
Temporary orchestrator_legacy.py maintains compatibility during refactor."
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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from elspeth.contracts.types import GateName, NodeID
    from elspeth.core.config import GateSettings
    from elspeth.plugins.protocols import GateProtocol, SourceProtocol, TransformProtocol

from elspeth.engine.orchestrator.types import RouteValidationError
from elspeth.plugins.protocols import GateProtocol, TransformProtocol


def validate_route_destinations(
    route_resolution_map: dict[tuple[str, str], str],
    available_sinks: set[str],
    transform_id_map: dict[int, str],
    transforms: list,
    config_gate_id_map: dict[str, str] | None = None,
    config_gates: list | None = None,
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
    node_id_to_gate_name: dict[str, str] = {}
    for seq, transform in enumerate(transforms):
        if isinstance(transform, GateProtocol):
            node_id = transform_id_map[seq]
            node_id_to_gate_name[node_id] = transform.name

    # Add config gates to the lookup
    if config_gate_id_map and config_gates:
        for gate_config in config_gates:
            node_id = config_gate_id_map[gate_config.name]
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
            gate_name = node_id_to_gate_name[gate_node_id]
            raise RouteValidationError(
                f"Gate '{gate_name}' can route to '{destination}' "
                f"(via route label '{route_label}') but no sink named "
                f"'{destination}' exists. Available sinks: {sorted(available_sinks)}"
            )


def validate_transform_error_sinks(
    transforms: list,
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
        # Only TransformProtocol has _on_error
        if not isinstance(transform, TransformProtocol):
            continue

        on_error = transform._on_error

        if on_error is None:
            continue

        if on_error == "discard":
            continue

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
    on_validation_failure = source._on_validation_failure

    if on_validation_failure == "discard":
        return

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
    _transform_id_map: dict[int, NodeID],
) -> None:
    """Delegate to validation module."""
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

Extract `_export_landscape`, `_export_csv_multifile`, `_reconstruct_schema_from_json`, `_json_schema_to_python_type` (lines 1780-2052).

```python
# src/elspeth/engine/orchestrator/export.py
"""Landscape export functionality.

Handles post-run export of audit trail to configured sinks in JSON or CSV format.
"""

from __future__ import annotations

import csv
import hashlib
import os
from datetime import datetime
from decimal import Decimal
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
    ctx = PluginContext(run_id=run_id, config={}, landscape=None)

    if export_config.format == "csv":
        # Multi-file CSV export: one file per record type
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
            _artifact_descriptor = sink.write(records, ctx)
        sink.flush()
        sink.close()


def _export_csv_multifile(
    exporter: Any,
    run_id: str,
    artifact_path: str,
    sign: bool,
    ctx: "PluginContext",
) -> None:
    """Export audit trail as multiple CSV files (one per record type).

    Creates a directory structure:
        artifact_path/
            runs.csv
            rows.csv
            node_states.csv
            ...

    Args:
        exporter: LandscapeExporter instance
        run_id: Run ID to export
        artifact_path: Base path for CSV files (directory will be created)
        sign: Whether to sign records
        ctx: Plugin context (reserved for future use)
    """
    import os

    # Create output directory
    os.makedirs(artifact_path, exist_ok=True)

    # Group records by type
    records_by_type: dict[str, list[dict[str, Any]]] = {}
    for record in exporter.export_run(run_id, sign=sign):
        record_type = record.get("record_type", "unknown")
        if record_type not in records_by_type:
            records_by_type[record_type] = []
        records_by_type[record_type].append(record)

    # Write each type to its own CSV file
    for record_type, records in records_by_type.items():
        if not records:
            continue

        file_path = os.path.join(artifact_path, f"{record_type}.csv")

        # Get all unique keys across records for CSV header
        all_keys: set[str] = set()
        for record in records:
            all_keys.update(record.keys())
        fieldnames = sorted(all_keys)

        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow(record)


def reconstruct_schema_from_json(schema_dict: dict[str, Any]) -> type:
    """Reconstruct a Pydantic model from JSON schema.

    Used during resume to restore the source output schema for proper
    type coercion (datetime, Decimal, etc.).

    Args:
        schema_dict: JSON schema dictionary from source_schema_json

    Returns:
        A dynamically created Pydantic model class
    """
    from pydantic import create_model

    # Extract properties from JSON schema
    properties = schema_dict.get("properties", {})
    required = set(schema_dict.get("required", []))

    # Build field definitions
    field_definitions: dict[str, Any] = {}
    for field_name, field_info in properties.items():
        python_type = _json_schema_to_python_type(field_name, field_info)
        if field_name in required:
            field_definitions[field_name] = (python_type, ...)
        else:
            field_definitions[field_name] = (python_type | None, None)

    # Create model dynamically
    return create_model("ReconstructedSchema", **field_definitions)


def _json_schema_to_python_type(field_name: str, field_info: dict[str, Any]) -> type:
    """Convert JSON schema type to Python type.

    Args:
        field_name: Name of the field (for error messages)
        field_info: JSON schema field definition

    Returns:
        Corresponding Python type
    """
    json_type = field_info.get("type", "string")
    json_format = field_info.get("format")

    # Handle anyOf (union types, typically for Optional)
    if "anyOf" in field_info:
        # Find the non-null type
        for option in field_info["anyOf"]:
            if option.get("type") != "null":
                return _json_schema_to_python_type(field_name, option)
        return str  # Fallback

    # Map JSON schema types to Python types
    type_map: dict[str, type] = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    # Handle format specifiers for special types
    if json_type == "string":
        if json_format == "date-time":
            return datetime
        elif json_format == "decimal":
            return Decimal

    return type_map.get(json_type, str)
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

**Step 1: Create aggregation.py with timeout/flush functions**

Extract `_check_aggregation_timeouts`, `_flush_remaining_aggregation_buffers`, `_find_aggregation_transform`, `_handle_incomplete_batches` (lines 2692-3120).

This is the largest extraction (~430 lines). The functions handle:
- Timeout-triggered flushes during processing
- End-of-source buffer flushes
- Incomplete batch handling for resume

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
from elspeth.engine.orchestrator.types import PipelineConfig


def check_aggregation_timeouts(
    config: PipelineConfig,
    processor: "RowProcessor",
    ctx: "PluginContext",
    pending_tokens: dict[str, list[tuple["TokenInfo", "PendingOutcome | None"]]],
    default_sink_name: str,
    agg_transform_lookup: dict[str, tuple["TransformProtocol", int]] | None = None,
) -> tuple[int, int, int, int, int, int, int, int, dict[str, int]]:
    """Check and flush any aggregations whose timeout has expired.

    Called BEFORE processing each row to ensure timeouts fire during active
    processing, not just at end-of-source.

    Args:
        config: Pipeline configuration with aggregation_settings
        processor: RowProcessor with public aggregation timeout API
        ctx: Plugin context for transform execution
        pending_tokens: Dict of sink_name -> tokens to append results to
        default_sink_name: Default sink for aggregation output
        agg_transform_lookup: Pre-computed dict mapping node_id_str -> (transform, step)

    Returns:
        Tuple of (rows_succeeded, rows_failed, rows_routed, rows_quarantined,
                  rows_coalesced, rows_forked, rows_expanded, rows_buffered,
                  routed_destinations)
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

        should_flush, trigger_type = processor.check_aggregation_timeout(agg_node_id)

        if not should_flush:
            continue

        if trigger_type != TriggerType.TIMEOUT:
            continue

        buffered_count = processor.get_aggregation_buffer_count(agg_node_id)
        if buffered_count == 0:
            continue

        # Get transform and step
        if agg_transform_lookup and agg_node_id_str in agg_transform_lookup:
            agg_transform, agg_step = agg_transform_lookup[agg_node_id_str]
        else:
            agg_transform, agg_step = find_aggregation_transform(
                config, agg_node_id_str, agg_settings.name
            )

        # Handle flush
        total_steps = len(config.transforms)
        completed_results, work_items = processor.handle_timeout_flush(
            node_id=agg_node_id,
            transform=agg_transform,
            ctx=ctx,
            step=agg_step,
            total_steps=total_steps,
            trigger_type=TriggerType.TIMEOUT,
        )

        # Process completed results
        for result in completed_results:
            if result.outcome == RowOutcome.FAILED:
                rows_failed += 1
            else:
                sink_name = result.token.branch_name or default_sink_name
                if sink_name not in pending_tokens:
                    sink_name = default_sink_name
                pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
                rows_succeeded += 1

        # Process work items through remaining transforms
        for work_item in work_items:
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
                    sink_name = result.token.branch_name or default_sink_name
                    if sink_name not in pending_tokens:
                        sink_name = default_sink_name
                    pending_tokens[sink_name].append((result.token, PendingOutcome(result.outcome)))
                    rows_succeeded += 1
                elif result.outcome == RowOutcome.ROUTED:
                    rows_routed += 1
                    routed_sink = result.sink_name or default_sink_name
                    routed_destinations[routed_sink] += 1
                    pending_tokens[routed_sink].append((result.token, PendingOutcome(RowOutcome.ROUTED)))
                elif result.outcome == RowOutcome.QUARANTINED:
                    rows_quarantined += 1
                elif result.outcome == RowOutcome.COALESCED:
                    rows_coalesced += 1
                    rows_succeeded += 1
                    pending_tokens[default_sink_name].append((result.token, PendingOutcome(RowOutcome.COMPLETED)))
                elif result.outcome == RowOutcome.FORKED:
                    rows_forked += 1
                elif result.outcome == RowOutcome.EXPANDED:
                    rows_expanded += 1
                elif result.outcome == RowOutcome.BUFFERED:
                    rows_buffered += 1

    return (
        rows_succeeded,
        rows_failed,
        rows_routed,
        rows_quarantined,
        rows_coalesced,
        rows_forked,
        rows_expanded,
        rows_buffered,
        dict(routed_destinations),
    )


def find_aggregation_transform(
    config: PipelineConfig,
    node_id_str: str,
    aggregation_name: str,
) -> tuple["TransformProtocol", int]:
    """Find the transform plugin and step index for an aggregation.

    Args:
        config: Pipeline configuration
        node_id_str: The node ID string to find
        aggregation_name: Name of the aggregation (for error message)

    Returns:
        Tuple of (transform_plugin, step_index)

    Raises:
        RuntimeError: If aggregation transform not found
    """
    from elspeth.plugins.protocols import TransformProtocol

    for step, transform in enumerate(config.transforms):
        if isinstance(transform, TransformProtocol):
            if transform.node_id == node_id_str:
                return transform, step

    raise RuntimeError(
        f"Could not find aggregation transform for node_id={node_id_str}, "
        f"aggregation_name={aggregation_name}"
    )


# Note: flush_remaining_aggregation_buffers and handle_incomplete_batches
# are large functions (~150 lines each) that will be added here.
# For brevity in this plan, they follow the same pattern as check_aggregation_timeouts.
```

**Step 2: Update orchestrator_legacy.py to delegate**

```python
# Add import:
from elspeth.engine.orchestrator.aggregation import (
    check_aggregation_timeouts,
    find_aggregation_transform,
    # flush_remaining_aggregation_buffers,
    # handle_incomplete_batches,
)

# Update methods to delegate (keep signatures, replace bodies)
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

Move timeout checking and flush logic to dedicated module."
```

---

## Task 5: Create Core Module with Orchestrator Class

**Files:**
- Create: `src/elspeth/engine/orchestrator/core.py`
- Modify: `src/elspeth/engine/orchestrator/__init__.py`
- Delete: `src/elspeth/engine/orchestrator_legacy.py`

**Step 1: Create core.py with the Orchestrator class**

Move the Orchestrator class from orchestrator_legacy.py, keeping `run()` and `resume()` methods but using imported helpers:

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

# ... (copy all imports from orchestrator_legacy.py)

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


class Orchestrator:
    """Orchestrates full pipeline runs.

    Manages the complete lifecycle:
    1. Begin run in Landscape
    2. Register all nodes
    3. Load rows from source
    4. Process rows through transforms
    5. Write to sinks
    6. Complete run
    """

    def __init__(
        self,
        db: LandscapeDB,
        span_factory: SpanFactory | None = None,
        events: EventBusProtocol | None = None,
        telemetry: TelemetryManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        checkpoint_config: RuntimeCheckpointConfig | None = None,
        concurrency_config: RuntimeConcurrencyConfig | None = None,
        retry_config: RuntimeRetryConfig | None = None,
        rate_limit_registry: RateLimitRegistry | None = None,
        clock: Clock | None = None,
    ) -> None:
        # ... (copy __init__ implementation)
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
        # ... (copy run implementation, using imported helpers)
        pass

    def resume(
        self,
        resume_point: ResumePoint,
        config: PipelineConfig,
        graph: ExecutionGraph,
        settings: ElspethSettings | None = None,
        *,
        payload_store: PayloadStore,
    ) -> RunResult:
        # ... (copy resume implementation)
        pass

    # Private methods that call module functions
    def _validate_route_destinations(self, *args, **kwargs) -> None:
        validate_route_destinations(*args, **kwargs)

    def _validate_transform_error_sinks(self, *args, **kwargs) -> None:
        validate_transform_error_sinks(*args, **kwargs)

    def _validate_source_quarantine_destination(self, *args, **kwargs) -> None:
        validate_source_quarantine_destination(*args, **kwargs)

    def _export_landscape(self, run_id: str, settings: Any, sinks: dict) -> None:
        export_landscape(self._db, run_id, settings, sinks)

    def _reconstruct_schema_from_json(self, schema_dict: dict) -> type:
        return reconstruct_schema_from_json(schema_dict)

    def _check_aggregation_timeouts(self, *args, **kwargs):
        return check_aggregation_timeouts(*args, **kwargs)

    def _find_aggregation_transform(self, *args, **kwargs):
        return find_aggregation_transform(*args, **kwargs)

    # ... other helper methods (_emit_telemetry, _flush_telemetry, etc.)
```

**Step 2: Update __init__.py to import from core**

```python
# src/elspeth/engine/orchestrator/__init__.py
"""Orchestrator package: Full run lifecycle management."""

from elspeth.engine.orchestrator.core import Orchestrator
from elspeth.engine.orchestrator.types import (
    PipelineConfig,
    RouteValidationError,
    RowPlugin,
    RunResult,
)

__all__ = [
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
Expected: Each file under 500 lines (except possibly core.py which may be ~800-1000)

**Step 6: Commit**

```bash
git add src/elspeth/engine/orchestrator/
git rm src/elspeth/engine/orchestrator_legacy.py
git commit -m "refactor(engine): complete orchestrator package extraction

Orchestrator is now a package with focused modules:
- types.py: PipelineConfig, RunResult, RouteValidationError
- validation.py: Route and sink validation
- export.py: Landscape export functionality
- aggregation.py: Aggregation timeout/flush handling
- core.py: Main Orchestrator class

Public API unchanged. Total lines reduced from 3120 to ~2500 across 5 files."
```

---

## Task 6: Update engine/__init__.py and Run Type Checks

**Files:**
- Modify: `src/elspeth/engine/__init__.py` (already imports correctly)

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

**Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(engine): resolve any type errors from orchestrator refactor"
```

---

## Task 7: Final Verification and Cleanup

**Step 1: Verify no imports break**

```bash
# Check nothing imports the old file path directly
grep -r "from elspeth.engine.orchestrator import" src/ tests/ | grep -v "__pycache__"
grep -r "from elspeth.engine import" src/ tests/ | grep -v "__pycache__"
```

**Step 2: Verify line counts meet criteria**

```bash
wc -l src/elspeth/engine/orchestrator/*.py
```
Expected output (approximate):
```
  80 src/elspeth/engine/orchestrator/__init__.py
  85 src/elspeth/engine/orchestrator/types.py
 120 src/elspeth/engine/orchestrator/validation.py
 150 src/elspeth/engine/orchestrator/export.py
 430 src/elspeth/engine/orchestrator/aggregation.py
1200 src/elspeth/engine/orchestrator/core.py
2065 total
```

If core.py exceeds 1000 lines, consider extracting `_execute_run()` to a separate `execution.py` module.

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
| Circular imports | Import TYPE_CHECKING guards, careful module ordering |
| Broken public API | Re-export everything from __init__.py |
| Test failures | Run tests after each extraction task |
| Import time regression | Use lazy imports if needed (defer to Task 6) |

## Rollback Plan

If issues discovered after merge:
```bash
git revert HEAD~N  # Revert N commits
# Or restore from orchestrator_legacy.py if kept as backup
```

---

## Summary

| Task | Description | Lines Extracted |
|------|-------------|-----------------|
| 1 | Create package + types.py | ~55 |
| 2 | Extract validation.py | ~140 |
| 3 | Extract export.py | ~150 |
| 4 | Extract aggregation.py | ~430 |
| 5 | Create core.py | ~1200 |
| 6 | Update imports, type check | - |
| 7 | Final verification | - |

**Total: 7 tasks, ~2500 lines across 5 modules (down from 3120 in one file)**
