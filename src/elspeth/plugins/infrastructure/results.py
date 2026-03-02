"""Result types for plugin operations.

These types define the contracts between plugins and the SDA engine.

IMPORTANT: Types are now defined in elspeth.contracts.results.
This module re-exports them as part of the public plugin API.

NOTE: AcceptResult was deleted in aggregation structural cleanup.
Aggregation is now engine-controlled via batch-aware transforms.
"""

from elspeth.contracts import (
    RoutingAction,
    RowOutcome,
    SourceRow,
    TransformResult,
)

# Re-export types as part of public plugin API
# NOTE: GateResult removed — gates are config-driven (not plugins),
# so GateResult is not part of the plugin API. Engine code imports
# it directly from elspeth.contracts.
__all__ = [
    "RoutingAction",
    "RowOutcome",
    "SourceRow",
    "TransformResult",
]
