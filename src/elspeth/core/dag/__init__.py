# src/elspeth/core/dag/__init__.py
"""DAG (Directed Acyclic Graph) operations for execution planning.

Package re-exports — preserves the public API of the former dag.py module.
"""

from elspeth.core.dag.graph import ExecutionGraph
from elspeth.core.dag.models import (
    GraphValidationError,
    NodeConfig,
    NodeInfo,
    WiredTransform,
)

__all__ = [
    "ExecutionGraph",
    "GraphValidationError",
    "NodeConfig",
    "NodeInfo",
    "WiredTransform",
]
