"""Tier 1 strictness regression tests for secrets response schemas.

The secrets API's response models serialize system-owned metadata —
secret names, scopes, resolvability flags.  The request-side schema
(``CreateSecretRequest``) remains a plain ``BaseModel`` because it is a
Tier 3 boundary; its own field validators already perform the relevant
boundary checks.

These tests verify that Tier 1 responses reject coercion and extra
fields, mirroring the execution module's strictness contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from elspeth.web.secrets.schemas import (
    CreateSecretResponse,
    SecretInventoryResponse,
    ValidateSecretResponse,
)


class TestSecretStrictCoercionRejected:
    def test_inventory_rejects_string_bool_available(self) -> None:
        with pytest.raises(ValidationError):
            SecretInventoryResponse(
                name="n",
                scope="user",
                available="true",  # type: ignore[arg-type]
                source_kind="env",
            )

    def test_inventory_rejects_int_for_source_kind(self) -> None:
        with pytest.raises(ValidationError):
            SecretInventoryResponse(
                name="n",
                scope="user",
                available=True,
                source_kind=42,  # type: ignore[arg-type]
            )

    def test_create_response_rejects_string_bool_available(self) -> None:
        with pytest.raises(ValidationError):
            CreateSecretResponse(name="n", scope="user", available="false")  # type: ignore[arg-type]

    def test_validate_response_rejects_string_bool_available(self) -> None:
        with pytest.raises(ValidationError):
            ValidateSecretResponse(name="n", available="yes")  # type: ignore[arg-type]


class TestSecretExtraFieldsRejected:
    def test_inventory_rejects_extra(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            SecretInventoryResponse(
                name="n",
                scope="user",
                available=True,
                source_kind="env",
                value="super-secret",  # type: ignore[call-arg]
            )

    def test_create_response_rejects_extra(self) -> None:
        """Regression guard — ``value`` must NEVER be silently accepted on
        a secret write-acknowledgement response.  ``extra="forbid"`` makes
        the class contract enforce what the docstring promises.
        """
        with pytest.raises(ValidationError, match="extra"):
            CreateSecretResponse(
                name="n",
                scope="user",
                available=True,
                value="super-secret",  # type: ignore[call-arg]
            )

    def test_validate_response_rejects_extra(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            ValidateSecretResponse(name="n", available=True, value="secret")  # type: ignore[call-arg]


class TestSecretResponseHappyPath:
    def test_inventory_with_defaults(self) -> None:
        resp = SecretInventoryResponse(name="api_key", scope="user", available=True)
        assert resp.source_kind == ""

    def test_create_response(self) -> None:
        resp = CreateSecretResponse(name="api_key", scope="user", available=True)
        assert resp.available is True

    def test_validate_response(self) -> None:
        resp = ValidateSecretResponse(name="api_key", available=False)
        assert resp.available is False
