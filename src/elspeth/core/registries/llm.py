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
    validate_azure_openai_endpoint,
    validate_http_api_endpoint,
)
from elspeth.core.validation.base import ConfigurationError
from elspeth.plugins.nodes.transforms.llm import AzureOpenAIClient, HttpOpenAIClient, MockLLMClient, StaticLLMClient

from .base import BasePluginRegistry

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

    # ADR-002-B: Reject security_level in configuration (plugin-author-owned)
    if entry_sec is not None or opts_sec is not None:
        raise ConfigurationError(
            f"llm:{plugin_name}: security_level cannot be specified in configuration (ADR-002-B). "
            "Security level is plugin-author-owned and inherited from parent context."
        )

    # ADR-002-B: Also reject allow_downgrade and max_operating_level (immutable security policy)
    entry_allow_downgrade = definition.get("allow_downgrade")
    opts_allow_downgrade = options.get("allow_downgrade")
    entry_max_operating = definition.get("max_operating_level")
    opts_max_operating = options.get("max_operating_level")

    if entry_allow_downgrade is not None or opts_allow_downgrade is not None:
        raise ConfigurationError(
            f"llm:{plugin_name}: allow_downgrade cannot be specified in configuration (ADR-002-B). "
            "Security policy is plugin-author-owned and cannot be overridden."
        )

    if entry_max_operating is not None or opts_max_operating is not None:
        raise ConfigurationError(
            f"llm:{plugin_name}: max_operating_level cannot be specified in configuration (ADR-002-B). "
            "Security policy is plugin-author-owned and cannot be overridden."
        )

    sources = []
    if entry_det is not None:
        sources.append(f"llm:{plugin_name}.definition.determinism_level")
    if opts_det is not None:
        sources.append(f"llm:{plugin_name}.options.determinism_level")
    if provenance:
        sources.extend(provenance)

    # ADR-002-B: Do NOT pass security_level in options (plugin-author-owned)
    # Security level comes from parent_context inheritance
    # Only pass determinism_level if specified (user-configurable)
    if entry_det is not None or opts_det is not None:
        try:
            det_level = coalesce_determinism_level(entry_det, opts_det)
            options["determinism_level"] = det_level
        except ValueError as exc:
            raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc
    elif parent_context.determinism_level is not None:
        options["determinism_level"] = parent_context.determinism_level

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
    """Create Azure OpenAI LLM client with endpoint validation.

    Args:
        options: Configuration options (should include security_level and allow_downgrade).
        context: Plugin context (provides fallback security_level if not in options).

    Returns:
        AzureOpenAIClient instance with security enforcement.

    Note:
        Defaults to allow_downgrade=True if not specified (standard trusted downgrade per ADR-002).
    """
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
            logger.debug("Azure OpenAI endpoint validated: %s", azure_endpoint)
        except ValueError as exc:
            logger.error("Azure OpenAI endpoint validation failed: %s", exc)
            raise ConfigurationError(f"Azure OpenAI endpoint validation failed: {exc}") from exc

    # ADR-002-B: Security level and allow_downgrade are hard-coded in plugin constructor
    # No need to pass them via options - plugin declares its own immutable policy
    return AzureOpenAIClient(**options)


def _create_http_openai(options: dict[str, Any], context: PluginContext) -> HttpOpenAIClient:
    """Create HTTP OpenAI LLM client with endpoint validation.

    Args:
        options: Configuration options (should include security_level and allow_downgrade).
        context: Plugin context (provides fallback security_level if not in options).

    Returns:
        HttpOpenAIClient instance with security enforcement.

    Note:
        Defaults to allow_downgrade=True if not specified (standard trusted downgrade per ADR-002).
    """
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
            logger.debug("HTTP API endpoint validated: %s", api_base)
        except ValueError as exc:
            logger.error("HTTP API endpoint validation failed: %s", exc)
            raise ConfigurationError(f"HTTP API endpoint validation failed: {exc}") from exc

    # ADR-002-B: Security level and allow_downgrade are hard-coded in plugin constructor
    # No need to pass them via options - plugin declares its own immutable policy
    return HttpOpenAIClient(**options)


def _create_mock_llm(options: dict[str, Any], context: PluginContext) -> MockLLMClient:
    """Create mock LLM client with security parameters.

    Args:
        options: Configuration options (should include security_level and allow_downgrade).
        context: Plugin context (provides fallback security_level if not in options).

    Returns:
        MockLLMClient instance with security enforcement.

    Note:
        For test/mock usage, defaults to allow_downgrade=True if not specified.
        This provides standard trusted downgrade behavior (ADR-002).
    """
    # ADR-002-B: Security level and allow_downgrade are hard-coded in plugin constructor
    # No need to pass them via options - plugin declares its own immutable policy
    return MockLLMClient(**options)


def _create_static_llm(options: dict[str, Any], context: PluginContext) -> StaticLLMClient:
    """Create static LLM client.

    Args:
        options: Configuration options (should include security_level, allow_downgrade, and content).
        context: Plugin context (provides fallback security_level if not in options).

    Returns:
        StaticLLMClient instance with security enforcement.

    Note:
        Defaults to allow_downgrade=True if not specified (standard trusted downgrade per ADR-002).
    """
    content = options.get("content")
    if not content:
        raise ConfigurationError(
            "static_test LLM requires explicit 'content' parameter. Provide the test response content explicitly in configuration."
        )

    # ADR-002-B: Security level and allow_downgrade are hard-coded in plugin constructor
    # No need to pass them via options - plugin declares its own immutable policy
    return StaticLLMClient(**options)


# ============================================================================
# Schema Definitions
# ============================================================================

_AZURE_OPENAI_SCHEMA = {
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
        "determinism_level": {"type": "string"},  # Allowed (runtime context, not security policy)
    },
    # Require explicit config block to match factory/client contract.
    # Users must provide configuration explicitly; environment-only setup
    # is not permitted at the registry layer.
    "required": ["config"],
    "additionalProperties": False,  # VULN-004 Layer 1: Reject security policy fields
}

_HTTP_OPENAI_SCHEMA = {
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
        "determinism_level": {"type": "string"},  # Allowed (runtime context, not security policy)
    },
    "required": ["api_base"],
    "additionalProperties": False,  # VULN-004 Layer 1: Reject security policy fields
}

_MOCK_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "seed": {"type": "integer"},
        "determinism_level": {"type": "string"},  # Allowed (runtime context, not security policy)
    },
    "additionalProperties": False,  # VULN-004 Layer 1: Reject security policy fields
}

_STATIC_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "Static response content to return for all requests"},
        "score": {"type": "number", "description": "Optional score metric"},
        "metrics": {"type": "object", "description": "Optional additional metrics"},
        "determinism_level": {"type": "string"},  # Allowed (runtime context, not security policy)
    },
    "required": ["content"],  # Enforce explicit content
    "additionalProperties": False,  # VULN-004 Layer 1: Reject security policy fields
}


# ============================================================================
# Register LLMs
# ============================================================================

llm_registry.register(
    "azure_openai",
    _create_azure_openai,
    schema=_AZURE_OPENAI_SCHEMA,
    declared_security_level="PROTECTED",  # ADR-002-B: Enterprise Azure OpenAI, maximum clearance
)

llm_registry.register(
    "http_openai",
    _create_http_openai,
    schema=_HTTP_OPENAI_SCHEMA,
    declared_security_level="OFFICIAL",  # ADR-002-B: Public HTTP OpenAI (per plugin implementation)
)

llm_registry.register(
    "mock",
    _create_mock_llm,
    schema=_MOCK_LLM_SCHEMA,
    declared_security_level="UNOFFICIAL",  # ADR-002-B: Test-only transform
)

llm_registry.register(
    "static_test",
    _create_static_llm,
    schema=_STATIC_LLM_SCHEMA,
    declared_security_level="UNOFFICIAL",  # ADR-002-B: Test-only transform
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
