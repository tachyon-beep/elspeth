# tests/unit/contracts/transform_contracts/test_truncate_contract.py
"""Contract tests for Truncate transform.

Verifies Truncate honors the TransformProtocol contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from elspeth.plugins.transforms.truncate import Truncate
from elspeth.testing import make_pipeline_row
from tests.fixtures.factories import make_context

from .test_transform_protocol import (
    TransformContractPropertyTestBase,
    TransformErrorContractTestBase,
)

if TYPE_CHECKING:
    from elspeth.plugins.protocols import TransformProtocol


class TestTruncateContract(TransformContractPropertyTestBase):
    """Contract tests for Truncate plugin."""

    @pytest.fixture
    def transform(self) -> TransformProtocol:
        """Return a configured transform instance."""
        return Truncate(
            {
                "fields": {"title": 20, "description": 50},
                "schema": {"mode": "observed"},
            }
        )

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        """Return input that should process successfully."""
        return {"title": "Short title", "description": "Short description", "id": 1}


class TestTruncateWithSuffixContract(TransformContractPropertyTestBase):
    """Contract tests for Truncate plugin with suffix."""

    @pytest.fixture
    def transform(self) -> TransformProtocol:
        """Return a configured transform instance with suffix."""
        return Truncate(
            {
                "fields": {"title": 20},
                "suffix": "...",
                "schema": {"mode": "observed"},
            }
        )

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        """Return input that should process successfully."""
        return {"title": "Short", "id": 1}


class TestTruncateStrictContract(TransformErrorContractTestBase):
    """Contract tests for Truncate error handling in strict mode."""

    @pytest.fixture
    def transform(self) -> TransformProtocol:
        """Return a configured transform instance in strict mode."""
        return Truncate(
            {
                "fields": {"required_field": 100},
                "strict": True,
                "schema": {"mode": "observed"},
            }
        )

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        """Return input that should process successfully (has required field)."""
        return {"required_field": "value", "id": 1}

    @pytest.fixture
    def error_input(self) -> dict[str, Any]:
        """Return input that triggers error (missing required field in strict mode)."""
        return {"other_field": "value", "id": 2}

    def test_strict_missing_field_returns_error(
        self,
        transform: TransformProtocol,
        error_input: dict[str, Any],
        ctx: Any,
    ) -> None:
        """Contract: Strict mode MUST return error with missing_field reason."""
        ctx = make_context(run_id="test")
        pipeline_row = make_pipeline_row(error_input)
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "missing_field"

    def test_strict_wrong_type_returns_error(
        self,
        transform: TransformProtocol,
        ctx: Any,
    ) -> None:
        """Contract: Strict mode MUST return error when field is not a string."""
        ctx = make_context(run_id="test")
        pipeline_row = make_pipeline_row({"required_field": 42, "id": 3})
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "type_mismatch"
        assert result.reason["field"] == "required_field"
        assert result.reason["expected"] == "str"
        assert result.reason["actual"] == "int"

    def test_strict_none_value_returns_error(
        self,
        transform: TransformProtocol,
        ctx: Any,
    ) -> None:
        """Contract: Strict mode MUST return error when field value is None."""
        ctx = make_context(run_id="test")
        pipeline_row = make_pipeline_row({"required_field": None, "id": 4})
        result = transform.process(pipeline_row, ctx)
        assert result.status == "error"
        assert result.reason is not None
        assert result.reason["reason"] == "type_mismatch"
        assert result.reason["actual"] == "NoneType"


class TestTruncateLenientNonStringContract(TransformContractPropertyTestBase):
    """Contract tests: lenient mode passes non-strings through unchanged."""

    @pytest.fixture
    def transform(self) -> TransformProtocol:
        """Return a configured transform in lenient (non-strict) mode."""
        return Truncate(
            {
                "fields": {"value": 10},
                "strict": False,
                "schema": {"mode": "observed"},
            }
        )

    @pytest.fixture
    def valid_input(self) -> dict[str, Any]:
        """Return input with non-string field — should pass through in lenient mode."""
        return {"value": 42, "id": 1}

    def test_lenient_non_string_passes_through(
        self,
        transform: TransformProtocol,
        valid_input: dict[str, Any],
        ctx: Any,
    ) -> None:
        """Contract: Lenient mode MUST pass non-string fields through unchanged."""
        ctx = make_context(run_id="test")
        pipeline_row = make_pipeline_row(valid_input)
        result = transform.process(pipeline_row, ctx)
        assert result.status == "success"
        assert result.row["value"] == 42
