"""Unit tests for RowDataState and RowDataResult invariants."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from elspeth.core.landscape.row_data import CallDataResult, CallDataState, RowDataResult, RowDataState


def test_row_data_state_values() -> None:
    assert RowDataState.AVAILABLE.value == "available"
    assert RowDataState.REPR_FALLBACK.value == "repr_fallback"
    assert RowDataState.PURGED.value == "purged"
    assert RowDataState.NEVER_STORED.value == "never_stored"
    assert RowDataState.STORE_NOT_CONFIGURED.value == "store_not_configured"
    assert RowDataState.ROW_NOT_FOUND.value == "row_not_found"


def test_row_data_result_available_requires_data() -> None:
    with pytest.raises(ValueError, match="available state requires non-None data"):
        RowDataResult(state=RowDataState.AVAILABLE, data=None)


def test_row_data_result_non_available_requires_none_data() -> None:
    with pytest.raises(ValueError, match="state requires None data"):
        RowDataResult(state=RowDataState.PURGED, data={"unexpected": "payload"})


def test_row_data_result_allows_available_with_data() -> None:
    result = RowDataResult(state=RowDataState.AVAILABLE, data={"id": 1})
    assert result.state == RowDataState.AVAILABLE
    assert result.data == {"id": 1}


@pytest.mark.parametrize("non_dict_data", [[1, 2, 3], "payload", 42, 3.14, True])
def test_row_data_result_available_rejects_non_dict_data(non_dict_data: Any) -> None:
    with pytest.raises(TypeError, match="available state requires dict data"):
        RowDataResult(state=RowDataState.AVAILABLE, data=non_dict_data)


def test_row_data_result_allows_non_available_with_none() -> None:
    result = RowDataResult(state=RowDataState.ROW_NOT_FOUND, data=None)
    assert result.state == RowDataState.ROW_NOT_FOUND
    assert result.data is None


def test_row_data_result_is_frozen() -> None:
    result = RowDataResult(state=RowDataState.AVAILABLE, data={"id": 1})
    with pytest.raises(FrozenInstanceError):
        result.state = RowDataState.PURGED  # type: ignore[misc]


# --- REPR_FALLBACK state tests ---


def test_row_data_result_repr_fallback_with_data() -> None:
    """REPR_FALLBACK state allows dict data (lossy repr snapshot)."""
    data = {"_repr": "{'nan_field': nan}"}
    result = RowDataResult(state=RowDataState.REPR_FALLBACK, data=data)
    assert result.state == RowDataState.REPR_FALLBACK
    assert result.data == data


def test_row_data_result_repr_fallback_requires_data() -> None:
    """REPR_FALLBACK state requires non-None data (same invariant as AVAILABLE)."""
    with pytest.raises(ValueError, match="repr_fallback state requires non-None data"):
        RowDataResult(state=RowDataState.REPR_FALLBACK, data=None)


@pytest.mark.parametrize("non_dict_data", [[1, 2], "string", 42])
def test_row_data_result_repr_fallback_rejects_non_dict(non_dict_data: Any) -> None:
    """REPR_FALLBACK state requires dict data, not other types."""
    with pytest.raises(TypeError, match="repr_fallback state requires dict data"):
        RowDataResult(state=RowDataState.REPR_FALLBACK, data=non_dict_data)


# --- CallDataState HASH_ONLY tests ---


def test_call_data_state_hash_only_value() -> None:
    assert CallDataState.HASH_ONLY.value == "hash_only"


def test_call_data_result_hash_only_with_none_data() -> None:
    """HASH_ONLY state requires None data (hash exists but no payload)."""
    result = CallDataResult(state=CallDataState.HASH_ONLY, data=None)
    assert result.state == CallDataState.HASH_ONLY
    assert result.data is None


def test_call_data_result_hash_only_rejects_data() -> None:
    """HASH_ONLY state must not have data (no payload available)."""
    with pytest.raises(ValueError, match="state requires None data"):
        CallDataResult(state=CallDataState.HASH_ONLY, data={"unexpected": "payload"})
