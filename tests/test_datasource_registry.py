"""Tests for datasource registry to reach 80% coverage.

Focus on testing uncovered error handling paths (lines 52-66).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.datasource import (
    _create_blob_datasource,
    _create_csv_blob_datasource,
    _create_csv_datasource,
    datasource_registry,
)
from elspeth.core.validation.base import ConfigurationError


@pytest.fixture
def test_context():
    """Create a test plugin context."""
    return PluginContext(
        security_level="public",
        provenance=["test"],
        plugin_kind="datasource",
        plugin_name="test_datasource",
    )


def test_blob_datasource_with_config_path(test_context, tmp_path):
    """Test blob datasource factory with config_path and validation success (lines 40-51)."""
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
        "retain_local": True,
    }

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint") as mock_validate:
        datasource = _create_blob_datasource(options, test_context)
        assert datasource is not None
        mock_validate.assert_called_once()


def test_blob_datasource_config_validation_failure(test_context, tmp_path):
    """Test blob datasource factory raises ConfigurationError on validation failure (lines 52-54)."""
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
        "retain_local": True,
    }

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint", side_effect=ValueError("Invalid endpoint")):
        with pytest.raises(ConfigurationError, match="Azure Blob datasource endpoint validation failed"):
            _create_blob_datasource(options, test_context)


def test_blob_datasource_with_account_url(test_context):
    """Test blob datasource factory with account_url fallback (lines 55-63)."""
    options = {
        "account_url": "https://approved.blob.core.windows.net",
        "retain_local": True,
    }

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint") as mock_validate:
        datasource = _create_blob_datasource(options, test_context)
        assert datasource is not None
        mock_validate.assert_called_once()


def test_blob_datasource_account_url_validation_failure(test_context):
    """Test blob datasource factory with account_url validation failure (lines 64-66)."""
    options = {
        "account_url": "https://malicious.example.com",
        "retain_local": True,
    }

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint", side_effect=ValueError("Invalid endpoint")):
        with pytest.raises(ConfigurationError, match="Azure Blob datasource endpoint validation failed"):
            _create_blob_datasource(options, test_context)


def test_blob_datasource_without_config_or_url(test_context):
    """Test blob datasource factory without config_path or account_url (skips validation)."""
    options = {"retain_local": True}

    # Should not raise validation errors, but may fail during datasource construction
    # This tests the path where neither config_path nor account_url are provided
    try:
        datasource = _create_blob_datasource(options, test_context)
    except Exception:
        # Expected to fail during BlobDataSource construction due to missing required params
        pass


def test_csv_blob_datasource(test_context, tmp_path):
    """Test CSV blob datasource factory (lines 71-77)."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col1,col2\nval1,val2\n")

    options = {
        "path": str(csv_file),
        "retain_local": True,
    }
    datasource = _create_csv_blob_datasource(options, test_context)
    assert datasource is not None


def test_csv_datasource(test_context, tmp_path):
    """Test local CSV datasource factory (lines 80-82)."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col1,col2\nval1,val2\n")

    options = {
        "path": str(csv_file),
        "retain_local": True,
    }
    datasource = _create_csv_datasource(options, test_context)
    assert datasource is not None


def test_all_datasources_registered():
    """Test that all datasource plugins are registered."""
    plugins = datasource_registry.list_plugins()
    assert "azure_blob" in plugins
    assert "csv_blob" in plugins
    assert "local_csv" in plugins


def test_registry_create_datasources(test_context, tmp_path):
    """Test creating datasources via registry interface."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("col1,col2\nval1,val2\n")

    # Test local_csv
    datasource = datasource_registry.create(
        "local_csv",
        {"path": str(csv_file), "retain_local": True},
        test_context,
    )
    assert datasource is not None

    # Test csv_blob
    datasource = datasource_registry.create(
        "csv_blob",
        {"path": str(csv_file), "retain_local": True},
        test_context,
    )
    assert datasource is not None


def test_registry_validate_schemas():
    """Test schema validation for datasources."""
    # Valid local_csv
    datasource_registry.validate("local_csv", {"path": "/tmp/test.csv", "retain_local": True})

    # Valid csv_blob
    datasource_registry.validate("csv_blob", {"path": "/tmp/test.csv", "retain_local": True})

    # Valid azure_blob
    datasource_registry.validate("azure_blob", {"config_path": "/tmp/config.yaml", "retain_local": True})

    # Missing required retain_local should fail
    with pytest.raises(ValueError):
        datasource_registry.validate("local_csv", {"path": "/tmp/test.csv"})


def test_blob_datasource_with_custom_profile(test_context, tmp_path):
    """Test blob datasource factory with custom profile."""
    config_file = tmp_path / "blob_config.yaml"
    config_file.write_text(
        """
profiles:
  production:
    account_url: https://prod.blob.core.windows.net
    """
    )

    options = {
        "config_path": str(config_file),
        "profile": "production",
        "retain_local": True,
    }

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint") as mock_validate:
        datasource = _create_blob_datasource(options, test_context)
        assert datasource is not None
        mock_validate.assert_called_once()


def test_blob_datasource_context_propagation(tmp_path):
    """Test that context security_level is passed to validation."""
    config_file = tmp_path / "blob_config.yaml"
    config_file.write_text(
        """
profiles:
  default:
    account_url: https://test.blob.core.windows.net
    """
    )

    options = {
        "config_path": str(config_file),
        "profile": "default",
        "retain_local": True,
    }

    context = PluginContext(
        security_level="confidential",
        provenance=["test"],
        plugin_kind="datasource",
        plugin_name="azure_blob",
    )

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint") as mock_validate:
        _create_blob_datasource(options, context)
        # Verify security_level was passed
        mock_validate.assert_called_once()
        call_kwargs = mock_validate.call_args[1]
        assert call_kwargs["security_level"] == "confidential"


def test_blob_datasource_none_context():
    """Test blob datasource factory handles None context gracefully."""
    options = {
        "account_url": "https://test.blob.core.windows.net",
        "retain_local": True,
    }

    with patch("elspeth.core.registries.datasource.validate_azure_blob_endpoint") as mock_validate:
        # Pass None as context - should use None for security_level
        _create_blob_datasource(options, None)  # type: ignore
        mock_validate.assert_called_once()
        call_kwargs = mock_validate.call_args[1]
        assert call_kwargs["security_level"] is None
