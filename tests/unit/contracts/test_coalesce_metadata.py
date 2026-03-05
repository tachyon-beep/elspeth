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
