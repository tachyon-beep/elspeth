"""ADR-003 CentralPluginRegistry - Unified Registry Interface.

SECURITY RATIONALE:
CentralPluginRegistry provides a single enforcement point for all plugin operations,
ensuring every plugin registration goes through security validation. It wraps all
type-specific registries and automatically invokes auto-discovery at initialization.

Security Architecture:
1. Single entry point for all plugin operations (unified interface)
2. Automatic discovery at initialization (forces registration)
3. Validation layer after discovery (catches bypasses)
4. Type-safe plugin retrieval (prevents type confusion)

Design Pattern:
- Facade pattern: Unified interface over type-specific registries
- Initialization guarantees: Auto-discover + validation on construction
- Defense-in-depth: Multiple security layers (discovery + validation + registration)

ADR-003 Threat Prevention:
- T1: Registration Bypass → Auto-discovery forces all plugins through registry
- T2: Incomplete Validation → Validation layer catches missing plugins
- T3: Initialization Bypass → Discovery runs automatically on construction
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from elspeth.core.registries.base import BasePluginRegistry

from .auto_discover import auto_discover_internal_plugins, validate_discovery

__all__ = ["CentralPluginRegistry", "central_registry"]

logger = logging.getLogger(__name__)


class CentralPluginRegistry:
    """Central plugin registry providing unified interface over type-specific registries.

    This class wraps all type-specific plugin registries (datasource, llm, sink, etc.)
    and provides a unified interface for plugin operations. It automatically invokes
    plugin discovery and validation at initialization.

    Security Features:
    - Automatic plugin discovery at initialization (no manual registration needed)
    - Validation layer verifies expected plugins are registered
    - Single enforcement point for all plugin operations
    - Type-safe plugin retrieval

    Example:
        >>> from elspeth.core.registry import central_registry
        >>> # Auto-discovery already ran during central_registry initialization
        >>> datasource = central_registry.get_plugin("datasource", "local_csv")
        >>> llm = central_registry.get_llm("azure_openai")  # Convenience method
        >>> all_plugins = central_registry.list_all_plugins()
    """

    def __init__(
        self,
        *,
        datasource_registry: BasePluginRegistry[Any] | None = None,
        llm_registry: BasePluginRegistry[Any] | None = None,
        sink_registry: BasePluginRegistry[Any] | None = None,
        middleware_registry: BasePluginRegistry[Any] | None = None,
        row_plugin_registry: BasePluginRegistry[Any] | None = None,
        aggregation_plugin_registry: BasePluginRegistry[Any] | None = None,
        validation_plugin_registry: BasePluginRegistry[Any] | None = None,
        baseline_plugin_registry: BasePluginRegistry[Any] | None = None,
        early_stop_plugin_registry: BasePluginRegistry[Any] | None = None,
        cost_tracker_registry: BasePluginRegistry[Any] | None = None,
        rate_limiter_registry: BasePluginRegistry[Any] | None = None,
        utility_plugin_registry: BasePluginRegistry[Any] | None = None,
    ):
        """Initialize central registry with type-specific registry instances.

        Args:
            datasource_registry: Registry for datasource plugins
            llm_registry: Registry for LLM plugins
            sink_registry: Registry for sink plugins
            middleware_registry: Registry for middleware plugins
            row_plugin_registry: Registry for row experiment plugins
            aggregation_plugin_registry: Registry for aggregation plugins
            validation_plugin_registry: Registry for validation plugins
            baseline_plugin_registry: Registry for baseline comparison plugins
            early_stop_plugin_registry: Registry for early stop plugins
            cost_tracker_registry: Registry for cost tracker plugins
            rate_limiter_registry: Registry for rate limiter plugins
            utility_plugin_registry: Registry for utility plugins

        Security:
            - Calls auto_discover_internal_plugins() to force registration
            - Calls validate_discovery() to verify expected plugins present
        """
        logger.info("Initializing CentralPluginRegistry")

        # Store type-specific registries
        self._registries: dict[str, BasePluginRegistry[Any]] = {}

        # Register core plugin types
        if datasource_registry:
            self._registries["datasource"] = datasource_registry
        if llm_registry:
            self._registries["llm"] = llm_registry
        if sink_registry:
            self._registries["sink"] = sink_registry
        if middleware_registry:
            self._registries["middleware"] = middleware_registry

        # Register experiment plugin types
        if row_plugin_registry:
            self._registries["row_plugin"] = row_plugin_registry
        if aggregation_plugin_registry:
            self._registries["aggregation_plugin"] = aggregation_plugin_registry
        if validation_plugin_registry:
            self._registries["validation_plugin"] = validation_plugin_registry
        if baseline_plugin_registry:
            self._registries["baseline_plugin"] = baseline_plugin_registry
        if early_stop_plugin_registry:
            self._registries["early_stop_plugin"] = early_stop_plugin_registry

        # Register control plugin types
        if cost_tracker_registry:
            self._registries["cost_tracker"] = cost_tracker_registry
        if rate_limiter_registry:
            self._registries["rate_limiter"] = rate_limiter_registry

        # Register utility plugin types
        if utility_plugin_registry:
            self._registries["utility"] = utility_plugin_registry

        logger.debug(f"Registered {len(self._registries)} plugin types: {list(self._registries.keys())}")

        # SECURITY: Auto-discover all internal plugins
        logger.info("Running auto-discovery for internal plugins")
        auto_discover_internal_plugins()

        # SECURITY: Validate that expected plugins are registered
        logger.info("Validating plugin discovery")
        validate_discovery(self._registries)

        logger.info("CentralPluginRegistry initialization complete")

    def create_plugin(
        self,
        plugin_type: str,
        plugin_name: str,
        options: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        """Create a plugin instance by type and name.

        Unified interface for creating plugins across all types.

        Args:
            plugin_type: Plugin type (e.g., "datasource", "llm", "sink")
            plugin_name: Plugin name (e.g., "local_csv", "azure_openai")
            options: Plugin configuration options
            **kwargs: Additional arguments passed to registry.create()

        Returns:
            Plugin instance

        Raises:
            KeyError: If plugin_type is unknown
            Exception: If plugin_name not found (depends on registry implementation)

        Example:
            >>> datasource = central_registry.create_plugin("datasource", "local_csv", options={...})
        """
        if plugin_type not in self._registries:
            raise KeyError(
                f"Unknown plugin type: {plugin_type}. "
                f"Available types: {', '.join(sorted(self._registries.keys()))}"
            )

        registry = self._registries[plugin_type]
        return registry.create(plugin_name, options, **kwargs)

    def get_registry(self, plugin_type: str) -> BasePluginRegistry[Any]:
        """Get the underlying registry for a plugin type.

        This is useful when you need direct access to the registry (e.g., for passing
        factory functions around).

        Args:
            plugin_type: Plugin type (e.g., "datasource", "llm", "sink")

        Returns:
            The underlying BasePluginRegistry instance

        Raises:
            KeyError: If plugin_type is unknown

        Example:
            >>> datasource_registry = central_registry.get_registry("datasource")
            >>> datasource = datasource_registry.create("local_csv", options={...})
        """
        if plugin_type not in self._registries:
            raise KeyError(
                f"Unknown plugin type: {plugin_type}. "
                f"Available types: {', '.join(sorted(self._registries.keys()))}"
            )

        return self._registries[plugin_type]

    def list_plugins(self, plugin_type: str) -> list[str]:
        """List all registered plugin names for a specific type.

        Args:
            plugin_type: Plugin type (e.g., "datasource", "llm", "sink")

        Returns:
            List of plugin names registered for this type

        Raises:
            KeyError: If plugin_type is unknown

        Example:
            >>> datasources = central_registry.list_plugins("datasource")
            ['local_csv', 'csv_blob', 'azure_blob']
        """
        if plugin_type not in self._registries:
            raise KeyError(
                f"Unknown plugin type: {plugin_type}. "
                f"Available types: {', '.join(sorted(self._registries.keys()))}"
            )

        registry = self._registries[plugin_type]
        return registry.list_plugins()

    def list_all_plugins(self) -> dict[str, list[str]]:
        """List all registered plugins across all types.

        Convenience method for discovering all available plugins.

        Returns:
            Dict mapping plugin type -> list of plugin names

        Example:
            >>> all_plugins = central_registry.list_all_plugins()
            {
                'datasource': ['local_csv', 'csv_blob', 'azure_blob'],
                'llm': ['mock', 'azure_openai', 'openai_http'],
                'sink': ['csv', 'json', 'markdown', ...]
            }
        """
        return {plugin_type: registry.list_plugins() for plugin_type, registry in self._registries.items()}

    # ============================================================================
    # Convenience Methods
    # ============================================================================

    def create_datasource(self, name: str, options: dict[str, Any], **kwargs: Any) -> Any:
        """Convenience method: create datasource plugin.

        Shorthand for create_plugin("datasource", name, options).

        Args:
            name: Datasource plugin name (e.g., "local_csv")
            options: Plugin configuration options
            **kwargs: Additional arguments passed to registry

        Returns:
            Datasource plugin instance
        """
        return self.create_plugin("datasource", name, options, **kwargs)

    def create_llm(self, name: str, options: dict[str, Any], **kwargs: Any) -> Any:
        """Convenience method: create LLM plugin.

        Shorthand for create_plugin("llm", name, options).

        Args:
            name: LLM plugin name (e.g., "azure_openai")
            options: Plugin configuration options
            **kwargs: Additional arguments passed to registry

        Returns:
            LLM plugin instance
        """
        return self.create_plugin("llm", name, options, **kwargs)

    def create_sink(self, name: str, options: dict[str, Any], **kwargs: Any) -> Any:
        """Convenience method: create sink plugin.

        Shorthand for create_plugin("sink", name, options).

        Args:
            name: Sink plugin name (e.g., "csv")
            options: Plugin configuration options
            **kwargs: Additional arguments passed to registry

        Returns:
            Sink plugin instance
        """
        return self.create_plugin("sink", name, options, **kwargs)

    def create_middleware(self, name: str, options: dict[str, Any], **kwargs: Any) -> Any:
        """Convenience method: create middleware plugin.

        Shorthand for create_plugin("middleware", name, options).

        Args:
            name: Middleware plugin name
            options: Plugin configuration options
            **kwargs: Additional arguments passed to registry

        Returns:
            Middleware plugin instance
        """
        return self.create_plugin("middleware", name, options, **kwargs)


# ============================================================================
# Global Registry Instance
# ============================================================================


def _create_central_registry() -> CentralPluginRegistry:
    """Create and initialize the global central registry instance.

    This function imports all type-specific registries and creates a unified
    CentralPluginRegistry instance. Auto-discovery and validation run automatically.

    Returns:
        Initialized CentralPluginRegistry instance
    """
    # Import type-specific registries (avoid circular imports)
    from elspeth.core.controls.cost_tracker_registry import cost_tracker_registry
    from elspeth.core.controls.rate_limiter_registry import rate_limiter_registry
    from elspeth.core.experiments.experiment_registries import (
        aggregation_plugin_registry,
        baseline_plugin_registry,
        early_stop_plugin_registry,
        row_plugin_registry,
        validation_plugin_registry,
    )
    from elspeth.core.registries.datasource import datasource_registry
    from elspeth.core.registries.llm import llm_registry
    from elspeth.core.registries.middleware import _middleware_registry  # Private registry
    from elspeth.core.registries.sink import sink_registry
    from elspeth.core.registries.utility import utility_plugin_registry

    return CentralPluginRegistry(
        datasource_registry=datasource_registry,
        llm_registry=llm_registry,
        sink_registry=sink_registry,
        middleware_registry=_middleware_registry,
        row_plugin_registry=row_plugin_registry,
        aggregation_plugin_registry=aggregation_plugin_registry,
        validation_plugin_registry=validation_plugin_registry,
        baseline_plugin_registry=baseline_plugin_registry,
        early_stop_plugin_registry=early_stop_plugin_registry,
        cost_tracker_registry=cost_tracker_registry,
        rate_limiter_registry=rate_limiter_registry,
        utility_plugin_registry=utility_plugin_registry,
    )


# Create global registry instance (auto-discover runs on import)
central_registry = _create_central_registry()
