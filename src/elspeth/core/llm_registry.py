"""LLM plugin registry using consolidated base framework.

This module provides the LLM registry implementation using the new
BasePluginRegistry framework from Phase 1/2. It replaces the duplicate
LLM registry logic in registry.py.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.plugins import PluginContext
from elspeth.core.protocols import LLMClientProtocol
from elspeth.core.registry.base import BasePluginRegistry
from elspeth.core.registry.schemas import with_security_properties
from elspeth.core.validation_base import ConfigurationError
from elspeth.plugins.nodes.transforms.llm import AzureOpenAIClient, HttpOpenAIClient, MockLLMClient, StaticLLMClient

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
    content = options.get("content")
    if not content:
        raise ConfigurationError(
            "static_test LLM requires explicit 'content' parameter. " "Provide the test response content explicitly in configuration."
        )
    return StaticLLMClient(
        content=content,
        score=options.get("score"),
        metrics=options.get("metrics"),
    )


# ============================================================================
# Schema Definitions
# ============================================================================

_AZURE_OPENAI_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "config": {
                "type": "object",
                "description": "Azure OpenAI configuration containing endpoint, API keys, and optional model parameters",
                "properties": {
                    "azure_endpoint": {"type": "string", "description": "Azure OpenAI service endpoint (required)"},
                    "api_key": {"type": "string", "description": "API key for authentication"},
                    "api_key_env": {"type": "string", "description": "Environment variable name for API key"},
                    "api_version": {"type": "string", "description": "Azure OpenAI API version (required)"},
                    "deployment": {"type": "string", "description": "Azure deployment name"},
                    "deployment_env": {"type": "string", "description": "Environment variable name for deployment"},
                    "temperature": {
                        "type": "number",
                        "description": "Sampling temperature (0-2). Optional - if not provided, uses Azure OpenAI default. Lower values are more deterministic.",
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": "Maximum tokens in response. Optional - if not provided, uses Azure OpenAI default. Set explicit bounds to control costs.",
                    },
                },
            },
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
            "temperature": {
                "type": "number",
                "description": "Sampling temperature (0-2). Optional - if not provided, uses OpenAI API default. Lower values (e.g., 0.2) are more deterministic, higher values (e.g., 1.5) are more creative.",
            },
            "max_tokens": {
                "type": "integer",
                "description": "Maximum tokens in response. Optional - if not provided, uses OpenAI API default (typically model's max context length). Set explicit bounds to control costs and response length.",
            },
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
            "content": {"type": "string", "description": "Static response content to return for all requests"},
            "score": {"type": "number", "description": "Optional score metric"},
            "metrics": {"type": "object", "description": "Optional additional metrics"},
        },
        "required": ["content"],  # Enforce explicit content
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
