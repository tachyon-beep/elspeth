"""Cost tracker plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for cost tracker plugins that monitor
token usage and estimate costs for LLM requests. Cost trackers are optional controls
and do not require security_level or determinism_level validation.

Migrated from controls/registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.controls.cost_tracker import CostTracker, FixedPriceCostTracker, NoopCostTracker
from elspeth.core.registries.base import BasePluginRegistry
from elspeth.core.validation.base import ConfigurationError

# Initialize the cost tracker registry
cost_tracker_registry = BasePluginRegistry[CostTracker]("cost_tracker")


# Plugin factory functions
def _create_noop_cost_tracker(options: dict[str, Any], context: PluginContext) -> NoopCostTracker:
    """Create a no-op cost tracker that performs no tracking."""
    return NoopCostTracker()


def _create_fixed_price_cost_tracker(options: dict[str, Any], context: PluginContext) -> FixedPriceCostTracker:
    """Create a fixed-price cost tracker with specified token prices."""
    if "prompt_token_price" not in options:
        raise ConfigurationError("prompt_token_price is required for fixed_price cost tracker")
    if "completion_token_price" not in options:
        raise ConfigurationError("completion_token_price is required for fixed_price cost tracker")

    return FixedPriceCostTracker(
        prompt_token_price=float(options["prompt_token_price"]),
        completion_token_price=float(options["completion_token_price"]),
    )


# Plugin schemas
_NOOP_SCHEMA = {
    "type": "object",
    "additionalProperties": True,
}

_FIXED_PRICE_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt_token_price": {
            "type": "number",
            "minimum": 0,
            "description": "Cost per prompt token in USD (required)",
        },
        "completion_token_price": {
            "type": "number",
            "minimum": 0,
            "description": "Cost per completion token in USD (required)",
        },
    },
    "required": ["prompt_token_price", "completion_token_price"],
    "additionalProperties": True,
}

# Register plugins
cost_tracker_registry.register("noop", _create_noop_cost_tracker, schema=_NOOP_SCHEMA)
cost_tracker_registry.register("fixed_price", _create_fixed_price_cost_tracker, schema=_FIXED_PRICE_SCHEMA)
