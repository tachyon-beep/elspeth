"""Tests for collection readiness probes."""

from __future__ import annotations

import pytest

from elspeth.contracts.probes import CollectionReadinessResult


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
