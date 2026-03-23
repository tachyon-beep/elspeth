# tests/unit/contracts/test_coalesce_metadata.py
"""Tests for CoalesceMetadata factory methods — truthiness conflation bugs."""

from types import MappingProxyType

from elspeth.contracts.coalesce_metadata import CoalesceMetadata


class TestForFailureTruthinessConflation:
    """for_failure must distinguish empty dict from None for branches_lost.

    Empty dict ({}) means "zero branches lost" — a known, meaningful state.
    None means "unknown/not applicable." Truthiness conflates them.
    """

    def test_empty_dict_branches_lost_preserved_as_empty_mapping(self) -> None:
        """branches_lost={} must become MappingProxyType({}), not None."""
        meta = CoalesceMetadata.for_failure(
            policy="wait_all",
            expected_branches=["a", "b"],
            branches_arrived=["a"],
            branches_lost={},
        )
        assert meta.branches_lost is not None
        assert meta.branches_lost == MappingProxyType({})

    def test_none_branches_lost_stays_none(self) -> None:
        """branches_lost=None must stay None."""
        meta = CoalesceMetadata.for_failure(
            policy="wait_all",
            expected_branches=["a", "b"],
            branches_arrived=["a"],
            branches_lost=None,
        )
        assert meta.branches_lost is None

    def test_populated_branches_lost_preserved(self) -> None:
        """Non-empty branches_lost dict is wrapped correctly."""
        meta = CoalesceMetadata.for_failure(
            policy="wait_all",
            expected_branches=["a", "b"],
            branches_arrived=["a"],
            branches_lost={"b": "timeout"},
        )
        assert meta.branches_lost is not None
        assert dict(meta.branches_lost) == {"b": "timeout"}


class TestBranchesLostAuditShapeConsistency:
    """Regression: elspeth-a7a6526b14, elspeth-de2e51b30e.

    to_dict() output for branches_lost must have a consistent shape between
    for_failure and for_merge paths. Empty dict must serialize as
    "branches_lost": {}, not be omitted entirely.
    """

    def test_for_failure_empty_dict_emits_branches_lost_key(self) -> None:
        """for_failure with empty branches_lost={} must emit the key in to_dict()."""
        meta = CoalesceMetadata.for_failure(
            policy="wait_all",
            expected_branches=["a", "b"],
            branches_arrived=["a", "b"],
            branches_lost={},
        )
        d = meta.to_dict()
        assert "branches_lost" in d, "branches_lost key omitted from to_dict() output"
        assert d["branches_lost"] == {}

    def test_for_merge_empty_dict_emits_branches_lost_key(self) -> None:
        """for_merge with empty branches_lost={} must emit the key in to_dict()."""
        from elspeth.contracts.coalesce_metadata import ArrivalOrderEntry

        meta = CoalesceMetadata.for_merge(
            policy="wait_all",
            merge_strategy="union",
            expected_branches=["a", "b"],
            branches_arrived=["a", "b"],
            branches_lost={},
            arrival_order=[
                ArrivalOrderEntry(branch="a", arrival_offset_ms=0.0),
                ArrivalOrderEntry(branch="b", arrival_offset_ms=100.0),
            ],
            wait_duration_ms=100.0,
        )
        d = meta.to_dict()
        assert "branches_lost" in d
        assert d["branches_lost"] == {}

    def test_failure_and_merge_shape_consistent_for_empty_branches_lost(self) -> None:
        """Both paths must produce identical shape for 'no branches lost'."""
        from elspeth.contracts.coalesce_metadata import ArrivalOrderEntry

        failure_meta = CoalesceMetadata.for_failure(
            policy="wait_all",
            expected_branches=["a"],
            branches_arrived=["a"],
            branches_lost={},
        )
        merge_meta = CoalesceMetadata.for_merge(
            policy="wait_all",
            merge_strategy="union",
            expected_branches=["a"],
            branches_arrived=["a"],
            branches_lost={},
            arrival_order=[ArrivalOrderEntry(branch="a", arrival_offset_ms=0.0)],
            wait_duration_ms=0.0,
        )
        failure_has_key = "branches_lost" in failure_meta.to_dict()
        merge_has_key = "branches_lost" in merge_meta.to_dict()
        assert failure_has_key == merge_has_key, (
            f"Shape inconsistency: for_failure emits branches_lost={failure_has_key}, for_merge emits branches_lost={merge_has_key}"
        )
