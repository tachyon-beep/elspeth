"""Early-stop plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for early-stop plugins that control
experiment termination based on metrics, thresholds, or other conditions. Early-stop
plugins enable efficient experiment execution by halting when conditions are met.

Migrated from plugin_registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from elspeth.core.experiments.plugins import EarlyStopPlugin
from elspeth.core.registry.base import BasePluginRegistry

# Initialize the early-stop plugin registry
early_stop_plugin_registry = BasePluginRegistry[EarlyStopPlugin]("early_stop_plugin")

# No default plugins registered here - all early-stop plugins are registered via
# side-effects when elspeth.plugins.experiments is imported
