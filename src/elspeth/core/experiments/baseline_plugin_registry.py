"""Baseline comparison plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for baseline comparison plugins that
compare baseline and variant experiment results. Baseline plugins enable A/B testing
and comparative analysis of different experiment configurations.

Migrated from plugin_registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from typing import Any

from elspeth.plugins.orchestrators.experiment.protocols import BaselineComparisonPlugin
from elspeth.core.registry.base import BasePluginRegistry

# Initialize the baseline plugin registry
baseline_plugin_registry = BasePluginRegistry[BaselineComparisonPlugin]("baseline_plugin")


# Noop plugin implementation
class _NoopBaselinePlugin:  # pylint: disable=too-few-public-methods
    """No-op baseline plugin that returns empty results."""

    name = "noop"

    def compare(self, _baseline: dict[str, Any], _variant: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty comparison result."""
        return {}


# Row count baseline plugin implementation
class _RowCountBaselinePlugin:  # pylint: disable=too-few-public-methods
    """Baseline plugin that compares result counts."""

    def __init__(self, key: str = "row_delta"):
        self.name = "row_count"
        self._key = key

    def compare(self, baseline: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
        """Return the delta in result counts between baseline and variant."""
        base_count = len(baseline.get("results", [])) if baseline else 0
        variant_count = len(variant.get("results", [])) if variant else 0
        return {self._key: variant_count - base_count}


# Register default plugins
baseline_plugin_registry.register(
    "noop",
    lambda options, context: _NoopBaselinePlugin(),
    schema={"type": "object", "additionalProperties": True},
)

baseline_plugin_registry.register(
    "row_count",
    lambda options, context: _RowCountBaselinePlugin(options.get("key", "row_delta")),
    schema={
        "type": "object",
        "properties": {"key": {"type": "string"}},
        "additionalProperties": True,
    },
)
