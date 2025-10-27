"""Base plugin registry infrastructure.

This module provides the core abstractions for plugin registries,
consolidating the factory pattern previously duplicated across
multiple registry implementations.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, ContextManager, Generic, Iterable, Iterator, Mapping, TypeVar

from elspeth.core.base.plugin_context import PluginContext, apply_plugin_context
from elspeth.core.validation.base import ConfigurationError, validate_schema

from .context_utils import (
    create_plugin_context,
    extract_security_levels,
    prepare_plugin_payload,
)

T = TypeVar("T")  # Plugin type


@dataclass
class BasePluginFactory(Generic[T]):
    """
    Base factory for creating and validating plugin instances.

    Consolidates the factory pattern repeated across 5 registries.
    Provides schema validation and consistent plugin instantiation.

    Type Parameters:
        T: The type of plugin this factory creates

    Attributes:
        create: Factory callable that creates plugin instances
        schema: Optional JSON schema for validation
        plugin_type: Human-readable plugin type (e.g., "datasource", "llm")
        capabilities: Declared capability flags exposed to registry consumers

    Example:
        >>> def create_my_plugin(opts: Dict, ctx: PluginContext) -> MyPlugin:
        ...     return MyPlugin(**opts)
        >>> factory = BasePluginFactory(
        ...     create=create_my_plugin,
        ...     schema={"type": "object", "properties": {...}},
        ...     plugin_type="my_plugin"
        ... )
        >>> plugin = factory.instantiate(
        ...     options={"key": "value"},
        ...     plugin_context=context,
        ...     schema_context="my_plugin:my_name"
        ... )
    """

    create: Callable[[dict[str, Any], PluginContext], T]
    schema: Mapping[str, Any] | None = None
    plugin_type: str = "plugin"
    requires_input_schema: bool = False
    capabilities: frozenset[str] = field(default_factory=frozenset)
    declared_security_level: str | None = None  # ADR-002-B: Plugin author's security declaration
    _compiled_validator: Any | None = field(default=None, init=False, repr=False)

    def validate(self, options: dict[str, Any], *, context: str) -> None:
        """
        Validate options against the schema.

        Args:
            options: Plugin options dictionary to validate
            context: Context string for error messages (e.g., "datasource:csv")

        Raises:
            ConfigurationError: If validation fails
        """
        if self.schema is None:
            return

        # Fast path: cache compiled JSON Schema validator per factory to avoid repeated parse/compile cost
        try:
            if self._compiled_validator is None:
                # Lazy import to avoid cost when unused, without type stubs dependency
                import importlib  # pylint: disable=import-outside-toplevel

                validator_cls = importlib.import_module("jsonschema").Draft202012Validator
                self._compiled_validator = validator_cls(self.schema)
            if self._compiled_validator is None:
                raise RuntimeError(f"Failed to compile JSON schema validator for {context}. Ensure jsonschema package is installed.")
            # Validate options
            errors = list(self._compiled_validator.iter_errors(options or {}))
            if errors:
                # Build a concise error message similar to validate_schema
                formatted = []
                for err in errors:
                    path = ".".join(str(p) for p in err.path) if err.path else context
                    formatted.append(f"{context}: {err.message} (at {path})")
                raise ConfigurationError("\n".join(formatted))
        except Exception:  # Fallback to original path for compatibility/error formatting
            errors = list(validate_schema(options or {}, self.schema, context=context))
            if errors:
                message = "\n".join(msg.format() for msg in errors)
                raise ConfigurationError(message)

    def instantiate(
        self,
        options: dict[str, Any],
        *,
        plugin_context: PluginContext,
        schema_context: str,
    ) -> T:
        """
        Validate and create a plugin instance.

        This method:
        1. Validates options against the schema
        2. Calls the factory function to create the plugin
        3. Applies the plugin context to the instance

        Args:
            options: Plugin configuration options
            plugin_context: Security and provenance context
            schema_context: Context string for validation errors

        Returns:
            Instantiated plugin of type T

        Raises:
            ConfigurationError: If validation fails
        """
        self.validate(options, context=schema_context)
        plugin = self.create(options, plugin_context)

        # Layer 3: Verify declared security_level matches actual (ADR-002-B, VULN-004)
        if self.declared_security_level is not None:
            # Only verify if plugin has security_level attribute
            if hasattr(plugin, "security_level"):
                actual_security_level = plugin.security_level

                # SECURITY VALIDATION: Enforce SecurityLevel enum (ADR-002-B immutable policy)
                # SecurityLevel is defined as class SecurityLevel(str, Enum), so isinstance(SecurityLevel.X, str) is True
                # We check for SecurityLevel enum specifically to reject plain strings or other types
                from elspeth.core.base.types import SecurityLevel  # pylint: disable=import-outside-toplevel

                if not isinstance(actual_security_level, SecurityLevel):
                    # Plain string or other type - not a SecurityLevel enum
                    # This prevents regressions where plugins return strings instead of enums
                    raise ConfigurationError(
                        f"CRITICAL SECURITY POLICY VIOLATION: Plugin {type(plugin).__name__} "
                        f"returns {type(actual_security_level).__name__} security_level='{actual_security_level}'. "
                        f"ALL plugins MUST return SecurityLevel enum instance. "
                        f"Update plugin to use SecurityLevel.{str(actual_security_level).upper()} instead."
                    )

                # SecurityLevel enum comparison: compare enum.value (string) against declared (string)
                if actual_security_level.value != self.declared_security_level:
                    raise ConfigurationError(
                        f"{schema_context}: Plugin declares security_level={self.declared_security_level} "
                        f"but has actual security_level={actual_security_level.value}. "
                        "Plugin implementation must match registry declaration (ADR-002-B)."
                    )

        # Attach factory metadata for downstream enforcement (e.g., input_schema requirement)
        try:
            setattr(plugin, "_elspeth_requires_input_schema", bool(self.requires_input_schema))
        except Exception:  # pragma: no cover - best effort
            # Best-effort; proceed even if plugin does not allow attribute assignment
            import logging  # pylint: disable=import-outside-toplevel

            logging.getLogger(__name__).debug("Failed to set _elspeth_requires_input_schema on %s", type(plugin).__name__, exc_info=True)
        apply_plugin_context(plugin, plugin_context)
        return plugin


# Type alias for registry dictionaries
PluginFactoryMap = dict[str, BasePluginFactory[T]]


class BasePluginRegistry(Generic[T]):
    """
    Base class for plugin registries.

    Provides common functionality for registering, validating, and creating
    plugins with consistent security context handling. This class consolidates
    the registry pattern previously duplicated across 5 implementations.

    Type Parameters:
        T: The type of plugin this registry manages

    Attributes:
        plugin_type: Human-readable plugin type name
        _plugins: Internal registry of factories

    Example:
        >>> registry = BasePluginRegistry[DataSource]("datasource")
        >>> registry.register(
        ...     "csv",
        ...     lambda opts, ctx: CSVDataSource(**opts),
        ...     schema={...}
        ... )
        >>> plugin = registry.create(
        ...     name="csv",
        ...     options={"path": "data.csv"},
        ...     require_security=True
        ... )
    """

    def __init__(self, plugin_type: str):
        """
        Initialize a plugin registry.

        Args:
            plugin_type: Human-readable type name (e.g., "datasource", "llm")
        """
        self.plugin_type = plugin_type
        self._plugins: PluginFactoryMap[T] = {}

    def register(
        self,
        name: str,
        factory: Callable[[dict[str, Any], PluginContext], T],
        *,
        schema: Mapping[str, Any] | None = None,
        requires_input_schema: bool = False,
        capabilities: Iterable[str] | None = None,
        declared_security_level: str | None = None,
    ) -> None:
        """
        Register a plugin factory with its immutable security policy.

        Args:
            name: Plugin name (used for lookup)
            factory: Factory callable that creates plugin instances
            schema: Optional JSON schema for validation
            capabilities: Optional iterable of capability flags exposed to callers
            declared_security_level: Plugin's hard-coded security level (ADR-002-B).
                This is the security level declared by the plugin author, not configurable by users.
        """
        plugin_factory = BasePluginFactory(
            create=factory,
            schema=schema,
            plugin_type=self.plugin_type,
            requires_input_schema=requires_input_schema,
            capabilities=frozenset(capabilities or ()),
            declared_security_level=declared_security_level,
        )
        # Pre-compile JSON schema validator once at registration to avoid first-call latency
        if schema is not None:
            try:
                import importlib  # pylint: disable=import-outside-toplevel

                validator_cls = importlib.import_module("jsonschema").Draft202012Validator
                plugin_factory._compiled_validator = validator_cls(schema)
                # Warm up validator by running a trivial check to pre-initialize internals
                if plugin_factory._compiled_validator is not None:
                    try:
                        _ = list(plugin_factory._compiled_validator.iter_errors({}))  # noqa: F841
                    except Exception:
                        import logging  # pylint: disable=import-outside-toplevel

                        logging.getLogger(__name__).debug("Warm-up validation error ignored for %s", name, exc_info=True)
            except Exception:
                plugin_factory._compiled_validator = None  # Fallback; validate() will handle
        self._plugins[name] = plugin_factory

    def validate(self, name: str, options: dict[str, Any] | None) -> None:
        """
        Validate plugin options without instantiation.

        Args:
            name: Plugin name
            options: Plugin options to validate

        Raises:
            ValueError: If plugin not found
            ConfigurationError: If validation fails
        """
        factory = self._get_factory(name)
        payload = dict(options or {})

        # Note: Security validation happens at create time
        # Strip framework-level keys before validation
        payload.pop("security_level", None)
        payload.pop("determinism_level", None)

        factory.validate(payload, context=f"{self.plugin_type}:{name}")

    def get_plugin_capabilities(self, name: str) -> frozenset[str]:
        """Return declared capability flags for the specified plugin."""

        factory = self._plugins.get(name)
        if factory is None:
            raise KeyError(f"Unknown {self.plugin_type} plugin '{name}'")
        return factory.capabilities

    def create(
        self,
        name: str,
        options: dict[str, Any],
        *,
        provenance: Iterable[str] | None = None,
        parent_context: PluginContext | None = None,
        require_determinism: bool = True,
    ) -> T:
        """
        Create a plugin instance with full context handling.

        This method handles the complete plugin lifecycle:
        1. Extracts and normalizes security/determinism levels
        2. Creates or derives plugin context
        3. Validates options against schema
        4. Instantiates the plugin
        5. Applies context to the plugin

        Args:
            name: Plugin name
            options: Plugin configuration options
            provenance: Optional provenance source identifiers
            parent_context: Optional parent context for inheritance
            require_determinism: Whether determinism_level is required

        Returns:
            Instantiated plugin of type T

        Raises:
            ValueError: If plugin not found
            ConfigurationError: If validation or creation fails
        """
        factory = self._get_factory(name)

        # ADR-002-B: ALWAYS include plugin's declared_security_level in coalescing
        # SECURITY: Factory default MUST participate regardless of parent_context
        # to enforce weakest-link model (prevents parent SECRET from bypassing child UNOFFICIAL)
        definition_for_extraction = dict(options)
        if (factory.declared_security_level is not None
            and "security_level" not in options):
            # ALWAYS add declared level - coalesce_security_level will enforce weakest-link
            definition_for_extraction["security_level"] = factory.declared_security_level

        # Extract and normalize security levels (ADR-001: always required, no backdoors)
        security_level, determinism_level, sources = extract_security_levels(
            definition=definition_for_extraction,
            options=options,
            plugin_type=self.plugin_type,
            plugin_name=name,
            parent_context=parent_context,
            require_determinism=require_determinism,
        )

        # Add provenance if provided
        if provenance:
            sources.extend(provenance)

        # Create plugin context
        context = create_plugin_context(
            plugin_name=name,
            plugin_kind=self.plugin_type,
            security_level=security_level,
            determinism_level=determinism_level,
            provenance=sources,
            parent_context=parent_context,
        )

        # Prepare payload (strip framework keys)
        payload = prepare_plugin_payload(options)

        # Instantiate plugin using BasePluginFactory
        return factory.instantiate(
            payload,
            plugin_context=context,
            schema_context=f"{self.plugin_type}:{name}",
        )

    def _get_factory(self, name: str) -> BasePluginFactory[T]:
        """
        Get factory by name, raising ValueError if not found.

        Args:
            name: Plugin name

        Returns:
            Factory for the named plugin

        Raises:
            ValueError: If plugin not found
        """
        try:
            return self._plugins[name]
        except KeyError as exc:
            raise ValueError(f"Unknown {self.plugin_type} plugin '{name}'") from exc

    def list_plugins(self) -> list[str]:
        """
        Return list of registered plugin names.

        Returns:
            Sorted list of registered plugin names
        """
        return sorted(self._plugins.keys())

    def unregister(self, name: str) -> None:
        """
        Unregister a plugin by name (for testing).

        This method removes a plugin from the registry. It's primarily intended
        for use in tests to clean up after plugin registration or to test
        error handling for missing plugins.

        Args:
            name: Plugin name to remove

        Raises:
            KeyError: If plugin not found

        Example:
            >>> registry.register("test_plugin", factory)
            >>> registry.unregister("test_plugin")
        """
        del self._plugins[name]

    def clear(self) -> None:
        """
        Clear all registered plugins (for testing).

        This method removes all plugins from the registry. It's primarily
        intended for use in test fixtures to ensure a clean state between tests.

        Example:
            >>> registry.clear()
            >>> assert len(registry.list_plugins()) == 0
        """
        self._plugins.clear()

    def temporary_override(
        self,
        name: str,
        factory: Callable[[dict[str, Any], PluginContext], T],
        *,
        schema: Mapping[str, Any] | None = None,
    ) -> ContextManager[None]:
        """
        Context manager to temporarily override a plugin factory (for testing).

        This allows tests to temporarily replace a plugin factory with a mock
        or test implementation. The original factory is automatically restored
        when the context exits, even if an exception occurs.

        Args:
            name: Plugin name to override
            factory: Temporary factory callable
            schema: Optional schema for temporary factory

        Yields:
            None

        Example:
            >>> def mock_factory(opts, ctx):
            ...     return MockPlugin(**opts)
            >>> with registry.temporary_override("csv", mock_factory):
            ...     plugin = registry.create("csv", {})  # Uses mock
            ...     assert isinstance(plugin, MockPlugin)
            >>> # Original factory restored
            >>> plugin = registry.create("csv", {})  # Uses original

        Note:
            If the plugin doesn't exist before the override, it will be
            removed when the context exits. This allows testing with
            completely new plugin names.
        """

        @contextmanager
        def _override() -> Iterator[None]:
            original = self._plugins.get(name)
            # ADR-002-B: Preserve declared_security_level from original factory
            # For new plugins (no original), default to UNOFFICIAL for testing
            original_declared_security_level = original.declared_security_level if original else "UNOFFICIAL"
            self.register(
                name,
                factory,
                schema=schema,
                declared_security_level=original_declared_security_level,
            )
            try:
                yield
            finally:
                if original is not None:
                    self._plugins[name] = original
                else:
                    self._plugins.pop(name, None)

        return _override()


__all__ = [
    "BasePluginFactory",
    "BasePluginRegistry",
    "PluginFactoryMap",
]
