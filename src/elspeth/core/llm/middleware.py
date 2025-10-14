"""Middleware primitives for LLM interactions.

DEPRECATED: This module is kept for backward compatibility.
Import from `elspeth.core.protocols` instead.

This compatibility shim will be removed in a future major version.
"""

from __future__ import annotations

import warnings

# Re-export from new consolidated location
from elspeth.core.protocols import LLMMiddleware, LLMRequest

__all__ = ["LLMRequest", "LLMMiddleware"]

# Emit deprecation warning on import
warnings.warn(
    "elspeth.core.llm.middleware is deprecated. "
    "Use elspeth.core.protocols instead. "
    "This compatibility shim will be removed in a future major version.",
    DeprecationWarning,
    stacklevel=2,
)
