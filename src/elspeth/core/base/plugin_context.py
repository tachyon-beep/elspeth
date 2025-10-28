"""Shared plugin context metadata."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Avoid top-level import of logging utilities to prevent circular imports
from elspeth.core.base.types import DeterminismLevel, SecurityLevel
from elspeth.core.security import ensure_determinism_level, ensure_security_level


class PluginContext(BaseModel):
    """Metadata propagated to plugin factories during instantiation.

    All plugins must declare both security_level and determinism_level.
    These are mandatory first-class attributes that propagate through the plugin hierarchy.

    This Pydantic model is FROZEN (immutable) for security - contexts cannot be modified
    after creation, preventing accidental security level downgrades or tampering.
    """

    plugin_name: str = Field(..., min_length=1, description="Name of the plugin instance")
    plugin_kind: str = Field(..., min_length=1, description="Type of plugin (datasource, llm, sink, etc)")
    security_level: SecurityLevel = Field(..., description="Security classification level (plugin's declared clearance)")
    operating_level: SecurityLevel | None = Field(
        default=None,
        description=(
            "Pipeline operating level (computed minimum clearance envelope). "
            "Plugins operate at this effective level, not their declared security_level. "
            "None indicates operating level not yet computed (pre-validation state)."
        ),
    )
    determinism_level: DeterminismLevel = Field(
        default=DeterminismLevel.NONE, description="Determinism level (none, low, high, guaranteed)"
    )
    provenance: tuple[str, ...] = Field(default_factory=tuple, description="Chain of plugin sources")
    parent: PluginContext | None = Field(default=None, description="Parent context for nested plugins")
    metadata: Mapping[str, Any] = Field(default_factory=dict, description="Additional context metadata")
    suite_root: Path | None = Field(default=None, description="Suite root directory (orchestration pack folder)")
    config_path: Path | None = Field(default=None, description="Configuration file path for this run")

    model_config = ConfigDict(
        # CRITICAL: Frozen for security - contexts are immutable
        frozen=True,
        # Allow arbitrary types (Mapping, etc.)
        arbitrary_types_allowed=True,
        # Strict mode - no extra fields
        extra="forbid",
        # Validate on assignment (though frozen=True prevents assignment)
        validate_assignment=True,
    )

    @field_validator("plugin_name", "plugin_kind")
    @classmethod
    def validate_non_empty(cls, v: str, info: Any) -> str:
        """Validate that critical fields are non-empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v.strip()

    @field_validator("security_level", mode="before")
    @classmethod
    def parse_security_level(cls, v: SecurityLevel | str | None) -> SecurityLevel:
        """Accept strings or enum; normalize via security.ensure_security_level."""
        return ensure_security_level(v)

    @field_validator("operating_level", mode="before")
    @classmethod
    def parse_operating_level(cls, v: SecurityLevel | str | None) -> SecurityLevel | None:
        """Accept strings or enum for operating_level; normalize via security.ensure_security_level.

        Returns None if value is None (pre-validation state).
        """
        if v is None:
            return None
        return ensure_security_level(v)

    @field_validator("determinism_level", mode="before")
    @classmethod
    def parse_determinism_level(cls, v: DeterminismLevel | str | None) -> DeterminismLevel:
        """Accept strings or enum; normalize via security.ensure_determinism_level."""
        return ensure_determinism_level(v)

    def derive(
        self,
        *,
        plugin_name: str,
        plugin_kind: str,
        security_level: SecurityLevel | None = None,
        operating_level: SecurityLevel | None = None,
        determinism_level: DeterminismLevel | None = None,
        provenance: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        suite_root: Path | None = None,
        config_path: Path | None = None,
    ) -> PluginContext:
        """Create a child context inheriting from this context.

        If security_level, operating_level, determinism_level, suite_root, or config_path
        are not provided, inherits from parent.

        This method creates a new immutable context (since the model is frozen)
        using Pydantic's model_validate to ensure all validators run.
        """
        sec_level = security_level or self.security_level
        # operating_level requires explicit check since None is a valid value (pre-validation)
        op_level = operating_level if operating_level is not None else self.operating_level
        det_level = determinism_level or self.determinism_level
        sources = tuple(provenance or ())
        data: Mapping[str, Any] = metadata or {}
        root = suite_root if suite_root is not None else self.suite_root
        cfg_path = config_path if config_path is not None else self.config_path

        # Use model_validate to ensure validators run on derived context
        return PluginContext.model_validate(
            {
                "plugin_name": plugin_name,
                "plugin_kind": plugin_kind,
                "security_level": sec_level,
                "operating_level": op_level,
                "determinism_level": det_level,
                "provenance": sources,
                "parent": self,
                "metadata": data,
                "suite_root": root,
                "config_path": cfg_path,
            }
        )


def apply_plugin_context(instance: Any, context: PluginContext) -> None:
    """Attach context metadata to a plugin instance.

    Sets both security_level and determinism_level as mandatory first-class attributes.
    Also attaches a PluginLogger for structured logging.

    For BasePlugin instances, security_level is read-only (set in constructor),
    so we skip setting it if it's already a property.
    """

    instance.plugin_context = context
    instance._elspeth_context = context  # noqa: SLF001 - internal marker for plugin context  # pylint: disable=protected-access

    # ADR-004: BasePlugin has read-only security_level property (set in constructor)
    # Only set security_level if it's not already a property
    if not hasattr(type(instance), 'security_level') or not isinstance(type(instance).security_level, property):
        instance.security_level = context.security_level

    instance._elspeth_security_level = context.security_level  # noqa: SLF001 - internal marker for plugin context  # pylint: disable=protected-access

    # Same for determinism_level (future: may also become read-only)
    if not hasattr(type(instance), 'determinism_level') or not isinstance(type(instance).determinism_level, property):
        instance.determinism_level = context.determinism_level

    instance._elspeth_determinism_level = context.determinism_level  # noqa: SLF001 - internal marker for plugin context  # pylint: disable=protected-access

    # Attach plugin logger for structured logging
    from elspeth.core.utils.logging import attach_plugin_logger  # pylint: disable=import-outside-toplevel

    attach_plugin_logger(instance, context)

    hook = getattr(instance, "on_plugin_context", None)
    if callable(hook):
        hook(context)
