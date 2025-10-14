"""Validation experiment plugin registry using BasePluginRegistry framework.

This module provides a centralized registry for validation plugins that check
experiment configurations and results against constraints and requirements.
Validation plugins ensure data quality and experimental integrity.

Migrated from plugin_registry.py as part of Phase 2 registry consolidation.
"""

from __future__ import annotations

from elspeth.core.experiments.plugins import ValidationPlugin
from elspeth.core.registry.base import BasePluginRegistry

# Initialize the validation plugin registry
validation_plugin_registry = BasePluginRegistry[ValidationPlugin]("validation_plugin")

# No default plugins registered - all validation plugins are registered via
# side-effects when elspeth.plugins.experiments is imported
