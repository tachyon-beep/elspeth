"""CatalogServiceImpl — wraps PluginManager for catalog browsing."""

from __future__ import annotations

from typing import Any

from elspeth.plugins.infrastructure.config_base import PluginConfig
from elspeth.plugins.infrastructure.discovery import get_plugin_description
from elspeth.plugins.infrastructure.manager import PluginManager
from elspeth.plugins.infrastructure.validation import PluginConfigValidator
from elspeth.web.catalog.schemas import (
    ConfigFieldSummary,
    PluginSchemaInfo,
    PluginSummary,
)

# Valid plugin type path segments and their PluginManager lookup methods
_VALID_TYPES = frozenset({"source", "transform", "sink"})


class CatalogServiceImpl:
    """Read-only catalog backed by PluginManager.

    Receives an already-initialized PluginManager via constructor injection.
    Does NOT call register_builtin_plugins() — the shared singleton factory
    (get_shared_plugin_manager) handles initialization before injection.

    Caches plugin class lists once at construction. The plugin set is
    fixed for the lifetime of the process.
    """

    def __init__(self, plugin_manager: PluginManager) -> None:
        self._pm = plugin_manager
        self._validator = PluginConfigValidator()

        # Cache plugin classes once
        self._source_classes = plugin_manager.get_sources()
        self._transform_classes = plugin_manager.get_transforms()
        self._sink_classes = plugin_manager.get_sinks()

    def list_sources(self) -> list[PluginSummary]:
        return [self._to_summary(cls, "source") for cls in self._source_classes]

    def list_transforms(self) -> list[PluginSummary]:
        return [self._to_summary(cls, "transform") for cls in self._transform_classes]

    def list_sinks(self) -> list[PluginSummary]:
        return [self._to_summary(cls, "sink") for cls in self._sink_classes]

    def get_schema(self, plugin_type: str, name: str) -> PluginSchemaInfo:
        if plugin_type not in _VALID_TYPES:
            raise ValueError(f"Unknown plugin type: {plugin_type}. Must be one of: {sorted(_VALID_TYPES)}")

        # Look up plugin class to verify it exists
        lookup = {
            "source": self._pm.get_source_by_name,
            "transform": self._pm.get_transform_by_name,
            "sink": self._pm.get_sink_by_name,
        }
        try:
            plugin_cls = lookup[plugin_type](name)
        except ValueError:
            available = self._available_names(plugin_type)
            raise ValueError(f"Unknown {plugin_type} plugin: {name}. Available: {available}") from None

        # Get config model via PluginConfigValidator
        json_schema = self._get_json_schema(plugin_type, name)

        # Full docstring for schema view (not just first line)
        description = (plugin_cls.__doc__ or "").strip()
        if not description:
            description = get_plugin_description(plugin_cls)

        return PluginSchemaInfo(
            name=name,
            plugin_type=plugin_type,
            description=description,
            json_schema=json_schema,
        )

    # -- Private helpers --

    def _to_summary(self, plugin_cls: type, plugin_type: str) -> PluginSummary:
        """Convert a plugin class to a PluginSummary."""
        name: str = plugin_cls.name  # type: ignore[attr-defined]
        description = get_plugin_description(plugin_cls)
        config_fields = self._extract_config_fields(plugin_type, name)
        return PluginSummary(
            name=name,
            description=description,
            plugin_type=plugin_type,
            config_fields=config_fields,
        )

    def _extract_config_fields(self, plugin_type: str, name: str) -> list[ConfigFieldSummary]:
        """Extract config field summaries from a plugin's Pydantic config model."""
        config_model = self._resolve_config_model(plugin_type, name)
        if config_model is None:
            return []

        # Pydantic's model_json_schema() produces a JSON Schema dict.
        # Keys like "type", "anyOf", "description", "default" are conditionally
        # present per JSON Schema spec — .get() is correct here (not defensive
        # programming, but standard JSON Schema traversal).
        schema = config_model.model_json_schema()
        properties: dict[str, Any] = schema.get("properties", {})
        required_fields: set[str] = set(schema.get("required", []))

        fields: list[ConfigFieldSummary] = []
        for field_name, field_schema in properties.items():
            json_type = field_schema.get("type", "object")
            # anyOf produces no top-level type — pick first non-null branch type
            if "anyOf" in field_schema and not field_schema.get("type"):
                for branch in field_schema["anyOf"]:
                    if branch.get("type") != "null":
                        json_type = branch.get("type", "object")
                        break

            fields.append(
                ConfigFieldSummary(
                    name=field_name,
                    type=json_type,
                    required=field_name in required_fields,
                    description=field_schema.get("description"),
                    default=field_schema.get("default"),
                )
            )

        return fields

    def _resolve_config_model(self, plugin_type: str, name: str) -> type[PluginConfig] | None:
        """Resolve plugin name to its Pydantic config model class.

        Delegates to PluginConfigValidator's private methods to avoid
        duplicating the name-to-config-class mapping.

        Returns None for plugins with no config model (e.g., null source).
        """
        try:
            if plugin_type in ("source", "sources"):
                return self._validator._get_source_config_model(name)
            elif plugin_type in ("transform", "transforms"):
                return self._validator._get_transform_config_model(name)
            elif plugin_type in ("sink", "sinks"):
                return self._validator._get_sink_config_model(name)
        except ValueError:
            # Plugin exists in PluginManager but has no config model mapping
            # in PluginConfigValidator — return None (empty schema)
            return None
        return None

    def _get_json_schema(self, plugin_type: str, name: str) -> dict[str, Any]:
        """Get full JSON schema for a plugin's config model."""
        config_model = self._resolve_config_model(plugin_type, name)
        if config_model is None:
            return {}
        schema: dict[str, Any] = config_model.model_json_schema()
        return schema

    def _available_names(self, plugin_type: str) -> list[str]:
        """Get sorted list of available plugin names for a type."""
        classes = {
            "source": self._source_classes,
            "transform": self._transform_classes,
            "sink": self._sink_classes,
        }[plugin_type]
        return sorted(cls.name for cls in classes)  # type: ignore[attr-defined]
