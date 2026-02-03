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
from elspeth.engine.orchestrator_legacy import Orchestrator
