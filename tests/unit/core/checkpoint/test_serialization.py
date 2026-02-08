"""Unit tests for checkpoint serialization edge cases."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from elspeth.core.checkpoint.serialization import checkpoint_dumps, checkpoint_loads


def test_checkpoint_dumps_sets_utc_on_naive_datetime() -> None:
    naive = datetime(2026, 2, 8, 10, 15, 30, tzinfo=UTC).replace(tzinfo=None)
    result = checkpoint_loads(checkpoint_dumps({"created_at": naive}))
    restored = result["created_at"]

    assert isinstance(restored, datetime)
    assert restored.tzinfo is not None
    assert restored.replace(tzinfo=None) == naive


def test_checkpoint_dumps_preserves_aware_datetime() -> None:
    aware = datetime(2026, 2, 8, 10, 15, 30, tzinfo=UTC)
    result = checkpoint_loads(checkpoint_dumps({"created_at": aware}))
    assert result["created_at"] == aware


def test_checkpoint_dumps_raises_for_unserializable_type() -> None:
    with pytest.raises(TypeError):
        checkpoint_dumps({"bad": {1, 2, 3}})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_checkpoint_dumps_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite float"):
        checkpoint_dumps({"v": value})


def test_checkpoint_dumps_rejects_non_finite_values_in_nested_list() -> None:
    with pytest.raises(ValueError, match="non-finite float"):
        checkpoint_dumps({"values": [1.0, {"inner": float("nan")}]})


def test_checkpoint_loads_restores_datetime_tag() -> None:
    payload = '{"ts":{"__datetime__":"2026-02-08T10:15:30+00:00"}}'
    result = checkpoint_loads(payload)

    assert isinstance(result["ts"], datetime)
    assert result["ts"] == datetime(2026, 2, 8, 10, 15, 30, tzinfo=UTC)


def test_checkpoint_loads_does_not_restore_lookalike_tag_with_extra_keys() -> None:
    payload = '{"ts":{"__datetime__":"2026-02-08T10:15:30+00:00","extra":1}}'
    result = checkpoint_loads(payload)

    assert isinstance(result["ts"], dict)
    assert result["ts"]["__datetime__"] == "2026-02-08T10:15:30+00:00"
    assert result["ts"]["extra"] == 1
