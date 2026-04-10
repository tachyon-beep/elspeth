"""Tests for PluginContext.record_validation_error() and record_transform_error().

Tests the offensive programming guards (FrameworkBugError) and basic delegation
to ExecutionRepository. Uses make_source_context() for real landscape integration
and manual PluginContext construction for guard-clause tests.
"""

from unittest.mock import Mock

import pytest

from elspeth.contracts import FrameworkBugError
from elspeth.contracts.audit import TokenRef
from elspeth.contracts.plugin_context import (
    PluginContext,
    TransformErrorToken,
    ValidationErrorToken,
)
from tests.fixtures.factories import make_source_context


class TestRecordValidationErrorGuards:
    """record_validation_error() must crash on missing landscape or node_id."""

    def test_raises_when_landscape_is_none(self) -> None:
        ctx = PluginContext(run_id="run-1", config={}, landscape=None, node_id="source")
        with pytest.raises(FrameworkBugError, match=r"record_validation_error.*without landscape"):
            ctx.record_validation_error(
                row={"name": "test"},
                error="field X is NULL",
                schema_mode="fixed",
                destination="discard",
            )

    def test_raises_when_node_id_is_none(self) -> None:
        ctx = PluginContext(run_id="run-1", config={}, landscape=Mock(), node_id=None)
        with pytest.raises(FrameworkBugError, match=r"record_validation_error.*without node_id"):
            ctx.record_validation_error(
                row={"name": "test"},
                error="field X is NULL",
                schema_mode="fixed",
                destination="discard",
            )


class TestRecordValidationErrorHappyPath:
    """record_validation_error() delegates to landscape and returns token."""

    def test_returns_validation_error_token(self) -> None:
        """Happy path: row with id field -> token with that row_id."""
        ctx = make_source_context()
        token = ctx.record_validation_error(
            row={"id": "row-42", "name": "test"},
            error="field X is NULL",
            schema_mode="fixed",
            destination="discard",
        )
        assert isinstance(token, ValidationErrorToken)
        assert token.row_id == "row-42"
        assert token.node_id == "source"
        assert token.destination == "discard"
        assert token.error_id is not None  # Landscape assigns an error_id

    def test_row_without_id_uses_content_hash(self) -> None:
        """Row without 'id' field -> row_id derived from stable_hash."""
        ctx = make_source_context()
        token = ctx.record_validation_error(
            row={"name": "test"},
            error="missing required field",
            schema_mode="flexible",
            destination="quarantine_sink",
        )
        assert isinstance(token, ValidationErrorToken)
        assert len(token.row_id) == 16  # stable_hash[:16]
        assert token.destination == "quarantine_sink"

    def test_non_dict_row_uses_repr_hash(self) -> None:
        """Non-dict row (e.g., JSON primitive) -> row_id from repr_hash."""
        ctx = make_source_context()
        token = ctx.record_validation_error(
            row="not a dict",
            error="expected dict, got str",
            schema_mode="parse",
            destination="discard",
        )
        assert isinstance(token, ValidationErrorToken)
        assert len(token.row_id) == 16

    def test_custom_destination_propagated(self) -> None:
        """Destination string flows through to the returned token."""
        ctx = make_source_context()
        token = ctx.record_validation_error(
            row={"id": "row-1"},
            error="bad data",
            schema_mode="fixed",
            destination="error_sink",
        )
        assert token.destination == "error_sink"


class TestRecordTransformErrorGuards:
    """record_transform_error() must crash on missing landscape."""

    def test_raises_when_landscape_is_none(self) -> None:
        ctx = PluginContext(run_id="run-1", config={}, landscape=None, node_id="transform-1")
        with pytest.raises(FrameworkBugError, match=r"record_transform_error.*without landscape"):
            ctx.record_transform_error(
                token_id="tok-1",
                transform_id="transform-1",
                row={"data": "test"},
                error_details={"action": "quarantine", "reason": "API returned 500"},
                destination="discard",
            )


class TestRecordTransformErrorHappyPath:
    """record_transform_error() delegates to landscape and returns token."""

    def test_returns_transform_error_token(self) -> None:
        """Happy path: landscape.record_transform_error is called and token fields are populated.

        record_transform_error requires a pre-existing token FK in the DB.
        Use a Mock landscape to test the delegation and return-value logic
        without needing to build the full token/row/node FK chain — that
        belongs in integration tests (test_recorder_errors.py).
        """
        mock_landscape = Mock()
        mock_landscape.record_transform_error.return_value = "terr_abc123"
        ctx = PluginContext(
            run_id="run-1",
            config={},
            landscape=mock_landscape,
            node_id="transform-1",
        )
        token = ctx.record_transform_error(
            token_id="tok-1",
            transform_id="transform-1",
            row={"data": "test"},
            error_details={"action": "quarantine", "reason": "API returned 500"},
            destination="error_sink",
        )
        assert isinstance(token, TransformErrorToken)
        assert token.token_id == "tok-1"
        assert token.transform_id == "transform-1"
        assert token.destination == "error_sink"
        assert token.error_id == "terr_abc123"
        mock_landscape.record_transform_error.assert_called_once_with(
            ref=TokenRef(token_id="tok-1", run_id="run-1"),
            transform_id="transform-1",
            row_data={"data": "test"},
            error_details={"action": "quarantine", "reason": "API returned 500"},
            destination="error_sink",
        )
