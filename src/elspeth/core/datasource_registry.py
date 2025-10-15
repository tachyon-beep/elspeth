"""Datasource plugin registry using consolidated base framework.

This module provides the datasource registry implementation using the new
BasePluginRegistry framework from Phase 1. It replaces the duplicate
datasource registry logic in registry.py.
"""

from __future__ import annotations

import logging
from typing import Any

from elspeth.adapters.blob_store import load_blob_config
from elspeth.core.plugin_context import PluginContext
from elspeth.core.protocols import DataSource
from elspeth.core.registry.base import BasePluginRegistry
from elspeth.core.registry.schemas import ON_ERROR_ENUM, with_security_properties
from elspeth.core.security import validate_azure_blob_endpoint
from elspeth.core.validation_base import ConfigurationError
from elspeth.plugins.nodes.sources import BlobDataSource, CSVBlobDataSource, CSVDataSource

logger = logging.getLogger(__name__)

# Create the datasource registry with type safety
datasource_registry = BasePluginRegistry[DataSource]("datasource")


# ============================================================================
# Datasource Factory Functions
# ============================================================================


def _create_blob_datasource(options: dict[str, Any], context: PluginContext) -> BlobDataSource:
    """Create Azure Blob datasource with endpoint validation."""
    # Load blob configuration to validate endpoint
    config_path = options.get("config_path")
    profile = options.get("profile", "default")

    if config_path:
        try:
            # Load the blob config to extract account_url
            blob_config = load_blob_config(config_path, profile=profile)

            # Validate endpoint against approved patterns
            security_level = context.security_level if context else None
            validate_azure_blob_endpoint(
                endpoint=blob_config.account_url,
                security_level=security_level,
            )
            logger.debug(f"Azure Blob endpoint validated: {blob_config.account_url}")
        except ValueError as exc:
            logger.error(f"Azure Blob endpoint validation failed: {exc}")
            raise ConfigurationError(f"Azure Blob datasource endpoint validation failed: {exc}") from exc

    return BlobDataSource(**options)


def _create_csv_blob_datasource(options: dict[str, Any], context: PluginContext) -> CSVBlobDataSource:
    """Create CSV Blob datasource (local file that mimics blob storage).

    Note: Despite the name, CSVBlobDataSource reads from local files, not actual blob storage.
    It's used for testing/mocking blob scenarios. No endpoint validation needed.
    """
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
            "retain_local": {"type": "boolean"},  # REQUIRED - audit trail
            "retain_local_path": {"type": "string"},
        },
        "required": ["config_path", "retain_local"],  # Must explicitly set retain_local
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
            "retain_local": {"type": "boolean"},  # REQUIRED - audit trail
            "retain_local_path": {"type": "string"},
        },
        "required": ["path", "retain_local"],  # Must explicitly set retain_local
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
            "retain_local": {"type": "boolean"},  # REQUIRED - audit trail
            "retain_local_path": {"type": "string"},
        },
        "required": ["path", "retain_local"],  # Must explicitly set retain_local
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
