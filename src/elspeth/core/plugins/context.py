"""Shared plugin context metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class PluginContext:
    """Metadata propagated to plugin factories during instantiation.

    All plugins must declare both security_level and determinism_level.
    These are mandatory first-class attributes that propagate through the plugin hierarchy.
    """

    plugin_name: str
    plugin_kind: str
    security_level: str
    determinism_level: str = "none"  # Temporary default during migration
    provenance: tuple[str, ...] = field(default_factory=tuple)
    parent: "PluginContext | None" = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def derive(
        self,
        *,
        plugin_name: str,
        plugin_kind: str,
        security_level: str | None = None,
        determinism_level: str | None = None,
        provenance: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "PluginContext":
        """Create a child context inheriting from this context.

        If security_level or determinism_level are not provided, inherits from parent.
        """

        sec_level = security_level or self.security_level
        det_level = determinism_level or self.determinism_level
        sources = tuple(provenance or ())
        data: Mapping[str, Any] = metadata or {}
        return PluginContext(
            plugin_name=plugin_name,
            plugin_kind=plugin_kind,
            security_level=sec_level,
            determinism_level=det_level,
            provenance=sources,
            parent=self,
            metadata=data,
        )


def apply_plugin_context(instance: Any, context: PluginContext) -> None:
    """Attach context metadata to a plugin instance.

    Sets both security_level and determinism_level as mandatory first-class attributes.
    """

    setattr(instance, "plugin_context", context)
    setattr(instance, "_elspeth_context", context)
    setattr(instance, "security_level", context.security_level)
    setattr(instance, "_elspeth_security_level", context.security_level)
    setattr(instance, "determinism_level", context.determinism_level)
    setattr(instance, "_elspeth_determinism_level", context.determinism_level)
    hook = getattr(instance, "on_plugin_context", None)
    if callable(hook):
        hook(context)
