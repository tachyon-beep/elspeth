"""Result types for plugin operations.

Types are defined in elspeth.contracts.results.
This module re-exports them as part of the public plugin API.
"""

from elspeth.contracts import (
    RoutingAction,
    RowOutcome,
    SourceRow,
    TransformResult,
)

__all__ = [
    "RoutingAction",
    "RowOutcome",
    "SourceRow",
    "TransformResult",
]
