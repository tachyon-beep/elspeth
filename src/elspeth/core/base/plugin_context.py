"""Shared plugin context metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PluginContext(BaseModel):
    """Metadata propagated to plugin factories during instantiation.

    All plugins must declare both security_level and determinism_level.
    These are mandatory first-class attributes that propagate through the plugin hierarchy.

    This Pydantic model is FROZEN (immutable) for security - contexts cannot be modified
    after creation, preventing accidental security level downgrades or tampering.
    """

    plugin_name: str = Field(..., min_length=1, description="Name of the plugin instance")
    plugin_kind: str = Field(..., min_length=1, description="Type of plugin (datasource, llm, sink, etc)")
    security_level: str = Field(..., min_length=1, description="Security classification level")
    determinism_level: str = Field(default="none", description="Determinism level (none, low, high, guaranteed)")
    provenance: tuple[str, ...] = Field(default_factory=tuple, description="Chain of plugin sources")
    parent: "PluginContext | None" = Field(default=None, description="Parent context for nested plugins")
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

    @field_validator("plugin_name", "plugin_kind", "security_level")
    @classmethod
    def validate_non_empty(cls, v: str, info: Any) -> str:
        """Validate that critical fields are non-empty."""
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} cannot be empty")
        return v.strip()

    @field_validator("determinism_level")
    @classmethod
    def validate_determinism_level(cls, v: str) -> str:
        """Validate determinism level is one of the expected values.

        Valid levels: none, low, high, guaranteed
        (These correspond to the DeterminismLevel enum)
        """
        valid_levels = {"none", "low", "high", "guaranteed"}
        v_lower = v.lower().strip()
        if v_lower not in valid_levels:
            raise ValueError(f"determinism_level must be one of {valid_levels}, got '{v}'")
        return v_lower

    def derive(
        self,
        *,
        plugin_name: str,
        plugin_kind: str,
        security_level: str | None = None,
        determinism_level: str | None = None,
        provenance: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        suite_root: Path | None = None,
        config_path: Path | None = None,
    ) -> "PluginContext":
        """Create a child context inheriting from this context.

        If security_level, determinism_level, suite_root, or config_path are not provided,
        inherits from parent.

        This method creates a new immutable context (since the model is frozen)
        using Pydantic's model_validate to ensure all validators run.
        """
        sec_level = security_level or self.security_level
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
    """

    setattr(instance, "plugin_context", context)
    setattr(instance, "_elspeth_context", context)
    setattr(instance, "security_level", context.security_level)
    setattr(instance, "_elspeth_security_level", context.security_level)
    setattr(instance, "determinism_level", context.determinism_level)
    setattr(instance, "_elspeth_determinism_level", context.determinism_level)

    # Attach plugin logger for structured logging
    from elspeth.core.utils.logging import attach_plugin_logger

    attach_plugin_logger(instance, context)

    hook = getattr(instance, "on_plugin_context", None)
    if callable(hook):
        hook(context)
