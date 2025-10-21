"""Sink plugin registry using consolidated base framework.

This module provides the sink registry implementation using the new
BasePluginRegistry framework from Phase 1/2. It replaces the duplicate
sink registry logic in registry.py.

The sink registry is the largest registry with 13 plugins, so this migration
will have the biggest impact on code reduction.
"""

from __future__ import annotations

import logging
from sys import modules as _modules
from typing import Any

from elspeth.adapters.blob_store import load_blob_config
from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.base.protocols import ResultSink
from elspeth.core.security import validate_azure_blob_endpoint
from elspeth.core.validation.base import ConfigurationError
from elspeth.plugins.nodes.sinks import (
    AnalyticsReportSink,
    AzureBlobArtifactsSink,
    AzureDevOpsArtifactsRepoSink,
    AzureDevOpsRepoSink,
    BlobResultSink,
    CsvResultSink,
    ExcelResultSink,
    FileCopySink,
    GitHubRepoSink,
    LocalBundleSink,
    ReproducibilityBundleSink,
    SignedArtifactSink,
    VisualAnalyticsSink,
    ZipResultSink,
)
from elspeth.plugins.nodes.sinks.embeddings_store import (
    DEFAULT_EMBEDDING_FIELD,
    DEFAULT_ID_FIELD,
    DEFAULT_TEXT_FIELD,
    EmbeddingsStoreSink,
)
from elspeth.plugins.nodes.sinks.enhanced_visual_report import EnhancedVisualAnalyticsSink

from .base import BasePluginRegistry
from .schemas import (
    with_artifact_properties,
    with_error_handling,
    with_security_properties,
)

# Capability flags exposed by sink plugins. Keep constants centralized to avoid drift.
CAP_SUPPORTS_FOLDER_PATH_INJECTION = "supports_folder_path_injection"

logger = logging.getLogger(__name__)

# Create the sink registry with type safety
sink_registry = BasePluginRegistry[ResultSink]("sink")


# ============================================================================
# Sink Factory Functions
# ============================================================================


def _create_azure_blob_sink(options: dict[str, Any], context: PluginContext) -> BlobResultSink:
    """Create Azure Blob result sink with endpoint validation."""
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
            raise ConfigurationError(f"Azure Blob sink endpoint validation failed: {exc}") from exc
    elif "account_url" in options:
        # Fallback: validate account_url if present in options to prevent bypass
        try:
            security_level = context.security_level if context else None
            validate_azure_blob_endpoint(
                endpoint=options["account_url"],
                security_level=security_level,
            )
            logger.debug(f"Azure Blob endpoint validated: {options['account_url']}")
        except ValueError as exc:
            logger.error(f"Azure Blob endpoint validation failed: {exc}")
            raise ConfigurationError(f"Azure Blob sink endpoint validation failed: {exc}") from exc

    return BlobResultSink(**options)


def _create_azure_blob_artifacts_sink(options: dict[str, Any], context: PluginContext) -> AzureBlobArtifactsSink:
    """Create Azure Blob artifacts publisher sink (folder upload)."""
    return AzureBlobArtifactsSink(**options)


def _create_csv_sink(options: dict[str, Any], context: PluginContext) -> CsvResultSink:
    """Create CSV result sink."""
    # Fast-path: prefer already-loaded module to avoid import overhead
    mod = _modules.get("elspeth.plugins.nodes.sinks.csv_file")
    if mod is not None:
        try:
            klass = getattr(mod, "CsvResultSink", CsvResultSink)
            return klass(**options)
        except Exception:
            return CsvResultSink(**options)

    # Fallback: use package export (lazy import via __getattr__ may load the module)
    try:
        return CsvResultSink(**options)
    except Exception:
        # As a last resort, attempt an explicit import
        try:
            from elspeth.plugins.nodes.sinks import csv_file as _csv_mod

            klass = getattr(_csv_mod, "CsvResultSink", CsvResultSink)
            return klass(**options)
        except Exception:
            return CsvResultSink(**options)


def _create_local_bundle_sink(options: dict[str, Any], context: PluginContext) -> LocalBundleSink:
    """Create local bundle result sink."""
    return LocalBundleSink(**options)


def _create_excel_sink(options: dict[str, Any], context: PluginContext) -> ExcelResultSink:
    """Create Excel workbook result sink."""
    return ExcelResultSink(**options)


def _create_zip_bundle_sink(options: dict[str, Any], context: PluginContext) -> ZipResultSink:
    """Create ZIP bundle result sink."""
    return ZipResultSink(**options)


def _create_file_copy_sink(options: dict[str, Any], context: PluginContext) -> FileCopySink:
    """Create file copy sink."""
    return FileCopySink(**options)


def _create_github_repo_sink(options: dict[str, Any], context: PluginContext) -> GitHubRepoSink:
    """Create GitHub repository sink."""
    return GitHubRepoSink(**options)


def _create_azure_devops_repo_sink(options: dict[str, Any], context: PluginContext) -> AzureDevOpsRepoSink:
    """Create Azure DevOps repository sink."""
    return AzureDevOpsRepoSink(**options)


def _create_azure_devops_artifacts_repo_sink(options: dict[str, Any], context: PluginContext) -> AzureDevOpsArtifactsRepoSink:
    """Create Azure DevOps Artifacts repo publisher sink (folder upload)."""
    return AzureDevOpsArtifactsRepoSink(**options)


def _create_signed_artifact_sink(options: dict[str, Any], context: PluginContext) -> SignedArtifactSink:
    """Create signed artifact sink."""
    return SignedArtifactSink(**options)


def _create_analytics_report_sink(options: dict[str, Any], context: PluginContext) -> AnalyticsReportSink:
    """Create analytics report sink."""
    return AnalyticsReportSink(**options)


def _create_visual_analytics_sink(options: dict[str, Any], context: PluginContext) -> VisualAnalyticsSink:
    """Create visual analytics sink."""
    return VisualAnalyticsSink(
        base_path=options["base_path"],
        file_stem=options.get("file_stem", "analytics_visual"),
        formats=options.get("formats"),
        dpi=int(options.get("dpi", 150)),
        figure_size=options.get("figure_size"),
        include_table=options.get("include_table", True),
        bar_color=options.get("bar_color"),
        chart_title=options.get("chart_title"),
        seaborn_style=options.get("seaborn_style", "darkgrid"),
        on_error=options.get("on_error", "abort"),
    )


def _create_enhanced_visual_sink(options: dict[str, Any], context: PluginContext) -> EnhancedVisualAnalyticsSink:
    """Create enhanced visual analytics sink."""
    return EnhancedVisualAnalyticsSink(
        base_path=options["base_path"],
        file_stem=options.get("file_stem", "enhanced_visual"),
        formats=options.get("formats"),
        chart_types=options.get("chart_types"),
        dpi=int(options.get("dpi", 150)),
        figure_size=options.get("figure_size"),
        seaborn_style=options.get("seaborn_style", "darkgrid"),
        color_palette=options.get("color_palette", "Set2"),
        on_error=options.get("on_error", "abort"),
    )


def _create_embeddings_store_sink(options: dict[str, Any], context: PluginContext) -> EmbeddingsStoreSink:
    """Create embeddings store sink."""
    return EmbeddingsStoreSink(
        provider=options["provider"],
        namespace=options.get("namespace"),
        dsn=options.get("dsn"),
        table=options.get("table", "elspeth_rag"),
        text_field=options.get("text_field", DEFAULT_TEXT_FIELD),
        embedding_source=options.get("embedding_source", DEFAULT_EMBEDDING_FIELD),
        embed_model=options.get("embed_model"),
        metadata_fields=options.get("metadata_fields"),
        id_field=options.get("id_field", DEFAULT_ID_FIELD),
        batch_size=options.get("batch_size", 50),
        upsert_conflict=options.get("upsert_conflict", "replace"),
        provider_options={
            key: options.get(key)
            for key in (
                "endpoint",
                "index",
                "api_key",
                "api_key_env",
                "vector_field",
                "namespace_field",
                "id_field",
            )
            if options.get(key) is not None
        },
    )


def _create_reproducibility_bundle_sink(options: dict[str, Any], context: PluginContext) -> ReproducibilityBundleSink:
    """Create reproducibility bundle sink for complete audit trail."""
    return ReproducibilityBundleSink(**options)


# ============================================================================
# Schema Definitions
# ============================================================================


# Helper to build sink schemas with common properties
def _sink_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build a sink schema with security, determinism, artifacts, and error handling."""
    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": True,
    }
    schema = with_security_properties(schema, require_security=False, require_determinism=False)
    schema = with_artifact_properties(schema)
    schema = with_error_handling(schema)
    return schema


_AZURE_BLOB_SINK_SCHEMA = _sink_schema(
    {
        "config_path": {"type": "string"},
        "profile": {"type": "string"},
        "path_template": {"type": "string"},
        "filename": {"type": "string"},
        "manifest_template": {"type": "string"},
        "manifest_suffix": {"type": "string"},
        "include_manifest": {"type": "boolean"},
        "overwrite": {"type": "boolean"},
        "metadata": {"type": "object"},
        "upload_chunk_size": {"type": "integer", "minimum": 0},
        "credential": {},
        "credential_env": {"type": "string"},
        "content_type": {"type": "string"},
    },
    ["config_path"],
)

_AZURE_BLOB_ARTIFACTS_SINK_SCHEMA = _sink_schema(
    {
        "config_path": {"type": "string"},
        "profile": {"type": "string"},
        "path_template": {"type": "string"},
        "folder_path": {"type": "string"},
        "metadata": {"type": "object"},
        "upload_chunk_size": {"type": "integer", "minimum": 0},
        "content_type_map": {"type": "object"},
    },
    ["config_path", "folder_path"],
)

_CSV_SINK_SCHEMA = _sink_schema(
    {
        "path": {"type": "string"},
        "overwrite": {"type": "boolean"},
        "sanitize_formulas": {"type": "boolean"},
        "sanitize_guard": {"type": "string", "minLength": 1, "maxLength": 1},
        "allowed_base_path": {"type": "string"},
    },
    ["path"],
)

_LOCAL_BUNDLE_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "bundle_name": {"type": "string"},
        "timestamped": {"type": "boolean"},
        "write_json": {"type": "boolean"},
        "write_csv": {"type": "boolean"},
        "sanitize_formulas": {"type": "boolean"},
        "sanitize_guard": {"type": "string", "minLength": 1, "maxLength": 1},
        "allowed_base_path": {"type": "string"},
    },
    ["base_path"],
)

_EXCEL_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "workbook_name": {"type": "string"},
        "timestamped": {"type": "boolean"},
        "results_sheet": {"type": "string"},
        "manifest_sheet": {"type": "string"},
        "aggregates_sheet": {"type": "string"},
        "include_manifest": {"type": "boolean"},
        "include_aggregates": {"type": "boolean"},
        "sanitize_formulas": {"type": "boolean"},
        "sanitize_guard": {"type": "string", "minLength": 1, "maxLength": 1},
        "allowed_base_path": {"type": "string"},
    },
    ["base_path"],
)

_ZIP_BUNDLE_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "bundle_name": {"type": "string"},
        "timestamped": {"type": "boolean"},
        "include_manifest": {"type": "boolean"},
        "include_results": {"type": "boolean"},
        "include_csv": {"type": "boolean"},
        "manifest_name": {"type": "string"},
        "results_name": {"type": "string"},
        "csv_name": {"type": "string"},
        "allowed_base_path": {"type": "string"},
    },
    ["base_path"],
)

_FILE_COPY_SINK_SCHEMA = _sink_schema(
    {
        "destination": {"type": "string"},
        "overwrite": {"type": "boolean"},
        "allowed_base_path": {"type": "string"},
    },
    ["destination"],
)

_GITHUB_REPO_SINK_SCHEMA = _sink_schema(
    {
        "path_template": {"type": "string"},
        "commit_message_template": {"type": "string"},
        "include_manifest": {"type": "boolean"},
        "owner": {"type": "string"},
        "repo": {"type": "string"},
        "branch": {"type": "string"},
        "token_env": {"type": "string"},
        "dry_run": {"type": "boolean"},
    },
    ["owner", "repo"],
)

_AZURE_DEVOPS_REPO_SINK_SCHEMA = _sink_schema(
    {
        "path_template": {"type": "string"},
        "commit_message_template": {"type": "string"},
        "include_manifest": {"type": "boolean"},
        "organization": {"type": "string"},
        "project": {"type": "string"},
        "repository": {"type": "string"},
        "branch": {"type": "string"},
        "token_env": {"type": "string"},
        "api_version": {"type": "string"},
        "base_url": {"type": "string"},
        "dry_run": {"type": "boolean"},
    },
    ["organization", "project", "repository"],
)

_AZURE_DEVOPS_ARTIFACTS_REPO_SINK_SCHEMA = _sink_schema(
    {
        "folder_path": {"type": "string"},
        "dest_prefix_template": {"type": "string"},
        "commit_message_template": {"type": "string"},
        "organization": {"type": "string"},
        "project": {"type": "string"},
        "repository": {"type": "string"},
        "branch": {"type": "string"},
        "token_env": {"type": "string"},
        "api_version": {"type": "string"},
        "base_url": {"type": "string"},
        "dry_run": {"type": "boolean"},
    },
    ["folder_path", "organization", "project", "repository"],
)

_SIGNED_ARTIFACT_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "bundle_name": {"type": "string"},
        "key": {"type": "string"},
        "key_env": {"type": "string"},
        "hash_algorithm": {"type": "string"},
    },
    ["base_path"],
)

_ANALYTICS_REPORT_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "file_stem": {"type": "string"},
        "formats": {
            "type": "array",
            "items": {"type": "string", "enum": ["json", "md", "markdown"]},
        },
        "include_metadata": {"type": "boolean"},
        "include_aggregates": {"type": "boolean"},
        "include_comparisons": {"type": "boolean"},
    },
    ["base_path"],
)

_VISUAL_ANALYTICS_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "file_stem": {"type": "string"},
        "formats": {
            "type": "array",
            "items": {"type": "string", "enum": ["png", "html"]},
        },
        "dpi": {"type": "integer", "minimum": 50},
        "figure_size": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
        },
        "include_table": {"type": "boolean"},
        "bar_color": {"type": "string"},
        "chart_title": {"type": "string"},
        "seaborn_style": {"type": "string"},
    },
    ["base_path"],
)

_ENHANCED_VISUAL_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "file_stem": {"type": "string"},
        "formats": {
            "type": "array",
            "items": {"type": "string", "enum": ["png", "html"]},
        },
        "chart_types": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["violin", "box", "heatmap", "forest", "distribution"],
            },
        },
        "dpi": {"type": "integer", "minimum": 50},
        "figure_size": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
        },
        "seaborn_style": {"type": "string"},
        "color_palette": {"type": "string"},
    },
    ["base_path"],
)

_EMBEDDINGS_STORE_SINK_SCHEMA = with_security_properties(
    {
        "type": "object",
        "properties": {
            "provider": {"type": "string"},
            "namespace": {"type": "string"},
            "dsn": {"type": "string"},
            "table": {"type": "string"},
            "text_field": {"type": "string"},
            "embedding_source": {"type": "string"},
            "embed_model": {"type": "object"},
            "metadata_fields": {"type": "array", "items": {"type": "string"}},
            "id_field": {"type": "string"},
            "batch_size": {"type": "integer", "minimum": 1},
            "upsert_conflict": {"type": "string", "enum": ["replace", "skip", "merge"]},
            "endpoint": {"type": "string"},
            "index": {"type": "string"},
            "api_key": {"type": "string"},
            "api_key_env": {"type": "string"},
            "vector_field": {"type": "string"},
            "namespace_field": {"type": "string"},
        },
        "required": ["provider"],
        "additionalProperties": True,
    },
    require_security=False,
    require_determinism=False,
)
_EMBEDDINGS_STORE_SINK_SCHEMA = with_artifact_properties(_EMBEDDINGS_STORE_SINK_SCHEMA)

_REPRODUCIBILITY_BUNDLE_SINK_SCHEMA = _sink_schema(
    {
        "base_path": {"type": "string"},
        "bundle_name": {"type": "string"},
        "timestamped": {"type": "boolean"},
        "include_results_json": {"type": "boolean"},
        "include_results_csv": {"type": "boolean"},
        "include_source_data": {"type": "boolean"},
        "include_config": {"type": "boolean"},
        "include_prompts": {"type": "boolean"},
        "include_plugins": {"type": "boolean"},
        "include_framework_code": {"type": "boolean"},
        "algorithm": {"type": "string", "enum": ["hmac-sha256", "hmac-sha512"]},
        "key": {"type": "string"},
        "key_env": {"type": "string"},
        "compression": {"type": "string", "enum": ["gz", "bz2", "xz", "none"]},
        "sanitize_formulas": {"type": "boolean"},
        "sanitize_guard": {"type": "string", "minLength": 1, "maxLength": 1},
    },
    ["base_path"],
)


# ============================================================================
# Register Sinks
# ============================================================================

sink_registry.register("azure_blob", _create_azure_blob_sink, schema=_AZURE_BLOB_SINK_SCHEMA)
sink_registry.register("azure_blob_artifacts", _create_azure_blob_artifacts_sink, schema=_AZURE_BLOB_ARTIFACTS_SINK_SCHEMA)
sink_registry.register("csv", _create_csv_sink, schema=_CSV_SINK_SCHEMA)
sink_registry.register("local_bundle", _create_local_bundle_sink, schema=_LOCAL_BUNDLE_SINK_SCHEMA)
sink_registry.register("excel_workbook", _create_excel_sink, schema=_EXCEL_SINK_SCHEMA)
sink_registry.register("zip_bundle", _create_zip_bundle_sink, schema=_ZIP_BUNDLE_SINK_SCHEMA)
sink_registry.register("file_copy", _create_file_copy_sink, schema=_FILE_COPY_SINK_SCHEMA)
sink_registry.register("github_repo", _create_github_repo_sink, schema=_GITHUB_REPO_SINK_SCHEMA)
sink_registry.register("azure_devops_repo", _create_azure_devops_repo_sink, schema=_AZURE_DEVOPS_REPO_SINK_SCHEMA)
sink_registry.register(
    "azure_devops_artifact_repo",
    _create_azure_devops_artifacts_repo_sink,
    schema=_AZURE_DEVOPS_ARTIFACTS_REPO_SINK_SCHEMA,
    capabilities={CAP_SUPPORTS_FOLDER_PATH_INJECTION},
)
sink_registry.register("signed_artifact", _create_signed_artifact_sink, schema=_SIGNED_ARTIFACT_SINK_SCHEMA)
sink_registry.register("analytics_report", _create_analytics_report_sink, schema=_ANALYTICS_REPORT_SINK_SCHEMA)
sink_registry.register("analytics_visual", _create_visual_analytics_sink, schema=_VISUAL_ANALYTICS_SINK_SCHEMA)
sink_registry.register("enhanced_visual", _create_enhanced_visual_sink, schema=_ENHANCED_VISUAL_SINK_SCHEMA)
sink_registry.register("embeddings_store", _create_embeddings_store_sink, schema=_EMBEDDINGS_STORE_SINK_SCHEMA)
sink_registry.register("reproducibility_bundle", _create_reproducibility_bundle_sink, schema=_REPRODUCIBILITY_BUNDLE_SINK_SCHEMA)


# ============================================================================
# Public API
# ============================================================================

__all__ = [
    "sink_registry",
    "CAP_SUPPORTS_FOLDER_PATH_INJECTION",
]
