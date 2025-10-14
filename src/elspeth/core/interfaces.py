"""Interfaces defining key plugin contracts.

DEPRECATED: This module is kept for backward compatibility.
Import from `elspeth.core.protocols` instead.

This compatibility shim will be removed in a future major version.
"""

from __future__ import annotations

import warnings

# Re-export all protocols from new consolidated location
from elspeth.core.protocols import (
    Artifact,
    ArtifactDescriptor,
    DataSource,
    ExperimentContext,
    LLMClientProtocol,
    OrchestratorPlugin,
    ResultSink,
)

__all__ = [
    "DataSource",
    "LLMClientProtocol",
    "ResultSink",
    "OrchestratorPlugin",
    "ExperimentContext",
    "ArtifactDescriptor",
    "Artifact",
]

# Emit deprecation warning on import (but only once)
warnings.warn(
    "elspeth.core.interfaces is deprecated. "
    "Use elspeth.core.protocols instead. "
    "This compatibility shim will be removed in a future major version.",
    DeprecationWarning,
    stacklevel=2,
)
