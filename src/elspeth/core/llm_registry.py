"""LLM plugin registry using consolidated base framework.

This module provides the LLM registry implementation using the new
BasePluginRegistry framework from Phase 1/2. It replaces the duplicate
LLM registry logic in registry.py.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.interfaces import LLMClientProtocol
from elspeth.core.plugins import PluginContext
from elspeth.core.registry.base import BasePluginRegistry
from elspeth.core.registry.schemas import with_security_properties
from elspeth.plugins.llms import AzureOpenAIClient, HttpOpenAIClient, MockLLMClient, StaticLLMClient

# Create the LLM registry with type safety
llm_registry = BasePluginRegistry[LLMClientProtocol]("llm")


# ============================================================================
# LLM Factory Functions
# ============================================================================


def _create_azure_openai(options: dict[str, Any], context: PluginContext) -> AzureOpenAIClient:
    """Create Azure OpenAI LLM client."""
    return AzureOpenAIClient(**options)


def _create_http_openai(options: dict[str, Any], context: PluginContext) -> HttpOpenAIClient:
    """Create HTTP OpenAI LLM client."""
    return HttpOpenAIClient(**options)


def _create_mock_llm(options: dict[str, Any], context: PluginContext) -> MockLLMClient:
    """Create mock LLM client."""
    return MockLLMClient(**options)


def _create_static_llm(options: dict[str, Any], context: PluginContext) -> StaticLLMClient:
    """Create static LLM client."""
    return StaticLLMClient(
        content=options.get("content", "STATIC RESPONSE"),
        score=options.get("score", 0.5),
        metrics=options.get("metrics"),
    )


# ============================================================================
# Schema Definitions
# ============================================================================

_AZURE_OPENAI_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "config": {"type": "object"},
            "deployment": {"type": "string"},
            "client": {},
        },
        "required": ["config"],
        "additionalProperties": True,
    },
    require_security=False,  # Will be enforced by registry
    require_determinism=False,
)

_HTTP_OPENAI_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "api_base": {"type": "string"},
            "api_key": {"type": "string"},
            "api_key_env": {"type": "string"},
            "model": {"type": "string"},
            "temperature": {"type": "number"},
            "max_tokens": {"type": "integer"},
            "timeout": {"type": "number", "exclusiveMinimum": 0},
        },
        "required": ["api_base"],
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)

_MOCK_LLM_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "seed": {"type": "integer"},
        },
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)

_STATIC_LLM_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "score": {"type": "number"},
            "metrics": {"type": "object"},
        },
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)


# ============================================================================
# Register LLMs
# ============================================================================

llm_registry.register(
    "azure_openai",
    _create_azure_openai,
    schema=_AZURE_OPENAI_SCHEMA,
)

llm_registry.register(
    "http_openai",
    _create_http_openai,
    schema=_HTTP_OPENAI_SCHEMA,
)

llm_registry.register(
    "mock",
    _create_mock_llm,
    schema=_MOCK_LLM_SCHEMA,
)

llm_registry.register(
    "static_test",
    _create_static_llm,
    schema=_STATIC_LLM_SCHEMA,
)


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "llm_registry",
]
