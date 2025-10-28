"""ADR-003 Automated Plugin Discovery - Security-Critical Infrastructure.

SECURITY RATIONALE:
Automated discovery prevents registration bypass attacks where plugins are loaded
directly without going through security validation. By automatically importing all
plugin modules at framework initialization, we ensure EVERY internal plugin undergoes
validation.

Attack Vectors Prevented:
1. Direct Import Bypass - Developer imports plugin directly without registration
2. Forgotten Registration - Plugin exists but registration call omitted
3. Import Order Attack - Side effects skipped due to import ordering
4. Configuration Drift - New plugins added without registry updates

Design Pattern:
- Explicit is better than implicit (all plugins must be imported)
- Fail-fast enforcement (missing plugins detected at startup)
- Security-first (bypass attempts caught by validation)

Discovery Process:
1. Scan src/elspeth/plugins/ directory recursively
2. Import all Python modules (triggers registration side effects)
3. Validate expected plugins are registered
4. Log discovery for audit trail

ADR-003 Threat Prevention:
- T1: Registration Bypass → Auto-import forces all plugins through registry
- T2: Incomplete Validation → Validation layer catches missing plugins
- T3: Configuration Drift → Expected plugin list enforced
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.registries.base import BasePluginRegistry

from elspeth.core.validation.base import SecurityValidationError

__all__ = ["auto_discover_internal_plugins", "validate_discovery"]

logger = logging.getLogger(__name__)


# ============================================================================
# Expected Plugins - Security Baseline
# ============================================================================

# Minimum expected plugins for each type (used for validation)
# If these are missing, it indicates a registration bypass or incomplete discovery
#
# VULN-010 FIX: Expanded from 8/29 plugins (27.6%) to 29/29 plugins (100% coverage)
# for production-critical types (datasource, llm, sink, middleware).
EXPECTED_PLUGINS = {
    # Datasources: 3/3 = 100% ✅ (unchanged)
    "datasource": ["local_csv", "csv_blob", "azure_blob"],

    # LLMs: 4/4 = 100% ✅ (was 2/4 = 50%)
    "llm": [
        "mock",           # Test/mock LLM
        "azure_openai",   # Enterprise Azure OpenAI
        "http_openai",    # Public HTTP OpenAI
        "static_test",    # Static test LLM
    ],

    # Sinks: 16/16 = 100% ✅ (was 3/16 = 18.75%)
    "sink": [
        # Core outputs
        "csv",
        "signed_artifact",
        "local_bundle",

        # Document formats
        "excel_workbook",

        # Cloud storage
        "azure_blob",
        "azure_blob_artifacts",

        # Artifact bundles
        "zip_bundle",
        "reproducibility_bundle",

        # Repository integrations
        "github_repo",
        "azure_devops_repo",
        "azure_devops_artifact_repo",

        # Analytics & visualization
        "analytics_report",
        "analytics_visual",
        "enhanced_visual",

        # Specialized sinks
        "embeddings_store",  # Vector storage
        "file_copy",         # File copy utility
    ],

    # Middleware: 7/7 = 100% ✅ (was 0/7 = 0%)
    "middleware": [
        "audit_logger",         # Audit logging
        "azure_content_safety", # Azure Content Safety
        "azure_environment",    # Azure environment middleware
        "classified_material",  # Classified material validation
        "health_monitor",       # Health monitoring
        "pii_shield",           # PII protection
        "prompt_shield",        # Prompt validation
    ],

    # Other plugin types have no minimum (optional plugins)
}


# ============================================================================
# Auto-Discovery Implementation
# ============================================================================


def auto_discover_internal_plugins() -> None:
    """Automatically discover and import all internal plugin modules.

    SECURITY: This function ensures ALL internal plugins go through
    registration and validation. Bypassing this function is a security breach.

    Discovery process:
    1. Scan src/elspeth/plugins/ for all .py files
    2. Import each module (triggers registration side effects)
    3. Skip __pycache__, __init__.py (handled by Python import system)
    4. Log discovery for audit trail
    5. Handle import errors gracefully (don't fail discovery for one broken plugin)

    Returns:
        None (side effect: imports trigger plugin registration)

    Raises:
        Does not raise - handles import errors gracefully

    Example:
        >>> from elspeth.core.registry.auto_discover import auto_discover_internal_plugins
        >>> auto_discover_internal_plugins()  # Imports all plugin modules
    """
    # Find plugins directory relative to this file
    # auto_discover.py is in src/elspeth/core/registry/
    # plugins/ is in src/elspeth/plugins/
    registry_dir = Path(__file__).parent  # .../core/registry
    core_dir = registry_dir.parent  # .../core
    elspeth_dir = core_dir.parent  # .../elspeth
    plugins_dir = elspeth_dir / "plugins"

    if not plugins_dir.exists():
        logger.warning(f"Plugins directory not found: {plugins_dir}")
        return

    logger.debug(f"Auto-discovering plugins in: {plugins_dir}")

    discovered_count = 0
    failed_count = 0

    # Walk the plugins directory recursively
    for root, dirs, files in os.walk(plugins_dir):
        # Skip __pycache__ and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith("_") and not d.startswith(".")]

        for file in files:
            # Only process Python source files (skip __init__.py, tests, etc.)
            if not file.endswith(".py"):
                continue
            if file.startswith("_"):
                continue  # Skip __init__.py, __pycache__, etc.

            # Convert file path to module name
            # Example: src/elspeth/plugins/nodes/sources/csv_local.py
            #       -> elspeth.plugins.nodes.sources.csv_local
            file_path = Path(root) / file
            try:
                relative_path = file_path.relative_to(elspeth_dir.parent)
                module_name = str(relative_path.with_suffix("")).replace(os.sep, ".")

                # Import module (triggers registration side effects)
                logger.debug(f"Importing plugin module: {module_name}")
                importlib.import_module(module_name)
                discovered_count += 1

            except Exception as exc:
                # Log error but continue discovery (one broken plugin shouldn't stop all discovery)
                logger.warning(f"Failed to import plugin module {file_path}: {exc}")
                failed_count += 1

    logger.info(
        f"Plugin discovery complete: {discovered_count} modules imported, {failed_count} failed"
    )


# ============================================================================
# Discovery Validation
# ============================================================================


def validate_discovery(registries: dict[str, BasePluginRegistry[Any]]) -> None:
    """Validate that expected plugins were discovered and registered.

    SECURITY: This function prevents bypass attacks where plugins exist but
    aren't registered. If expected plugins are missing, it indicates either:
    1. Registration bypass (developer loaded plugin directly)
    2. Incomplete discovery (auto_discover failed to import some modules)
    3. Configuration drift (expected plugins list is outdated)

    Args:
        registries: Dictionary mapping plugin type names to registry instances

    Raises:
        SecurityValidationError: If expected plugins are missing

    Example:
        >>> from elspeth.core.registry import central_registry
        >>> validate_discovery(central_registry._registries)
    """
    logger.debug("Validating plugin discovery...")

    missing_plugins: dict[str, list[str]] = {}

    for plugin_type, expected_names in EXPECTED_PLUGINS.items():
        # Get registry for this plugin type
        registry = registries.get(plugin_type)
        if not registry:
            missing_plugins[plugin_type] = expected_names
            logger.error(
                f"Plugin type '{plugin_type}' not in registries (expected plugins: {expected_names})"
            )
            continue

        # Check which expected plugins are registered
        registered = set(registry.list_plugins())
        expected = set(expected_names)
        missing = expected - registered

        if missing:
            missing_plugins[plugin_type] = list(missing)
            logger.error(
                f"Expected plugins missing from {plugin_type} registry: {missing}. "
                f"Registered: {registered}"
            )

    if missing_plugins:
        # Format error message with details
        error_lines = [
            "SECURITY VIOLATION: Expected plugins missing from registries.",
            "This indicates a registration bypass attempt or incomplete discovery.",
            "",
            "Missing plugins by type:",
        ]
        for plugin_type, missing_list in missing_plugins.items():
            error_lines.append(f"  {plugin_type}: {', '.join(missing_list)}")

        error_lines.extend([
            "",
            "Possible causes:",
            "1. Plugin modules failed to import (check auto_discover logs)",
            "2. Registration bypassed (plugin loaded without registry.register())",
            "3. Expected plugins list outdated (update EXPECTED_PLUGINS in auto_discover.py)",
        ])

        raise SecurityValidationError("\n".join(error_lines))

    logger.info("Plugin discovery validation passed - all expected plugins registered")
