"""Coverage tests for datasource registry to reach 80% threshold."""

from unittest.mock import MagicMock, patch

import pytest

from elspeth.core.base.plugin_context import PluginContext
from elspeth.core.registries.datasource import datasource_registry
from elspeth.core.validation.base import ConfigurationError


def test_blob_datasource_load_config_failure():
    """Test blob datasource when load_blob_config raises ValueError - lines 52-54."""
    context = PluginContext(
        plugin_name="test_ds",
        plugin_kind="datasource",
        security_level="internal",
        determinism_level="guaranteed",
    )

    # Mock load_blob_config to raise ValueError
    with patch("elspeth.core.registries.datasource.load_blob_config") as mock_load:
        mock_load.side_effect = ValueError("Invalid blob config")

        with pytest.raises(ConfigurationError, match="Azure Blob datasource endpoint validation failed"):
            datasource_registry.create(
                "azure_blob",
                {
                    "config_path": "/fake/config.yaml",
                    "profile": "default",
                    "retain_local": True,
                },
                parent_context=context,
            )


# Note: Lines 55-68 (account_url fallback) are unreachable
# The schema requires config_path, so the elif branch is dead code


def test_csv_blob_datasource_creation():
    """Test CSV blob datasource factory - line 77."""
    context = PluginContext(
        plugin_name="test_ds",
        plugin_kind="datasource",
        security_level="internal",
        determinism_level="guaranteed",
    )

    with patch("elspeth.core.registries.datasource.CSVBlobDataSource") as mock_csv_blob:
        mock_csv_blob.return_value = MagicMock()  # Return an object that can have attrs set

        result = datasource_registry.create(
            "csv_blob",
            {
                "path": "/fake/data.csv",
                "retain_local": True,
            },
            parent_context=context,
        )

        # Verify factory was called and object returned
        mock_csv_blob.assert_called_once()
        assert result is not None


def test_local_csv_datasource_creation():
    """Test local CSV datasource factory - line 82."""
    context = PluginContext(
        plugin_name="test_ds",
        plugin_kind="datasource",
        security_level="internal",
        determinism_level="guaranteed",
    )

    with patch("elspeth.core.registries.datasource.CSVDataSource") as mock_csv:
        mock_csv.return_value = MagicMock()  # Return an object that can have attrs set

        result = datasource_registry.create(
            "local_csv",
            {
                "path": "/fake/data.csv",
                "retain_local": True,
            },
            parent_context=context,
        )

        # Verify factory was called and object returned
        mock_csv.assert_called_once()
        assert result is not None
