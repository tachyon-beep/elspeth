"""Row-level experiment plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for row-level experiment plugins that
process individual rows during experiment execution. Row plugins transform input
data and LLM responses into metric values or derived features.

Migrated from plugin_registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from typing import Any

from elspeth.plugins.orchestrators.experiment.protocols import RowExperimentPlugin
from elspeth.core.registry.base import BasePluginRegistry

# Initialize the row plugin registry
row_plugin_registry = BasePluginRegistry[RowExperimentPlugin]("row_plugin")


# Noop plugin implementation
class _NoopRowPlugin:  # pylint: disable=too-few-public-methods
    """No-op row plugin that returns empty results."""

    name = "noop"

    def process_row(self, _row: dict[str, Any], _responses: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - trivial
        """Return an empty payload for noop processing."""
        return {}

    def input_schema(self):
        """Noop plugin does not require specific input columns."""
        return None


# Register noop plugin
row_plugin_registry.register(
    "noop",
    lambda options, context: _NoopRowPlugin(),
    schema={"type": "object", "additionalProperties": True},
)
