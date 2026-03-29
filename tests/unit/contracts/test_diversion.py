"""Tests for sink diversion contracts."""

from __future__ import annotations

import pytest

from elspeth.contracts.diversion import RowDiversion, SinkWriteResult
from elspeth.contracts.results import ArtifactDescriptor


class TestRowDiversion:
    def test_create_with_required_fields(self) -> None:
        d = RowDiversion(row_index=0, reason="bad metadata", row_data={"a": 1})
        assert d.row_index == 0
        assert d.reason == "bad metadata"
        assert d.row_data["a"] == 1

    def test_frozen(self) -> None:
        d = RowDiversion(row_index=0, reason="test", row_data={"a": 1})
        with pytest.raises(AttributeError):
            d.row_index = 1  # type: ignore[misc]

    def test_row_data_deep_frozen(self) -> None:
        """row_data uses freeze_fields — nested dicts become MappingProxyType."""
        d = RowDiversion(row_index=0, reason="test", row_data={"a": {"nested": 1}})
        with pytest.raises(TypeError):
            d.row_data["b"] = 2  # type: ignore[index]

    def test_row_data_nested_frozen(self) -> None:
        """Nested dicts inside row_data are also frozen."""
        d = RowDiversion(row_index=0, reason="test", row_data={"a": {"nested": 1}})
        with pytest.raises(TypeError):
            d.row_data["a"]["new_key"] = 99

    def test_negative_row_index_rejected(self) -> None:
        with pytest.raises(ValueError, match="row_index must be >= 0"):
            RowDiversion(row_index=-1, reason="test", row_data={})

    def test_bool_row_index_rejected(self) -> None:
        """bool is a subclass of int — require_int rejects it."""
        with pytest.raises(TypeError, match="row_index must be int"):
            RowDiversion(row_index=True, reason="test", row_data={})


class TestSinkWriteResult:
    def _make_artifact(self) -> ArtifactDescriptor:
        return ArtifactDescriptor.for_file(
            path="/tmp/test.csv",
            content_hash="abc123def456",
            size_bytes=100,
        )

    def test_no_diversions_default(self) -> None:
        result = SinkWriteResult(artifact=self._make_artifact())
        assert result.diversions == ()
        assert result.artifact.path_or_uri == "file:///tmp/test.csv"

    def test_with_diversions(self) -> None:
        divs = (
            RowDiversion(row_index=1, reason="bad type", row_data={"x": 1}),
            RowDiversion(row_index=3, reason="too long", row_data={"x": 2}),
        )
        result = SinkWriteResult(artifact=self._make_artifact(), diversions=divs)
        assert len(result.diversions) == 2
        assert result.diversions[0].row_index == 1
        assert result.diversions[1].row_index == 3

    def test_frozen(self) -> None:
        result = SinkWriteResult(artifact=self._make_artifact())
        with pytest.raises(AttributeError):
            result.artifact = self._make_artifact()  # type: ignore[misc]

    def test_diversions_tuple_not_list(self) -> None:
        """Diversions must be a tuple (immutable), not a list."""
        result = SinkWriteResult(artifact=self._make_artifact())
        assert isinstance(result.diversions, tuple)
