"""Datasource plugin registry using consolidated base framework.

This module provides the datasource registry implementation using the new
BasePluginRegistry framework from Phase 1. It replaces the duplicate
datasource registry logic in registry.py.
"""

from __future__ import annotations

from typing import Any

from elspeth.core.protocols import DataSource
from elspeth.core.plugins import PluginContext
from elspeth.core.registry.base import BasePluginRegistry
from elspeth.core.registry.schemas import ON_ERROR_ENUM, with_security_properties
from elspeth.plugins.nodes.sources import BlobDataSource, CSVBlobDataSource, CSVDataSource

# Create the datasource registry with type safety
datasource_registry = BasePluginRegistry[DataSource]("datasource")


# ============================================================================
# Datasource Factory Functions
# ============================================================================


def _create_blob_datasource(options: dict[str, Any], context: PluginContext) -> BlobDataSource:
    """Create Azure Blob datasource."""
    return BlobDataSource(**options)


def _create_csv_blob_datasource(options: dict[str, Any], context: PluginContext) -> CSVBlobDataSource:
    """Create CSV Blob datasource."""
    return CSVBlobDataSource(**options)


def _create_csv_datasource(options: dict[str, Any], context: PluginContext) -> CSVDataSource:
    """Create local CSV datasource."""
    return CSVDataSource(**options)


# ============================================================================
# Schema Definitions
# ============================================================================

_BLOB_DATASOURCE_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "config_path": {"type": "string"},
            "profile": {"type": "string"},
            "pandas_kwargs": {"type": "object"},
            "on_error": ON_ERROR_ENUM,
        },
        "required": ["config_path"],
        "additionalProperties": True,
    },
    require_security=False,  # Will be enforced by registry
    require_determinism=False,
)

_CSV_BLOB_DATASOURCE_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "dtype": {"type": "object"},
            "encoding": {"type": "string"},
            "on_error": ON_ERROR_ENUM,
        },
        "required": ["path"],
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)

_CSV_DATASOURCE_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "dtype": {"type": "object"},
            "encoding": {"type": "string"},
            "on_error": ON_ERROR_ENUM,
        },
        "required": ["path"],
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)


# ============================================================================
# Register Datasources
# ============================================================================

datasource_registry.register(
    "azure_blob",
    _create_blob_datasource,
    schema=_BLOB_DATASOURCE_SCHEMA,
)

datasource_registry.register(
    "csv_blob",
    _create_csv_blob_datasource,
    schema=_CSV_BLOB_DATASOURCE_SCHEMA,
)

datasource_registry.register(
    "local_csv",
    _create_csv_datasource,
    schema=_CSV_DATASOURCE_SCHEMA,
)


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "datasource_registry",
]
