"""Experiment plugin interfaces.

DEPRECATED: This module is kept for backward compatibility.
Import from `elspeth.plugins.orchestrators.experiment.protocols` instead.

This compatibility shim will be removed in a future major version.
"""

from __future__ import annotations

import warnings

# Re-export from new location
from elspeth.plugins.orchestrators.experiment.protocols import (
    AggregationExperimentPlugin,
    BaselineComparisonPlugin,
    EarlyStopPlugin,
    RowExperimentPlugin,
    ValidationError,
    ValidationPlugin,
)

__all__ = [
    "ValidationError",
    "ValidationPlugin",
    "RowExperimentPlugin",
    "AggregationExperimentPlugin",
    "BaselineComparisonPlugin",
    "EarlyStopPlugin",
]

# Emit deprecation warning on import
warnings.warn(
    "elspeth.core.experiments.plugins is deprecated. "
    "Use elspeth.plugins.orchestrators.experiment.protocols instead. "
    "This compatibility shim will be removed in a future major version.",
    DeprecationWarning,
    stacklevel=2,
)
