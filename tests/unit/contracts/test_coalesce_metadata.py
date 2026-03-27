# tests/unit/contracts/test_coalesce_metadata.py
"""Tests for CoalesceMetadata factory methods — truthiness conflation bugs."""

from types import MappingProxyType

from elspeth.contracts.coalesce_enums import CoalescePolicy, MergeStrategy
from elspeth.contracts.coalesce_metadata import CoalesceMetadata


class TestForFailureTruthinessConflation:
    """for_failure must distinguish empty dict from None for branches_lost.

    Empty dict ({}) means "zero branches lost" — a known, meaningful state.
    None means "unknown/not applicable." Truthiness conflates them.
    """

    def test_empty_dict_branches_lost_preserved_as_empty_mapping(self) -> None:
        """branches_lost={} must become MappingProxyType({}), not None."""
        meta = CoalesceMetadata.for_failure(
            policy=CoalescePolicy.REQUIRE_ALL,
            expected_branches=["a", "b"],
            branches_arrived=["a"],
            branches_lost={},
        )
        assert meta.branches_lost is not None
        assert meta.branches_lost == MappingProxyType({})

    def test_none_branches_lost_stays_none(self) -> None:
        """branches_lost=None must stay None."""
        meta = CoalesceMetadata.for_failure(
            policy=CoalescePolicy.REQUIRE_ALL,
            expected_branches=["a", "b"],
            branches_arrived=["a"],
            branches_lost=None,
        )
        assert meta.branches_lost is None

    def test_populated_branches_lost_preserved(self) -> None:
        """Non-empty branches_lost dict is wrapped correctly."""
        meta = CoalesceMetadata.for_failure(
            policy=CoalescePolicy.REQUIRE_ALL,
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
            policy=CoalescePolicy.REQUIRE_ALL,
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
            policy=CoalescePolicy.REQUIRE_ALL,
            merge_strategy=MergeStrategy.UNION,
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
            policy=CoalescePolicy.REQUIRE_ALL,
            expected_branches=["a"],
            branches_arrived=["a"],
            branches_lost={},
        )
        merge_meta = CoalesceMetadata.for_merge(
            policy=CoalescePolicy.REQUIRE_ALL,
            merge_strategy=MergeStrategy.UNION,
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


class TestCoalesceMetadataEnumFields:
    def test_policy_is_enum(self) -> None:
        meta = CoalesceMetadata(policy=CoalescePolicy.REQUIRE_ALL)
        assert isinstance(meta.policy, CoalescePolicy)

    def test_merge_strategy_is_enum(self) -> None:
        meta = CoalesceMetadata(
            policy=CoalescePolicy.REQUIRE_ALL,
            merge_strategy=MergeStrategy.UNION,
        )
        assert isinstance(meta.merge_strategy, MergeStrategy)

    def test_factory_for_late_arrival_uses_enum(self) -> None:
        meta = CoalesceMetadata.for_late_arrival(
            policy=CoalescePolicy.REQUIRE_ALL,
            reason="test",
        )
        assert meta.policy is CoalescePolicy.REQUIRE_ALL

    def test_to_dict_emits_string_value_for_policy(self) -> None:
        meta = CoalesceMetadata(policy=CoalescePolicy.REQUIRE_ALL)
        d = meta.to_dict()
        assert d["policy"] == "require_all"
        assert isinstance(d["policy"], str)

    def test_to_dict_emits_string_value_for_merge_strategy(self) -> None:
        meta = CoalesceMetadata(
            policy=CoalescePolicy.REQUIRE_ALL,
            merge_strategy=MergeStrategy.UNION,
        )
        d = meta.to_dict()
        assert d["merge_strategy"] == "union"
        assert isinstance(d["merge_strategy"], str)


class TestCoalesceMetadataFreezeGuards:
    def test_direct_construction_with_raw_dict_freezes(self) -> None:
        """Even if someone bypasses factories, freeze_fields catches it."""
        meta = CoalesceMetadata(
            policy=CoalescePolicy.REQUIRE_ALL,
            branches_lost={"a": "timeout"},  # type: ignore[arg-type]
        )
        assert isinstance(meta.branches_lost, MappingProxyType)

    def test_direct_construction_with_raw_collisions_freezes(self) -> None:
        meta = CoalesceMetadata(
            policy=CoalescePolicy.REQUIRE_ALL,
            union_field_collisions={"x": ("a", "b")},  # type: ignore[arg-type]
        )
        assert isinstance(meta.union_field_collisions, MappingProxyType)
