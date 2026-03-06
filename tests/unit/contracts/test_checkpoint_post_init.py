"""Tests for __post_init__ validations on checkpoint types.

Covers: AggregationTokenCheckpoint, AggregationNodeCheckpoint,
AggregationCheckpointState, RowMappingEntry, BatchCheckpointState.
"""

import pytest

from elspeth.contracts.aggregation_checkpoint import (
    AggregationCheckpointState,
    AggregationNodeCheckpoint,
    AggregationTokenCheckpoint,
)
from elspeth.contracts.batch_checkpoint import BatchCheckpointState, RowMappingEntry


class TestAggregationTokenCheckpointPostInit:
    def test_rejects_empty_token_id(self) -> None:
        with pytest.raises(ValueError, match="token_id must not be empty"):
            AggregationTokenCheckpoint(
                token_id="",
                row_id="r1",
                branch_name=None,
                fork_group_id=None,
                join_group_id=None,
                expand_group_id=None,
                row_data={},
                contract_version="v1",
            )

    def test_rejects_empty_row_id(self) -> None:
        with pytest.raises(ValueError, match="row_id must not be empty"):
            AggregationTokenCheckpoint(
                token_id="t1",
                row_id="",
                branch_name=None,
                fork_group_id=None,
                join_group_id=None,
                expand_group_id=None,
                row_data={},
                contract_version="v1",
            )

    def test_rejects_empty_contract_version(self) -> None:
        with pytest.raises(ValueError, match="contract_version must not be empty"):
            AggregationTokenCheckpoint(
                token_id="t1",
                row_id="r1",
                branch_name=None,
                fork_group_id=None,
                join_group_id=None,
                expand_group_id=None,
                row_data={},
                contract_version="",
            )

    def test_accepts_valid(self) -> None:
        t = AggregationTokenCheckpoint(
            token_id="t1",
            row_id="r1",
            branch_name=None,
            fork_group_id=None,
            join_group_id=None,
            expand_group_id=None,
            row_data={"x": 1},
            contract_version="v1",
        )
        assert t.token_id == "t1"


class TestAggregationNodeCheckpointPostInit:
    def test_rejects_empty_batch_id(self) -> None:
        with pytest.raises(ValueError, match="batch_id must not be empty"):
            AggregationNodeCheckpoint(
                tokens=(),
                batch_id="",
                elapsed_age_seconds=0.0,
                count_fire_offset=None,
                condition_fire_offset=None,
                contract={},
            )

    def test_rejects_negative_elapsed_age(self) -> None:
        with pytest.raises(ValueError, match="elapsed_age_seconds must be non-negative"):
            AggregationNodeCheckpoint(
                tokens=(),
                batch_id="b1",
                elapsed_age_seconds=-1.0,
                count_fire_offset=None,
                condition_fire_offset=None,
                contract={},
            )

    def test_accepts_valid(self) -> None:
        n = AggregationNodeCheckpoint(
            tokens=(),
            batch_id="b1",
            elapsed_age_seconds=5.0,
            count_fire_offset=None,
            condition_fire_offset=None,
            contract={},
        )
        assert n.batch_id == "b1"


class TestAggregationCheckpointStatePostInit:
    def test_rejects_empty_version(self) -> None:
        with pytest.raises(ValueError, match="version must not be empty"):
            AggregationCheckpointState(version="", nodes={})


class TestRowMappingEntryPostInit:
    def test_rejects_negative_index(self) -> None:
        with pytest.raises(ValueError, match="index must be non-negative"):
            RowMappingEntry(index=-1, variables_hash="abc")

    def test_rejects_empty_variables_hash(self) -> None:
        with pytest.raises(ValueError, match="variables_hash must not be empty"):
            RowMappingEntry(index=0, variables_hash="")

    def test_accepts_valid(self) -> None:
        e = RowMappingEntry(index=0, variables_hash="abc123")
        assert e.index == 0


class TestBatchCheckpointStatePostInit:
    def test_rejects_empty_batch_id(self) -> None:
        with pytest.raises(ValueError, match="batch_id must not be empty"):
            BatchCheckpointState(
                batch_id="",
                input_file_id="f1",
                row_mapping={},
                template_errors=[],
                submitted_at="2026-01-01T00:00:00Z",
                row_count=1,
                requests={},
            )

    def test_rejects_empty_input_file_id(self) -> None:
        with pytest.raises(ValueError, match="input_file_id must not be empty"):
            BatchCheckpointState(
                batch_id="b1",
                input_file_id="",
                row_mapping={},
                template_errors=[],
                submitted_at="2026-01-01T00:00:00Z",
                row_count=1,
                requests={},
            )

    def test_rejects_negative_row_count(self) -> None:
        with pytest.raises(ValueError, match="row_count must be non-negative"):
            BatchCheckpointState(
                batch_id="b1",
                input_file_id="f1",
                row_mapping={},
                template_errors=[],
                submitted_at="2026-01-01T00:00:00Z",
                row_count=-1,
                requests={},
            )

    def test_accepts_valid(self) -> None:
        s = BatchCheckpointState(
            batch_id="b1",
            input_file_id="f1",
            row_mapping={},
            template_errors=[],
            submitted_at="2026-01-01T00:00:00Z",
            row_count=5,
            requests={},
        )
        assert s.batch_id == "b1"
