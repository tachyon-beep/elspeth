"""
Backward compatibility shim for LLM clients.

DEPRECATED: This module has moved to elspeth.plugins.nodes.transforms.llm
This shim will be removed in a future major version.
"""

import warnings

# Re-export from new location
from elspeth.plugins.nodes.transforms.llm import (
    AzureOpenAIClient,
    HttpOpenAIClient,
    MockLLMClient,
    StaticLLMClient,
)

__all__ = ["AzureOpenAIClient", "MockLLMClient", "HttpOpenAIClient", "StaticLLMClient"]

# Emit deprecation warning on import
warnings.warn(
    "elspeth.plugins.llms is deprecated. "
    "Use elspeth.plugins.nodes.transforms.llm instead. "
    "This compatibility shim will be removed in a future major version.",
    DeprecationWarning,
    stacklevel=2,
)
