"""LLM plugin registry using consolidated base framework.

This module provides the LLM registry implementation using the new
BasePluginRegistry framework from Phase 1/2. It replaces the duplicate
LLM registry logic in registry.py.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import LLMClientProtocol
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
    validate_azure_openai_endpoint,
    validate_http_api_endpoint,
)
from elspeth.core.validation.base import ConfigurationError
from elspeth.plugins.nodes.transforms.llm import AzureOpenAIClient, HttpOpenAIClient, MockLLMClient, StaticLLMClient

from .base import BasePluginRegistry
from .schemas import with_security_properties

logger = logging.getLogger(__name__)

# Create the LLM registry with type safety
llm_registry = BasePluginRegistry[LLMClientProtocol]("llm")


def create_llm_from_definition(
    definition: Mapping[str, Any],
    *,
    parent_context: Any,
    provenance: Iterable[str] | None = None,
) -> LLMClientProtocol:
    """Create an LLM instance from a configuration definition.

    This helper mirrors the legacy ``registry.create_llm_from_definition`` API.
    It merges security and determinism levels from the incoming definition,
    falling back to the parent context when values are omitted.
    """

    if not isinstance(definition, Mapping):
        raise ValueError("LLM definition must be a mapping")

    plugin_name = definition.get("plugin")
    if not plugin_name:
        raise ConfigurationError("LLM definition requires 'plugin'")

    options = dict(definition.get("options", {}) or {})

    entry_sec = definition.get("security_level")
    opts_sec = options.get("security_level")
    entry_det = definition.get("determinism_level")
    opts_det = options.get("determinism_level")

    sources = []
    if entry_sec:
        sources.append(f"llm:{plugin_name}.definition.security_level")
    if opts_sec:
        sources.append(f"llm:{plugin_name}.options.security_level")
    if entry_det is not None:
        sources.append(f"llm:{plugin_name}.definition.determinism_level")
    if opts_det is not None:
        sources.append(f"llm:{plugin_name}.options.determinism_level")
    if provenance:
        sources.extend(provenance)

    try:
        sec_level = coalesce_security_level(parent_context.security_level, entry_sec, opts_sec)
    except ValueError as exc:
        raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc

    if entry_det is not None or opts_det is not None:
        try:
            det_level = coalesce_determinism_level(entry_det, opts_det)
        except ValueError as exc:
            raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc
    else:
        det_level = parent_context.determinism_level

    options["security_level"] = sec_level
    options["determinism_level"] = det_level

    return llm_registry.create(
        plugin_name,
        options,
        provenance=tuple(sources or (f"llm:{plugin_name}.resolved",)),
        parent_context=parent_context,
    )


# ============================================================================
# LLM Factory Functions
# ============================================================================


def _create_azure_openai(options: dict[str, Any], context: PluginContext) -> AzureOpenAIClient:
    """Create Azure OpenAI LLM client with endpoint validation."""
    # Extract azure_endpoint from config for validation
    config = options.get("config", {})
    azure_endpoint = config.get("azure_endpoint")

    if azure_endpoint:
        # Validate endpoint against approved patterns
        # Use security_level from context if available
        security_level = context.security_level if context else None
        try:
            validate_azure_openai_endpoint(
                endpoint=azure_endpoint,
                security_level=security_level,
            )
            logger.debug(f"Azure OpenAI endpoint validated: {azure_endpoint}")
        except ValueError as exc:
            logger.error(f"Azure OpenAI endpoint validation failed: {exc}")
            raise ConfigurationError(f"Azure OpenAI endpoint validation failed: {exc}") from exc

    return AzureOpenAIClient(**options)


def _create_http_openai(options: dict[str, Any], context: PluginContext) -> HttpOpenAIClient:
    """Create HTTP OpenAI LLM client with endpoint validation."""
    # Extract api_base for validation
    api_base = options.get("api_base")

    if api_base:
        # Validate endpoint against approved patterns
        # Use security_level from context if available
        security_level = context.security_level if context else None
        try:
            validate_http_api_endpoint(
                endpoint=api_base,
                security_level=security_level,
            )
            logger.debug(f"HTTP API endpoint validated: {api_base}")
        except ValueError as exc:
            logger.error(f"HTTP API endpoint validation failed: {exc}")
            raise ConfigurationError(f"HTTP API endpoint validation failed: {exc}") from exc

    return HttpOpenAIClient(**options)


def _create_mock_llm(options: dict[str, Any], context: PluginContext) -> MockLLMClient:
    """Create mock LLM client."""
    return MockLLMClient(**options)


def _create_static_llm(options: dict[str, Any], context: PluginContext) -> StaticLLMClient:
    """Create static LLM client."""
    content = options.get("content")
    if not content:
        raise ConfigurationError(
            "static_test LLM requires explicit 'content' parameter. Provide the test response content explicitly in configuration."
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
                        "description": (
                            "Sampling temperature (0-2). Optional - if not provided, uses Azure OpenAI default. "
                            "Lower values are more deterministic."
                        ),
                    },
                    "max_tokens": {
                        "type": "integer",
                        "description": (
                            "Maximum tokens in response. Optional - if not provided, uses Azure OpenAI default. "
                            "Set explicit bounds to control costs."
                        ),
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
                "description": (
                    "Sampling temperature (0-2). Optional - if not provided, uses OpenAI API default. "
                    "Lower values (e.g., 0.2) are more deterministic, higher values (e.g., 1.5) are more creative."
                ),
            },
            "max_tokens": {
                "type": "integer",
                "description": (
                    "Maximum tokens in response. Optional - if not provided, uses OpenAI API default "
                    "(typically model's max context length). Set explicit bounds to control costs and response length."
                ),
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
    "create_llm_from_definition",
    "_create_azure_openai",
    "_create_http_openai",
    "_create_mock_llm",
    "_create_static_llm",
]
