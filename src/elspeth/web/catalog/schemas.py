"""Catalog API response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ConfigFieldSummary(BaseModel):
    """Summary of a single field in a plugin's config model."""

    name: str
    type: str
    required: bool
    description: str | None = None
    default: Any | None = None


class PluginSummary(BaseModel):
    """Lightweight plugin info for catalog browsing."""

    name: str
    description: str
    plugin_type: str
    config_fields: list[ConfigFieldSummary]


class PluginSchemaInfo(BaseModel):
    """Full plugin schema detail for the composer."""

    name: str
    plugin_type: str
    description: str
    json_schema: dict[str, Any]
