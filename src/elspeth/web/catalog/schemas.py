"""Catalog API response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

PluginKind = Literal["source", "transform", "sink"]


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
    plugin_type: PluginKind
    config_fields: list[ConfigFieldSummary]


class PluginSchemaInfo(BaseModel):
    """Full plugin schema detail for the composer.

    ``json_schema`` contains the raw output of ``ConfigModel.model_json_schema()``.
    It is ``{}`` (empty dict) when the plugin has no configuration model
    (e.g., the ``null`` source).
    """

    name: str
    plugin_type: PluginKind
    description: str
    json_schema: dict[str, Any]
