"""Simple registry for resolving plugin implementations.

NOTE: This module is being gradually migrated to use the new BasePluginRegistry
framework. Three registries have been migrated so far:
- datasource_registry.py (Phase 2)
- llm_registry.py (Phase 2)
- sink_registry.py (Phase 2)
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from elspeth.core.datasource_registry import datasource_registry
from elspeth.core.protocols import DataSource, LLMClientProtocol, ResultSink
from elspeth.core.llm_registry import llm_registry
from elspeth.core.plugins import PluginContext, apply_plugin_context
from elspeth.core.registry.base import BasePluginFactory
from elspeth.core.security import (
    coalesce_determinism_level,
    coalesce_security_level,
)
from elspeth.core.sink_registry import sink_registry
from elspeth.core.validation import ConfigurationError

ON_ERROR_ENUM = {"type": "string", "enum": ["abort", "skip"]}

ARTIFACT_DESCRIPTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "schema_id": {"type": "string"},
        "persist": {"type": "boolean"},
        "alias": {"type": "string"},
        "security_level": {"type": "string"},
        "determinism_level": {"type": "string"},
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

ARTIFACTS_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "produces": {
            "type": "array",
            "items": ARTIFACT_DESCRIPTOR_SCHEMA,
        },
        "consumes": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string"},
                            "mode": {"type": "string", "enum": ["single", "all"]},
                        },
                        "required": ["token"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
    },
    "additionalProperties": False,
}


# NOTE: PluginFactory has been removed - use BasePluginFactory from registry.base
# This alias is provided for backward compatibility with tests during migration
PluginFactory = BasePluginFactory


class PluginRegistry:
    """Central registry for datasource, LLM, and sink plugins."""

    def __init__(self):
        # NOTE: Datasource, LLM, and Sink registries migrated (Phase 2)
        # - datasource_registry.py
        # - llm_registry.py
        # - sink_registry.py
        # For backward compatibility with tests, we expose their _plugins dicts
        # as properties below
        pass  # All registries have been migrated

    def create_datasource(
        self,
        name: str,
        options: dict[str, Any],
        *,
        provenance: Iterable[str] | None = None,
        parent_context: PluginContext | None = None,
    ) -> DataSource:
        """Instantiate a datasource plugin by name after validating options.

        NOTE: This method now delegates to the migrated datasource_registry
        from Phase 2. All validation, context handling, and plugin creation
        is handled by BasePluginRegistry.
        """
        return datasource_registry.create(
            name,
            options,
            provenance=provenance,
            parent_context=parent_context,
            require_security=True,
            require_determinism=True,
        )

    def validate_datasource(self, name: str, options: dict[str, Any] | None) -> None:
        """Validate datasource plugin options without creating the plugin.

        NOTE: This method now delegates to the migrated datasource_registry
        from Phase 2.
        """
        datasource_registry.validate(name, options or {})

    def create_llm(
        self,
        name: str,
        options: dict[str, Any],
        *,
        provenance: Iterable[str] | None = None,
        parent_context: PluginContext | None = None,
    ) -> LLMClientProtocol:
        """Instantiate an LLM plugin by name after validating options.

        NOTE: This method now delegates to the migrated llm_registry
        from Phase 2. All validation, context handling, and plugin creation
        is handled by BasePluginRegistry.
        """
        return llm_registry.create(
            name,
            options,
            provenance=provenance,
            parent_context=parent_context,
            require_security=True,
            require_determinism=True,
        )

    def create_llm_from_definition(
        self,
        definition: Mapping[str, Any] | LLMClientProtocol,
        *,
        parent_context: PluginContext,
        provenance: Iterable[str] | None = None,
    ) -> LLMClientProtocol:
        """Instantiate an LLM plugin from a nested definition with inherited context."""

        if isinstance(definition, LLMClientProtocol):
            context = parent_context.derive(
                plugin_name=getattr(definition, "name", definition.__class__.__name__),
                plugin_kind="llm",
                security_level=parent_context.security_level,
                determinism_level=parent_context.determinism_level,
                provenance=tuple(provenance or ("llm.instance",)),
            )
            apply_plugin_context(definition, context)
            return definition

        if not isinstance(definition, Mapping):
            raise ValueError("LLM definition must be a mapping or LLM instance")

        plugin_name = definition.get("plugin")
        if not plugin_name:
            raise ConfigurationError("LLM definition requires 'plugin'")
        options = dict(definition.get("options", {}) or {})

        # Handle security_level coalescing
        entry_sec_level = definition.get("security_level")
        options_sec_level = options.get("security_level")
        sources: list[str] = []
        if entry_sec_level is not None:
            sources.append(f"llm:{plugin_name}.definition.security_level")
        if options_sec_level is not None:
            sources.append(f"llm:{plugin_name}.options.security_level")

        # Handle determinism_level coalescing
        entry_det_level = definition.get("determinism_level")
        options_det_level = options.get("determinism_level")
        if entry_det_level is not None:
            sources.append(f"llm:{plugin_name}.definition.determinism_level")
        if options_det_level is not None:
            sources.append(f"llm:{plugin_name}.options.determinism_level")

        if provenance:
            sources.extend(provenance)

        try:
            sec_level = coalesce_security_level(parent_context.security_level, entry_sec_level, options_sec_level)
        except ValueError as exc:
            raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc

        # For determinism_level: if definition specifies it, use that; otherwise inherit from parent
        if entry_det_level is not None or options_det_level is not None:
            try:
                det_level = coalesce_determinism_level(entry_det_level, options_det_level)
            except ValueError as exc:
                raise ConfigurationError(f"llm:{plugin_name}: {exc}") from exc
        else:
            # No explicit determinism_level in definition, inherit from parent
            det_level = parent_context.determinism_level

        payload = dict(options)
        payload["security_level"] = sec_level
        payload["determinism_level"] = det_level
        resolved_provenance = tuple(sources or (f"llm:{plugin_name}.resolved",))
        return self.create_llm(
            plugin_name,
            payload,
            provenance=resolved_provenance,
            parent_context=parent_context,
        )

    def validate_llm(self, name: str, options: dict[str, Any] | None) -> None:
        """Validate LLM plugin options without instantiation.

        NOTE: This method now delegates to the migrated llm_registry
        from Phase 2.
        """
        llm_registry.validate(name, options or {})

    def create_sink(
        self,
        name: str,
        options: dict[str, Any],
        *,
        provenance: Iterable[str] | None = None,
        parent_context: PluginContext | None = None,
    ) -> ResultSink:
        """Instantiate a sink plugin by name after validating options.

        NOTE: This method now delegates to the migrated sink_registry
        from Phase 2. All validation, context handling, and plugin creation
        is handled by BasePluginRegistry.
        """
        return sink_registry.create(
            name,
            options,
            provenance=provenance,
            parent_context=parent_context,
            require_security=True,
            require_determinism=True,
        )

    def validate_sink(self, name: str, options: dict[str, Any] | None) -> None:
        """Validate sink plugin options without instantiation.

        NOTE: This method now delegates to the migrated sink_registry
        from Phase 2.
        """
        sink_registry.validate(name, options or {})

    @property
    def _datasources(self) -> dict[str, Any]:
        """Backward compatibility property for tests that access registry._datasources.

        Returns the internal _plugins dict from the migrated datasource_registry.
        This allows existing tests to mock datasources by directly modifying
        the dictionary.
        """
        return datasource_registry._plugins

    @property
    def _llms(self) -> dict[str, Any]:
        """Backward compatibility property for tests that access registry._llms.

        Returns the internal _plugins dict from the migrated llm_registry.
        This allows existing tests to mock LLMs by directly modifying
        the dictionary.
        """
        return llm_registry._plugins

    @property
    def _sinks(self) -> dict[str, Any]:
        """Backward compatibility property for tests that access registry._sinks.

        Returns the internal _plugins dict from the migrated sink_registry.
        This allows existing tests to mock sinks by directly modifying
        the dictionary.
        """
        return sink_registry._plugins


registry = PluginRegistry()
