# src/elspeth/engine/orchestrator/validation.py
"""Pipeline configuration validation functions.

These functions validate route configurations at pipeline initialization,
BEFORE any rows are processed. This catches config errors early instead
of failing mid-run with cryptic errors.

Validations performed:
- Gate route destinations reference existing sinks
- Transform on_error destinations reference existing sinks
- Source quarantine destinations reference existing sinks

IMPORTANT: Import Cycle Prevention
----------------------------------
This module imports RouteValidationError from types.py (a leaf module).
It imports protocols at runtime because isinstance() checks require them.
Other imports use TYPE_CHECKING to avoid cycles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Import GateName at runtime - used in function body, not just type hints
from elspeth.contracts import RouteDestination, RouteDestinationKind
from elspeth.contracts.types import GateName
from elspeth.engine.orchestrator.types import RouteValidationError

# Import protocols at runtime - needed for isinstance() checks
from elspeth.plugins.protocols import GateProtocol, TransformProtocol

if TYPE_CHECKING:
    from elspeth.contracts.types import NodeID
    from elspeth.core.config import GateSettings
    from elspeth.engine.orchestrator.types import RowPlugin
    from elspeth.plugins.protocols import SourceProtocol


def validate_route_destinations(
    route_resolution_map: dict[tuple[NodeID, str], RouteDestination],
    available_sinks: set[str],
    transform_id_map: dict[int, NodeID],
    transforms: list[RowPlugin],
    config_gate_id_map: dict[GateName, NodeID] | None = None,
    config_gates: list[GateSettings] | None = None,
) -> None:
    """Validate all route destinations reference existing sinks.

    Called at pipeline initialization, BEFORE any rows are processed.
    This catches config errors early instead of failing mid-run.

    Args:
        route_resolution_map: Maps (gate_node_id, route_label) -> resolved destination
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
        for gate_config in config_gates:
            # Graph must have ID for every config gate - crash if missing
            node_id = config_gate_id_map[GateName(gate_config.name)]
            node_id_to_gate_name[node_id] = gate_config.name

    # Check each route destination
    for (gate_node_id, route_label), destination in route_resolution_map.items():
        if destination.kind in (RouteDestinationKind.CONTINUE, RouteDestinationKind.FORK, RouteDestinationKind.PROCESSING_NODE):
            continue

        if destination.kind != RouteDestinationKind.SINK:
            continue

        if destination.sink_name is None:
            raise ValueError(
                f"Route destination for gate_node_id={gate_node_id!r}, route_label={route_label!r} has kind='sink' but sink_name is None"
            )

        # destination should be a sink name
        if destination.sink_name not in available_sinks:
            # Every gate in route_resolution_map MUST have a name mapping
            gate_name = node_id_to_gate_name[gate_node_id]
            raise RouteValidationError(
                f"Gate '{gate_name}' can route to '{destination.sink_name}' "
                f"(via route label '{route_label}') but no sink named "
                f"'{destination.sink_name}' exists. Available sinks: {sorted(available_sinks)}"
            )


def validate_transform_error_sinks(
    transforms: list[RowPlugin],
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

        on_error = transform.on_error

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
    source: SourceProtocol,
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
