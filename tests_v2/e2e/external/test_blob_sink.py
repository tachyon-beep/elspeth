# tests_v2/e2e/external/test_blob_sink.py
"""E2E tests for Azure Blob Storage sink plugin.

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


class TestBlobSink:
    """Azure Blob Storage sink plugin E2E tests."""

    def test_blob_sink_writes_csv_data(self) -> None:
        """Blob sink writes CSV data to Azure Blob Storage."""
        pytest.skip("Requires Azurite emulator or Azure credentials")

    def test_blob_sink_writes_json_data(self) -> None:
        """Blob sink writes JSON data to Azure Blob Storage."""
        pytest.skip("Requires Azurite emulator or Azure credentials")

    def test_blob_sink_overwrites_existing_blob(self) -> None:
        """Blob sink can overwrite an existing blob when configured."""
        pytest.skip("Requires Azurite emulator or Azure credentials")

    def test_blob_sink_creates_new_blob(self) -> None:
        """Blob sink creates a new blob in the container."""
        pytest.skip("Requires Azurite emulator or Azure credentials")
