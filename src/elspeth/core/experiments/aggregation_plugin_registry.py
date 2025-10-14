"""Aggregation experiment plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for aggregation experiment plugins that
summarize results across all rows in an experiment. Aggregation plugins produce
suite-level metrics and insights from experiment results.

Migrated from plugin_registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.experiments.plugins import AggregationExperimentPlugin
from elspeth.core.registry.base import BasePluginRegistry

# Initialize the aggregation plugin registry
aggregation_plugin_registry = BasePluginRegistry[AggregationExperimentPlugin]("aggregation_plugin")


# Noop plugin implementation
class _NoopAggPlugin:  # pylint: disable=too-few-public-methods
    """No-op aggregation plugin that returns empty results."""

    name = "noop"

    def finalize(self, _records: list[dict[str, Any]]) -> dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty aggregation result."""
        return {}

    def input_schema(self):
        """Noop plugin does not require specific input columns."""
        return None


# Register noop plugin
aggregation_plugin_registry.register(
    "noop",
    lambda options, context: _NoopAggPlugin(),
    schema={"type": "object", "additionalProperties": True},
)
