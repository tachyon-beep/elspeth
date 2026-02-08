"""Tests for lineage.explain() — complete lineage query composition.

Tests cover:
- explain() with token_id (direct lookup)
- explain() with row_id (single terminal token resolution)
- explain() with row_id + sink (disambiguation)
- explain() raises when neither token_id nor row_id provided
- explain() raises when row_id has multiple terminal tokens without sink
- explain() returns None for unknown token/row
- LineageResult fields populated correctly
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from elspeth.contracts.audit import (
    RowLineage,
    Token,
    TokenOutcome,
    TokenParent,
)
from elspeth.contracts.enums import RowOutcome
from elspeth.core.landscape.lineage import LineageResult, explain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recorder(
    *,
    token: Token | None = None,
    row_lineage: RowLineage | None = None,
    node_states: list | None = None,
    routing_events: list | None = None,
    calls: list | None = None,
    token_parents: list | None = None,
    token_outcomes: list | None = None,
    validation_errors: list | None = None,
    transform_errors: list | None = None,
    token_outcome: TokenOutcome | None = None,
) -> Mock:
    """Create a mock recorder with configurable return values."""
    recorder = Mock()
    recorder.get_token.return_value = token
    recorder.explain_row.return_value = row_lineage
    recorder.get_node_states_for_token.return_value = node_states or []
    recorder.get_routing_events_for_states.return_value = routing_events or []
    recorder.get_calls_for_states.return_value = calls or []
    recorder.get_token_parents.return_value = token_parents or []
    recorder.get_token_outcomes_for_row.return_value = token_outcomes or []
    recorder.get_validation_errors_for_row.return_value = validation_errors or []
    recorder.get_transform_errors_for_token.return_value = transform_errors or []
    recorder.get_token_outcome.return_value = token_outcome
    return recorder


def _make_token(
    token_id: str = "tok-1",
    row_id: str = "row-1",
    *,
    fork_group_id: str | None = None,
    join_group_id: str | None = None,
    expand_group_id: str | None = None,
) -> Token:
    from datetime import UTC, datetime
    return Token(
        token_id=token_id,
        row_id=row_id,
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
        fork_group_id=fork_group_id,
        join_group_id=join_group_id,
        expand_group_id=expand_group_id,
    )


def _make_outcome(
    token_id: str = "tok-1",
    outcome: RowOutcome = RowOutcome.COMPLETED,
    is_terminal: bool = True,
    sink_name: str | None = None,
) -> TokenOutcome:
    from datetime import UTC, datetime
    return TokenOutcome(
        outcome_id="out-1",
        run_id="run-1",
        token_id=token_id,
        outcome=outcome,
        is_terminal=is_terminal,
        recorded_at=datetime(2026, 1, 15, tzinfo=UTC),
        sink_name=sink_name,
    )


def _make_row_lineage() -> RowLineage:
    from datetime import UTC, datetime
    return RowLineage(
        row_id="row-1",
        run_id="run-1",
        source_node_id="source-0",
        row_index=0,
        source_data_hash="hash-1",
        created_at=datetime(2026, 1, 15, tzinfo=UTC),
        source_data={"id": 1, "name": "test"},
        payload_available=True,
    )


# ===========================================================================
# Validation
# ===========================================================================


class TestExplainValidation:
    """Tests for explain() argument validation."""

    def test_raises_when_neither_token_nor_row_provided(self) -> None:
        recorder = _make_recorder()
        with pytest.raises(ValueError, match="Must provide either token_id or row_id"):
            explain(recorder, "run-1")

    def test_raises_when_multiple_terminal_tokens_without_sink(self) -> None:
        """Row with multiple terminal tokens and no sink filter raises."""
        outcomes = [
            _make_outcome(token_id="tok-1", sink_name="output"),
            _make_outcome(token_id="tok-2", sink_name="errors"),
        ]
        recorder = _make_recorder(token_outcomes=outcomes)
        with pytest.raises(ValueError, match="has 2 terminal tokens"):
            explain(recorder, "run-1", row_id="row-1")

    def test_raises_when_multiple_tokens_at_same_sink(self) -> None:
        """Multiple tokens reaching same sink raises (fork ambiguity)."""
        outcomes = [
            _make_outcome(token_id="tok-1", sink_name="output"),
            _make_outcome(token_id="tok-2", sink_name="output"),
        ]
        recorder = _make_recorder(token_outcomes=outcomes)
        with pytest.raises(ValueError, match="has 2 tokens at sink"):
            explain(recorder, "run-1", row_id="row-1", sink="output")


# ===========================================================================
# Token ID lookup
# ===========================================================================


class TestExplainByTokenId:
    """Tests for explain() with direct token_id."""

    def test_returns_lineage_for_known_token(self) -> None:
        token = _make_token()
        row_lineage = _make_row_lineage()
        recorder = _make_recorder(token=token, row_lineage=row_lineage)

        result = explain(recorder, "run-1", token_id="tok-1")
        assert result is not None
        assert result.token.token_id == "tok-1"
        assert result.source_row.row_id == "row-1"

    def test_returns_none_for_unknown_token(self) -> None:
        recorder = _make_recorder(token=None)
        result = explain(recorder, "run-1", token_id="nonexistent")
        assert result is None

    def test_returns_none_when_row_not_found(self) -> None:
        token = _make_token()
        recorder = _make_recorder(token=token, row_lineage=None)
        result = explain(recorder, "run-1", token_id="tok-1")
        assert result is None


# ===========================================================================
# Row ID resolution
# ===========================================================================


class TestExplainByRowId:
    """Tests for explain() with row_id resolution."""

    def test_resolves_single_terminal_token(self) -> None:
        token = _make_token()
        row_lineage = _make_row_lineage()
        outcomes = [_make_outcome(token_id="tok-1")]
        recorder = _make_recorder(
            token=token, row_lineage=row_lineage, token_outcomes=outcomes,
        )
        result = explain(recorder, "run-1", row_id="row-1")
        assert result is not None
        assert result.token.token_id == "tok-1"

    def test_returns_none_when_no_outcomes(self) -> None:
        recorder = _make_recorder(token_outcomes=[])
        result = explain(recorder, "run-1", row_id="row-1")
        assert result is None

    def test_returns_none_when_all_non_terminal(self) -> None:
        outcomes = [_make_outcome(is_terminal=False, outcome=RowOutcome.BUFFERED)]
        recorder = _make_recorder(token_outcomes=outcomes)
        result = explain(recorder, "run-1", row_id="row-1")
        assert result is None

    def test_filters_by_sink(self) -> None:
        token = _make_token(token_id="tok-2")
        row_lineage = _make_row_lineage()
        outcomes = [
            _make_outcome(token_id="tok-1", sink_name="output"),
            _make_outcome(token_id="tok-2", sink_name="errors"),
        ]
        recorder = _make_recorder(
            token=token, row_lineage=row_lineage, token_outcomes=outcomes,
        )
        result = explain(recorder, "run-1", row_id="row-1", sink="errors")
        assert result is not None
        # Verify get_token was called with tok-2 (the errors sink token)
        recorder.get_token.assert_called_with("tok-2")

    def test_returns_none_when_sink_has_no_tokens(self) -> None:
        outcomes = [_make_outcome(token_id="tok-1", sink_name="output")]
        recorder = _make_recorder(token_outcomes=outcomes)
        result = explain(recorder, "run-1", row_id="row-1", sink="nonexistent")
        assert result is None


# ===========================================================================
# Parent token integrity
# ===========================================================================


class TestExplainParentIntegrity:
    """Tests for explain() parent token validation."""

    def test_fork_token_without_parents_raises(self) -> None:
        """Token with fork_group_id but no parents is audit corruption."""
        token = _make_token(fork_group_id="fg-1")
        row_lineage = _make_row_lineage()
        recorder = _make_recorder(
            token=token, row_lineage=row_lineage, token_parents=[],
        )
        with pytest.raises(ValueError, match="Audit integrity violation"):
            explain(recorder, "run-1", token_id="tok-1")

    def test_parent_token_not_found_raises(self) -> None:
        """Missing parent token is audit corruption."""
        token = _make_token()
        row_lineage = _make_row_lineage()
        parent_ref = TokenParent(token_id="tok-1", parent_token_id="missing-parent", ordinal=0)
        recorder = _make_recorder(
            token=token, row_lineage=row_lineage,
            token_parents=[parent_ref],
        )
        # get_token returns the main token for tok-1, None for missing-parent
        recorder.get_token.side_effect = lambda tid: token if tid == "tok-1" else None

        with pytest.raises(ValueError, match=r"parent token.*not found"):
            explain(recorder, "run-1", token_id="tok-1")


# ===========================================================================
# LineageResult structure
# ===========================================================================


class TestLineageResult:
    """Tests for LineageResult dataclass."""

    def test_has_expected_fields(self) -> None:
        token = _make_token()
        row_lineage = _make_row_lineage()
        result = LineageResult(
            token=token,
            source_row=row_lineage,
            node_states=[],
            routing_events=[],
            calls=[],
            parent_tokens=[],
        )
        assert result.token is token
        assert result.source_row is row_lineage
        assert result.validation_errors == []
        assert result.transform_errors == []
        assert result.outcome is None
