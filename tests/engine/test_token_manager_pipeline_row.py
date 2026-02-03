"""Tests for TokenManager with PipelineRow support."""

from unittest.mock import MagicMock, Mock

import pytest

from elspeth.contracts import SourceRow
from elspeth.contracts.identity import TokenInfo
from elspeth.contracts.schema_contract import FieldContract, PipelineRow, SchemaContract


def _make_contract() -> SchemaContract:
    """Create a minimal schema contract for testing."""
    return SchemaContract(
        mode="OBSERVED",
        fields=(
            FieldContract(
                normalized_name="amount",
                original_name="'Amount'",
                python_type=int,
                required=True,
                source="declared",
            ),
        ),
        locked=True,
    )


def _make_mock_recorder() -> MagicMock:
    """Create a mock LandscapeRecorder."""
    recorder = MagicMock()
    recorder.create_row.return_value = Mock(row_id="row_001")
    recorder.create_token.return_value = Mock(token_id="token_001")
    return recorder


class TestTokenManagerCreateInitialToken:
    """Tests for TokenManager.create_initial_token() with SourceRow."""

    def test_create_initial_token_from_source_row(self) -> None:
        """create_initial_token should accept SourceRow and create PipelineRow."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        manager = TokenManager(recorder)

        source_row = SourceRow.valid({"amount": 100}, contract=contract)

        token = manager.create_initial_token(
            run_id="run_001",
            source_node_id="source_001",
            row_index=0,
            source_row=source_row,
        )

        # Token has PipelineRow
        assert isinstance(token.row_data, PipelineRow)
        assert token.row_data["amount"] == 100
        assert token.row_data.contract is contract

        # Recorder was called with dict (for landscape storage)
        recorder.create_row.assert_called_once()
        call_kwargs = recorder.create_row.call_args.kwargs
        assert call_kwargs["data"] == {"amount": 100}

    def test_create_initial_token_requires_contract(self) -> None:
        """create_initial_token should raise ValueError if SourceRow has no contract.

        This is a critical guard - if a source plugin returns SourceRow without
        contract, we crash immediately with a clear message rather than propagating
        None through the pipeline.
        """
        from elspeth.engine.tokens import TokenManager

        recorder = _make_mock_recorder()
        manager = TokenManager(recorder)

        # SourceRow without contract
        source_row = SourceRow.valid({"amount": 100}, contract=None)

        with pytest.raises(ValueError, match="must have contract"):
            manager.create_initial_token(
                run_id="run_001",
                source_node_id="source_001",
                row_index=0,
                source_row=source_row,
            )


class TestTokenManagerForkToken:
    """Tests for TokenManager.fork_token() with PipelineRow."""

    def test_fork_token_propagates_contract(self) -> None:
        """fork_token should propagate contract to all children."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        # Mock fork_token to return children with branch names
        child1 = Mock(token_id="child_001", branch_name="branch_a", fork_group_id="fork_group_001")
        child2 = Mock(token_id="child_002", branch_name="branch_b", fork_group_id="fork_group_001")
        recorder.fork_token.return_value = ([child1, child2], "fork_group_001")
        manager = TokenManager(recorder)

        # Create parent token with PipelineRow
        parent_row = PipelineRow({"amount": 100}, contract)
        parent_token = TokenInfo(
            row_id="row_001",
            token_id="parent_001",
            row_data=parent_row,
        )

        children, fork_group_id = manager.fork_token(
            parent_token=parent_token,
            branches=["branch_a", "branch_b"],
            step_in_pipeline=1,
            run_id="run_001",
        )

        assert len(children) == 2
        # Each child has PipelineRow with same contract
        for child in children:
            assert isinstance(child.row_data, PipelineRow)
            assert child.row_data.contract is contract
            # Data is deep copied
            assert child.row_data["amount"] == 100


class TestTokenManagerExpandToken:
    """Tests for TokenManager.expand_token() with PipelineRow (W6 fix)."""

    def test_expand_token_propagates_contract(self) -> None:
        """expand_token should propagate parent contract to all children."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        # Mock expand_token to return children
        child1 = Mock(token_id="child_001", expand_group_id="eg_001")
        child2 = Mock(token_id="child_002", expand_group_id="eg_001")
        recorder.expand_token.return_value = ([child1, child2], "eg_001")
        manager = TokenManager(recorder)

        # Create parent token with PipelineRow
        parent_row = PipelineRow({"amount": 100}, contract)
        parent_token = TokenInfo(
            row_id="row_001",
            token_id="parent_001",
            row_data=parent_row,
        )

        # Expanded rows are dicts from transform output
        expanded_rows = [
            {"amount": 100, "split": 1},
            {"amount": 100, "split": 2},
        ]

        children, expand_group_id = manager.expand_token(
            parent_token=parent_token,
            expanded_rows=expanded_rows,
            step_in_pipeline=1,
            run_id="run_001",
        )

        assert len(children) == 2
        # Each child has PipelineRow with parent's contract
        for i, child in enumerate(children):
            assert isinstance(child.row_data, PipelineRow)
            assert child.row_data.contract is contract
            # Data from expanded_rows - use to_dict() for fields outside contract
            # (In production, the contract would be updated to include new fields)
            data = child.row_data.to_dict()
            assert data["amount"] == 100
            assert data["split"] == i + 1


class TestTokenManagerCoalesceTokens:
    """Tests for TokenManager.coalesce_tokens() with PipelineRow."""

    def test_coalesce_accepts_pipeline_row(self) -> None:
        """coalesce_tokens should accept PipelineRow for merged_data."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        # Mock coalesce_tokens return
        recorder.coalesce_tokens.return_value = Mock(
            token_id="merged_001",
            join_group_id="join_001",
        )
        manager = TokenManager(recorder)

        # Create parent tokens with PipelineRow
        parent_row_a = PipelineRow({"amount": 100, "branch_a_field": "a"}, contract)
        parent_row_b = PipelineRow({"amount": 100, "branch_b_field": "b"}, contract)
        parent_a = TokenInfo(row_id="row_001", token_id="token_a", row_data=parent_row_a)
        parent_b = TokenInfo(row_id="row_001", token_id="token_b", row_data=parent_row_b)

        # Merged data as PipelineRow
        merged_row = PipelineRow(
            {"amount": 100, "branch_a_field": "a", "branch_b_field": "b"},
            contract,
        )

        merged_token = manager.coalesce_tokens(
            parents=[parent_a, parent_b],
            merged_data=merged_row,
            step_in_pipeline=3,
        )

        assert merged_token.token_id == "merged_001"
        assert isinstance(merged_token.row_data, PipelineRow)
        assert merged_token.row_data["amount"] == 100
        assert merged_token.row_data.contract is contract


class TestPipelineRowDeepCopy:
    """Tests for deepcopy behavior of PipelineRow (B8 fix)."""

    def test_deepcopy_preserves_contract(self) -> None:
        """copy.deepcopy(PipelineRow) should preserve contract reference."""
        import copy

        contract = _make_contract()
        original = PipelineRow({"amount": 100, "nested": {"a": 1}}, contract)

        copied = copy.deepcopy(original)

        # Contract is preserved (same reference is acceptable for immutable contracts)
        # SchemaContract is frozen=True, so sharing reference is safe
        assert copied.contract is contract or copied.contract == contract
        # Data is copied (not shared)
        assert copied.to_dict() == original.to_dict()
        assert copied.to_dict() is not original.to_dict()

    def test_deepcopy_isolates_nested_data(self) -> None:
        """Deepcopy should isolate nested mutable structures.

        Note: PipelineRow uses MappingProxyType internally which makes it immutable,
        but the source data dict could have nested mutables. Deepcopy should still
        produce an independent copy.
        """
        import copy

        contract = _make_contract()
        # Create PipelineRow - it stores immutable view internally
        original = PipelineRow({"amount": 100, "items": [1, 2, 3]}, contract)

        copied = copy.deepcopy(original)

        # Both should have same values
        assert copied.to_dict()["items"] == [1, 2, 3]
        # But be independent copies
        assert copied.to_dict()["items"] is not original.to_dict()["items"]


class TestTokenManagerUpdateRowData:
    """Tests for TokenManager.update_row_data() with PipelineRow."""

    def test_update_row_data_accepts_pipeline_row(self) -> None:
        """update_row_data should accept PipelineRow and return updated TokenInfo."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        manager = TokenManager(recorder)

        original_row = PipelineRow({"amount": 100}, contract)
        token = TokenInfo(row_id="row_001", token_id="token_001", row_data=original_row)

        new_row = PipelineRow({"amount": 200, "computed": True}, contract)
        updated = manager.update_row_data(token, new_row)

        assert isinstance(updated.row_data, PipelineRow)
        # Use to_dict() for fields that may not be in the original contract
        data = updated.row_data.to_dict()
        assert data["amount"] == 200
        assert data["computed"] is True
        assert updated.token_id == token.token_id
        assert updated.row_id == token.row_id

    def test_update_row_data_preserves_lineage(self) -> None:
        """update_row_data should preserve all lineage fields."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        manager = TokenManager(recorder)

        original_row = PipelineRow({"amount": 100}, contract)
        token = TokenInfo(
            row_id="row_001",
            token_id="token_001",
            row_data=original_row,
            branch_name="my_branch",
            fork_group_id="fork_001",
            expand_group_id="expand_001",
        )

        new_row = PipelineRow({"amount": 200}, contract)
        updated = manager.update_row_data(token, new_row)

        # All lineage preserved
        assert updated.branch_name == "my_branch"
        assert updated.fork_group_id == "fork_001"
        assert updated.expand_group_id == "expand_001"


class TestTokenManagerCreateTokenForExistingRow:
    """Tests for TokenManager.create_token_for_existing_row() with PipelineRow."""

    def test_create_token_for_existing_row_accepts_pipeline_row(self) -> None:
        """create_token_for_existing_row should accept PipelineRow."""
        from elspeth.engine.tokens import TokenManager

        contract = _make_contract()
        recorder = _make_mock_recorder()
        recorder.create_token.return_value = Mock(token_id="new_token_001")
        manager = TokenManager(recorder)

        row_data = PipelineRow({"amount": 100}, contract)

        token = manager.create_token_for_existing_row(
            row_id="existing_row_001",
            row_data=row_data,
        )

        assert token.row_id == "existing_row_001"
        assert token.token_id == "new_token_001"
        assert isinstance(token.row_data, PipelineRow)
        assert token.row_data["amount"] == 100
