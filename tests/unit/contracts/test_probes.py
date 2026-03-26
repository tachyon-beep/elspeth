"""Tests for collection readiness probes."""

from __future__ import annotations

import pytest

from elspeth.contracts.probes import CollectionProbe, CollectionReadinessResult


class TestCollectionReadinessResult:
    """Tests for the unified collection readiness result type."""

    def test_construction_with_all_fields(self) -> None:
        result = CollectionReadinessResult(
            collection="science-facts",
            reachable=True,
            count=450,
            message="Collection 'science-facts' has 450 documents",
        )
        assert result.collection == "science-facts"
        assert result.reachable is True
        assert result.count == 450
        assert result.message == "Collection 'science-facts' has 450 documents"

    def test_frozen_immutability(self) -> None:
        result = CollectionReadinessResult(
            collection="test",
            reachable=True,
            count=10,
            message="ok",
        )
        with pytest.raises(AttributeError):
            result.count = 99  # type: ignore[misc]

    def test_unreachable_result(self) -> None:
        result = CollectionReadinessResult(
            collection="missing",
            reachable=False,
            count=0,
            message="Collection 'missing' not found",
        )
        assert result.reachable is False
        assert result.count == 0

    def test_empty_collection_result(self) -> None:
        result = CollectionReadinessResult(
            collection="empty",
            reachable=True,
            count=0,
            message="Collection 'empty' is empty",
        )
        assert result.reachable is True
        assert result.count == 0

    def test_empty_collection_raises(self) -> None:
        with pytest.raises(ValueError, match="collection must not be empty"):
            CollectionReadinessResult(collection="", reachable=True, count=0, message="ok")

    def test_negative_count_raises(self) -> None:
        with pytest.raises(ValueError, match="count must be non-negative"):
            CollectionReadinessResult(collection="test", reachable=True, count=-1, message="ok")

    def test_valid_construction(self) -> None:
        result = CollectionReadinessResult(
            collection="my-collection",
            reachable=True,
            count=0,
            message="ok",
        )
        assert result.collection == "my-collection"
        assert result.count == 0


class TestCollectionProbe:
    """Tests for the CollectionProbe protocol."""

    def test_compliant_implementation_passes_isinstance(self) -> None:
        class FakeProbe:
            collection_name: str = "test-collection"

            def probe(self) -> CollectionReadinessResult:
                return CollectionReadinessResult(
                    collection=self.collection_name,
                    reachable=True,
                    count=5,
                    message="ok",
                )

        probe = FakeProbe()
        assert isinstance(probe, CollectionProbe)

    def test_non_compliant_missing_probe_method(self) -> None:
        class BadProbe:
            collection_name: str = "test"

        assert not isinstance(BadProbe(), CollectionProbe)

    def test_non_compliant_missing_collection_name(self) -> None:
        class BadProbe:
            def probe(self) -> CollectionReadinessResult:
                return CollectionReadinessResult(collection="x", reachable=True, count=1, message="ok")

        # Python 3.12+ runtime_checkable checks non-callable protocol
        # members as instance attributes. BadProbe has no collection_name
        # instance attribute, so isinstance returns False.
        assert not isinstance(BadProbe(), CollectionProbe)
