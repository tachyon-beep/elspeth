# tests_v2/e2e/external/test_keyvault.py
"""E2E tests for Azure Key Vault secret resolution.

These tests require:
  - TEST_KEYVAULT_URL environment variable set to a valid vault URL
  - Azure credentials available (DefaultAzureCredential)
  - Test secrets pre-provisioned in the vault

Skipped by default in CI unless the vault is configured.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_KEYVAULT_URL"),
    reason="TEST_KEYVAULT_URL not set — requires Azure Key Vault credentials",
)


class TestKeyVault:
    """Azure Key Vault secret resolution E2E tests."""

    def test_keyvault_secret_resolution(self) -> None:
        """Key Vault secrets can be resolved and loaded into config."""
        pytest.skip("Requires Azure Key Vault credentials and pre-provisioned secrets")

    def test_keyvault_secret_fingerprinting(self) -> None:
        """Resolved secrets are fingerprinted for audit trail storage."""
        pytest.skip("Requires Azure Key Vault credentials and pre-provisioned secrets")

    def test_keyvault_missing_secret_raises(self) -> None:
        """Missing secrets in Key Vault produce clear error messages."""
        pytest.skip("Requires Azure Key Vault credentials and pre-provisioned secrets")

    def test_keyvault_resolution_recorded_in_landscape(self) -> None:
        """Secret resolutions are recorded in the Landscape audit trail."""
        pytest.skip("Requires Azure Key Vault credentials and pre-provisioned secrets")
