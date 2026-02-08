# tests_v2/e2e/external/test_blob_source.py
"""E2E tests for Azure Blob Storage source plugin.

These tests require either:
  - Azurite emulator running locally, OR
  - Azure Blob Storage credentials via environment variables

Skipped by default in CI unless the test infrastructure is available.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skipif(
    True,  # TODO: Check for Azurite availability or Azure credentials
    reason="Requires Azurite emulator or Azure Blob Storage credentials",
)


class TestBlobSource:
    """Azure Blob Storage source plugin E2E tests."""

    def test_blob_source_reads_csv_data(self) -> None:
        """Blob source reads CSV data from Azure Blob Storage."""
        pytest.skip("Requires Azurite emulator or Azure credentials")

    def test_blob_source_reads_json_data(self) -> None:
        """Blob source reads JSON data from Azure Blob Storage."""
        pytest.skip("Requires Azurite emulator or Azure credentials")

    def test_blob_source_handles_missing_blob(self) -> None:
        """Blob source raises appropriate error for missing blob."""
        pytest.skip("Requires Azurite emulator or Azure credentials")

    def test_blob_source_handles_empty_blob(self) -> None:
        """Blob source handles empty blob gracefully."""
        pytest.skip("Requires Azurite emulator or Azure credentials")
