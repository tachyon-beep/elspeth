"""Rate limiter plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for rate limiter plugins that control
request and token throughput for LLM clients. Rate limiters are optional controls
and do not require security_level or determinism_level validation.

Migrated from controls/registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.controls.rate_limit import (
    AdaptiveRateLimiter,
    FixedWindowRateLimiter,
    NoopRateLimiter,
    RateLimiter,
)
from elspeth.core.plugin_context import PluginContext
from elspeth.core.registries.base import BasePluginRegistry

# Initialize the rate limiter registry
rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")


# Plugin factory functions
def _create_noop_rate_limiter(options: dict[str, Any], context: PluginContext) -> NoopRateLimiter:
    """Create a no-op rate limiter that imposes no restrictions."""
    return NoopRateLimiter()


def _create_fixed_window_rate_limiter(options: dict[str, Any], context: PluginContext) -> FixedWindowRateLimiter:
    """Create a fixed window rate limiter with specified request rate."""
    from elspeth.core.validation_base import ConfigurationError

    if "requests" not in options:
        raise ConfigurationError("requests is required for fixed_window rate limiter")
    if "per_seconds" not in options:
        raise ConfigurationError("per_seconds is required for fixed_window rate limiter")

    return FixedWindowRateLimiter(
        requests=int(options["requests"]),
        per_seconds=float(options["per_seconds"]),
    )


def _create_adaptive_rate_limiter(options: dict[str, Any], context: PluginContext) -> AdaptiveRateLimiter:
    """Create an adaptive rate limiter with request and token limits."""
    from elspeth.core.validation_base import ConfigurationError

    if "requests_per_minute" not in options:
        raise ConfigurationError("requests_per_minute is required for adaptive rate limiter")
    if "interval_seconds" not in options:
        raise ConfigurationError("interval_seconds is required for adaptive rate limiter")

    requests_per_minute = int(options["requests_per_minute"])
    token_value = options.get("tokens_per_minute")
    tokens_per_minute = int(token_value) if token_value is not None else None
    interval_seconds = float(options["interval_seconds"])
    return AdaptiveRateLimiter(
        requests_per_minute=requests_per_minute,
        tokens_per_minute=tokens_per_minute,
        interval_seconds=interval_seconds,
    )


# Plugin schemas
_NOOP_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
}

_FIXED_WINDOW_SCHEMA = {
    "type": "object",
    "properties": {
        "requests": {
            "type": "integer",
            "minimum": 1,
            "description": "Number of requests allowed in the time window (required)",
        },
        "per_seconds": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Time window in seconds (required). Combined with requests, creates 'requests per per_seconds' rate limit.",
        },
    },
    "required": ["requests", "per_seconds"],
    "additionalProperties": True,
}

_ADAPTIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "requests_per_minute": {
            "type": "integer",
            "minimum": 1,
            "description": "Maximum requests allowed per minute (required)",
        },
        "tokens_per_minute": {
            "type": "integer",
            "minimum": 0,
            "description": "Maximum tokens allowed per minute (optional - if not provided, no token-based limiting)",
        },
        "interval_seconds": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Rate limit check interval in seconds (required)",
        },
    },
    "required": ["requests_per_minute", "interval_seconds"],
    "additionalProperties": True,
}

# Register plugins
rate_limiter_registry.register("noop", _create_noop_rate_limiter, schema=_NOOP_SCHEMA)
rate_limiter_registry.register("fixed_window", _create_fixed_window_rate_limiter, schema=_FIXED_WINDOW_SCHEMA)
rate_limiter_registry.register("adaptive", _create_adaptive_rate_limiter, schema=_ADAPTIVE_SCHEMA)
