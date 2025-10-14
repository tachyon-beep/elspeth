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
from elspeth.core.plugins.context import PluginContext
from elspeth.core.registry.base import BasePluginRegistry

# Initialize the rate limiter registry
rate_limiter_registry = BasePluginRegistry[RateLimiter]("rate_limiter")


# Plugin factory functions
def _create_noop_rate_limiter(options: dict[str, Any], context: PluginContext) -> NoopRateLimiter:
    """Create a no-op rate limiter that imposes no restrictions."""
    return NoopRateLimiter()


def _create_fixed_window_rate_limiter(options: dict[str, Any], context: PluginContext) -> FixedWindowRateLimiter:
    """Create a fixed window rate limiter with specified request rate."""
    return FixedWindowRateLimiter(
        requests=int(options.get("requests", 1)),
        per_seconds=float(options.get("per_seconds", 1.0)),
    )


def _create_adaptive_rate_limiter(options: dict[str, Any], context: PluginContext) -> AdaptiveRateLimiter:
    """Create an adaptive rate limiter with request and token limits."""
    requests_per_minute = int(options.get("requests_per_minute", options.get("requests", 60)) or 60)
    token_value = options.get("tokens_per_minute")
    tokens_per_minute = int(token_value) if token_value is not None else None
    interval_seconds = float(options.get("interval_seconds", 60.0))
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
        "requests": {"type": "integer", "minimum": 1},
        "per_seconds": {"type": "number", "exclusiveMinimum": 0},
    },
    "additionalProperties": True,
}

_ADAPTIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "requests_per_minute": {"type": "integer", "minimum": 1},
        "requests": {"type": "integer", "minimum": 1},
        "tokens_per_minute": {"type": "integer", "minimum": 0},
        "interval_seconds": {"type": "number", "exclusiveMinimum": 0},
    },
    "additionalProperties": True,
}

# Register plugins
rate_limiter_registry.register("noop", _create_noop_rate_limiter, schema=_NOOP_SCHEMA)
rate_limiter_registry.register("fixed_window", _create_fixed_window_rate_limiter, schema=_FIXED_WINDOW_SCHEMA)
rate_limiter_registry.register("adaptive", _create_adaptive_rate_limiter, schema=_ADAPTIVE_SCHEMA)
