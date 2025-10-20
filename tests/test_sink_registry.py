"""Tests for sink registry to reach 80% coverage.

Focus on testing uncovered factory functions (lines 67-98, 103, 114-115, 120-128,
138, 143, 153, 158, 163, 168, 173, 178, 194, 209, 239).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.sink import (
    _create_analytics_report_sink,
    _create_azure_blob_artifacts_sink,
    _create_azure_blob_sink,
    _create_azure_devops_artifacts_repo_sink,
    _create_azure_devops_repo_sink,
    _create_csv_sink,
    _create_embeddings_store_sink,
    _create_enhanced_visual_sink,
    _create_excel_sink,
    _create_file_copy_sink,
    _create_github_repo_sink,
    _create_local_bundle_sink,
    _create_reproducibility_bundle_sink,
    _create_signed_artifact_sink,
    _create_visual_analytics_sink,
    _create_zip_bundle_sink,
    sink_registry,
)
from elspeth.core.validation.base import ConfigurationError


@pytest.fixture
def test_context():
    """Create a test plugin context."""
    return PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="sink",
        plugin_name="test_sink",
    )


def test_azure_blob_sink_with_config_path(test_context, tmp_path):
    """Test Azure Blob sink factory with config_path (lines 67-98)."""
    config_file = tmp_path / "blob_config.yaml"
    config_file.write_text(
        """
profiles:
  default:
    account_url: https://approved.blob.core.windows.net
    """
    )

    options = {
        "config_path": str(config_file),
        "profile": "default",
        "path_template": "test/{experiment_id}.csv",
    }

    with patch("elspeth.core.registries.sink.validate_azure_blob_endpoint") as mock_validate:
        sink = _create_azure_blob_sink(options, test_context)
        assert sink is not None
        mock_validate.assert_called_once()


def test_azure_blob_sink_config_validation_failure(test_context, tmp_path):
    """Test Azure Blob sink factory raises ConfigurationError on validation failure (lines 82-84)."""
    config_file = tmp_path / "blob_config.yaml"
    config_file.write_text(
        """
profiles:
  default:
    account_url: https://malicious.example.com
    """
    )

    options = {
        "config_path": str(config_file),
        "profile": "default",
    }

    with patch("elspeth.core.registries.sink.validate_azure_blob_endpoint", side_effect=ValueError("Invalid endpoint")):
        with pytest.raises(ConfigurationError, match="Azure Blob sink endpoint validation failed"):
            _create_azure_blob_sink(options, test_context)


def test_azure_blob_sink_with_account_url(test_context):
    """Test Azure Blob sink factory with account_url fallback (lines 85-96)."""
    options = {
        "account_url": "https://approved.blob.core.windows.net",
        "path_template": "test/{experiment_id}.csv",
    }

    with patch("elspeth.core.registries.sink.validate_azure_blob_endpoint") as mock_validate:
        sink = _create_azure_blob_sink(options, test_context)
        assert sink is not None
        mock_validate.assert_called_once()


def test_azure_blob_sink_account_url_validation_failure(test_context):
    """Test Azure Blob sink factory with account_url validation failure (lines 94-96)."""
    options = {
        "account_url": "https://malicious.example.com",
    }

    with patch("elspeth.core.registries.sink.validate_azure_blob_endpoint", side_effect=ValueError("Invalid endpoint")):
        with pytest.raises(ConfigurationError, match="Azure Blob sink endpoint validation failed"):
            _create_azure_blob_sink(options, test_context)


def test_azure_blob_artifacts_sink(test_context):
    """Test Azure Blob artifacts sink factory (line 103)."""
    options = {
        "config_path": "/path/to/config.yaml",
        "folder_path": "/artifacts",
    }
    sink = _create_azure_blob_artifacts_sink(options, test_context)
    assert sink is not None


def test_csv_sink_happy_path(test_context, tmp_path):
    """Test CSV sink factory happy path (line 113)."""
    options = {"path": str(tmp_path / "output.csv")}
    sink = _create_csv_sink(options, test_context)
    assert sink is not None


def test_csv_sink_fast_path_with_loaded_module(test_context, tmp_path):
    """Test CSV sink factory fast path when module is already loaded (lines 109-115)."""
    import sys

    from elspeth.plugins.nodes.sinks import csv_file

    # Ensure module is in sys.modules
    assert "elspeth.plugins.nodes.sinks.csv_file" in sys.modules

    options = {"path": str(tmp_path / "output.csv")}
    sink = _create_csv_sink(options, test_context)
    assert sink is not None


def test_csv_sink_fallback_paths(test_context, tmp_path, monkeypatch):
    """Test CSV sink factory fallback import paths (lines 118-128)."""
    import sys

    # Remove module from sys.modules to force fallback
    original_modules = sys.modules.copy()
    try:
        # Force fallback by simulating module not in sys.modules
        if "elspeth.plugins.nodes.sinks.csv_file" in sys.modules:
            del sys.modules["elspeth.plugins.nodes.sinks.csv_file"]

        options = {"path": str(tmp_path / "output.csv")}
        sink = _create_csv_sink(options, test_context)
        assert sink is not None
    finally:
        # Restore modules
        sys.modules.update(original_modules)


def test_local_bundle_sink(test_context, tmp_path):
    """Test local bundle sink factory (line 133)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_local_bundle_sink(options, test_context)
    assert sink is not None


def test_excel_sink(test_context, tmp_path):
    """Test Excel sink factory (line 138)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_excel_sink(options, test_context)
    assert sink is not None


def test_zip_bundle_sink(test_context, tmp_path):
    """Test ZIP bundle sink factory (line 143)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_zip_bundle_sink(options, test_context)
    assert sink is not None


def test_file_copy_sink(test_context, tmp_path):
    """Test file copy sink factory (line 148)."""
    options = {"destination": str(tmp_path / "copy")}
    sink = _create_file_copy_sink(options, test_context)
    assert sink is not None


def test_github_repo_sink(test_context):
    """Test GitHub repo sink factory (line 153)."""
    options = {
        "owner": "test-owner",
        "repo": "test-repo",
        "path_template": "results/{experiment_id}.csv",
    }
    sink = _create_github_repo_sink(options, test_context)
    assert sink is not None


def test_azure_devops_repo_sink(test_context):
    """Test Azure DevOps repo sink factory (line 158)."""
    options = {
        "organization": "test-org",
        "project": "test-project",
        "repository": "test-repo",
        "path_template": "results/{experiment_id}.csv",
    }
    sink = _create_azure_devops_repo_sink(options, test_context)
    assert sink is not None


def test_azure_devops_artifacts_repo_sink(test_context):
    """Test Azure DevOps artifacts repo sink factory (line 163)."""
    options = {
        "organization": "test-org",
        "project": "test-project",
        "repository": "test-repo",
        "folder_path": "/artifacts",
    }
    sink = _create_azure_devops_artifacts_repo_sink(options, test_context)
    assert sink is not None


def test_signed_artifact_sink(test_context, tmp_path):
    """Test signed artifact sink factory (line 168)."""
    options = {
        "base_path": str(tmp_path),
        "key_env": "TEST_KEY",
    }
    sink = _create_signed_artifact_sink(options, test_context)
    assert sink is not None


def test_analytics_report_sink(test_context, tmp_path):
    """Test analytics report sink factory (line 173)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_analytics_report_sink(options, test_context)
    assert sink is not None


def test_visual_analytics_sink(test_context, tmp_path):
    """Test visual analytics sink factory (lines 176-189)."""
    options = {
        "base_path": str(tmp_path),
        "file_stem": "test_visual",
        "formats": ["png"],
        "dpi": 200,
        "figure_size": [10, 8],
        "include_table": False,
        "bar_color": "blue",
        "chart_title": "Test Chart",
        "seaborn_style": "whitegrid",
        "on_error": "skip",
    }
    sink = _create_visual_analytics_sink(options, test_context)
    assert sink is not None


def test_visual_analytics_sink_defaults(test_context, tmp_path):
    """Test visual analytics sink factory with defaults (line 178)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_visual_analytics_sink(options, test_context)
    assert sink is not None


def test_enhanced_visual_sink(test_context, tmp_path):
    """Test enhanced visual sink factory (lines 192-204)."""
    options = {
        "base_path": str(tmp_path),
        "file_stem": "enhanced",
        "formats": ["html"],
        "chart_types": ["violin", "box"],
        "dpi": 150,
        "figure_size": [12, 10],
        "seaborn_style": "dark",
        "color_palette": "viridis",
        "on_error": "abort",
    }
    sink = _create_enhanced_visual_sink(options, test_context)
    assert sink is not None


def test_enhanced_visual_sink_defaults(test_context, tmp_path):
    """Test enhanced visual sink factory with defaults (line 194)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_enhanced_visual_sink(options, test_context)
    assert sink is not None


def test_embeddings_store_sink(test_context):
    """Test embeddings store sink factory (lines 207-234)."""
    options = {
        "provider": "pgvector",
        "namespace": "test",
        "dsn": "postgresql://localhost/test",
        "table": "embeddings",
        "text_field": "content",
        "embedding_source": "embedding",
        "embed_model": {"type": "azure_openai", "model": "text-embedding-3-small"},
        "metadata_fields": ["title", "author"],
        "id_field": "doc_id",
        "batch_size": 100,
        "upsert_conflict": "merge",
        "endpoint": "https://test.search.windows.net",
        "index": "test-index",
        "api_key_env": "AZURE_SEARCH_KEY",
        "vector_field": "content_vector",
        "namespace_field": "namespace",
    }
    sink = _create_embeddings_store_sink(options, test_context)
    assert sink is not None


def test_embeddings_store_sink_minimal(test_context):
    """Test embeddings store sink factory with minimal options (line 209)."""
    options = {"provider": "pgvector"}
    sink = _create_embeddings_store_sink(options, test_context)
    assert sink is not None


def test_reproducibility_bundle_sink(test_context, tmp_path):
    """Test reproducibility bundle sink factory (line 239)."""
    options = {"base_path": str(tmp_path)}
    sink = _create_reproducibility_bundle_sink(options, test_context)
    assert sink is not None


def test_all_sinks_registered():
    """Test that all sink plugins are registered."""
    plugins = sink_registry.list_plugins()
    expected = {
        "azure_blob",
        "azure_blob_artifacts",
        "csv",
        "local_bundle",
        "excel_workbook",
        "zip_bundle",
        "file_copy",
        "github_repo",
        "azure_devops_repo",
        "azure_devops_artifact_repo",
        "signed_artifact",
        "analytics_report",
        "analytics_visual",
        "enhanced_visual",
        "embeddings_store",
        "reproducibility_bundle",
    }
    assert expected.issubset(set(plugins))


def test_registry_create_csv_sink(test_context, tmp_path):
    """Test creating CSV sink via registry interface."""
    sink = sink_registry.create("csv", {"path": str(tmp_path / "test.csv")}, test_context)
    assert sink is not None


def test_registry_validate_schemas():
    """Test schema validation for various sinks."""
    # CSV sink
    sink_registry.validate("csv", {"path": "/tmp/test.csv"})

    # Excel sink
    sink_registry.validate("excel_workbook", {"base_path": "/tmp"})

    # Visual analytics sink
    sink_registry.validate("analytics_visual", {"base_path": "/tmp"})

    # GitHub repo sink
    sink_registry.validate("github_repo", {"owner": "test", "repo": "test"})
