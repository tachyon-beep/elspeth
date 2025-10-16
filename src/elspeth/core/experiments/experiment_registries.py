"""Experiment plugin registries for all plugin types.

This module provides centralized registries for experiment plugins:
- Row plugins: Process individual rows during experiment execution
- Aggregation plugins: Summarize experiment results across all rows
- Validation plugins: Check configurations and results against constraints
- Baseline comparison plugins: Compare experiment variants against baselines
- Early-stop plugins: Control experiment termination based on conditions

All registries use BasePluginRegistry framework for consistent behavior,
type safety, and context propagation.

Migrated from individual *_plugin_registry.py files to reduce sprawl.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.registry.base import BasePluginRegistry
from elspeth.plugins.orchestrators.experiment.protocols import (
    AggregationExperimentPlugin,
    BaselineComparisonPlugin,
    EarlyStopPlugin,
    RowExperimentPlugin,
    ValidationPlugin,
)

# Initialize all experiment plugin registries
row_plugin_registry = BasePluginRegistry[RowExperimentPlugin]("row_plugin")
aggregation_plugin_registry = BasePluginRegistry[AggregationExperimentPlugin]("aggregation_plugin")
validation_plugin_registry = BasePluginRegistry[ValidationPlugin]("validation_plugin")
baseline_plugin_registry = BasePluginRegistry[BaselineComparisonPlugin]("baseline_plugin")
early_stop_plugin_registry = BasePluginRegistry[EarlyStopPlugin]("early_stop_plugin")


# Default noop plugin implementations
class _NoopRowPlugin:  # pylint: disable=too-few-public-methods
    """No-op row plugin that returns empty results."""

    name = "noop"

    def process_row(self, _row: dict[str, Any], _responses: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty payload for noop processing."""
        return {}

    def input_schema(self) -> None:  # pragma: no cover - trivial
        """Return None as noop requires no input schema."""
        return None


class _NoopAggPlugin:  # pylint: disable=too-few-public-methods
    """No-op aggregation plugin that returns empty results."""

    name = "noop"

    def finalize(self, _records: list[dict[str, Any]]) -> dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty aggregation result."""
        return {}

    def input_schema(self) -> None:  # pragma: no cover - trivial
        """Return None as noop requires no input schema."""
        return None


class _NoopBaselinePlugin:  # pylint: disable=too-few-public-methods
    """No-op baseline comparison plugin that returns empty results."""

    name = "noop"

    def compare(self, _baseline: dict[str, Any], _variant: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty comparison result."""
        return {}


# Register default noop plugins
row_plugin_registry.register("noop", lambda opts, ctx: _NoopRowPlugin())
aggregation_plugin_registry.register("noop", lambda opts, ctx: _NoopAggPlugin())
baseline_plugin_registry.register("noop", lambda opts, ctx: _NoopBaselinePlugin())

# Note: Validation and early-stop plugins have no default noop implementations
# All concrete plugins are registered via side-effects when elspeth.plugins.experiments is imported

__all__ = [
    "row_plugin_registry",
    "aggregation_plugin_registry",
    "validation_plugin_registry",
    "baseline_plugin_registry",
    "early_stop_plugin_registry",
]
