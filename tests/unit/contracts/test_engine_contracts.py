"""Tests for contracts/engine.py DTOs."""

from dataclasses import FrozenInstanceError

import pytest

from elspeth.contracts.engine import BufferEntry, PendingOutcome
from elspeth.contracts.enums import RowOutcome


class TestBufferEntry:
    def test_frozen(self) -> None:
        """BufferEntry must be immutable — audit timing metadata cannot change after construction."""
        entry = BufferEntry(
            submit_index=0,
            complete_index=1,
            result="test",
            submit_timestamp=1.0,
            complete_timestamp=2.0,
            buffer_wait_ms=5.0,
        )
        with pytest.raises(FrozenInstanceError):
            entry.submit_index = 99  # type: ignore[misc]

    def test_slots(self) -> None:
        """BufferEntry uses __slots__ for memory efficiency — no instance __dict__."""
        entry = BufferEntry(
            submit_index=0,
            complete_index=0,
            result="test",
            submit_timestamp=1.0,
            complete_timestamp=2.0,
            buffer_wait_ms=0.5,
        )
        assert not hasattr(entry, "__dict__"), "Slots dataclass should not have __dict__"

    def test_construction_with_all_fields(self) -> None:
        """BufferEntry should accept all fields at construction."""
        entry = BufferEntry(
            submit_index=3,
            complete_index=1,
            result={"key": "value"},
            submit_timestamp=100.5,
            complete_timestamp=101.2,
            buffer_wait_ms=0.7,
        )
        assert entry.submit_index == 3
        assert entry.complete_index == 1
        assert entry.result == {"key": "value"}
        assert entry.submit_timestamp == 100.5
        assert entry.complete_timestamp == 101.2
        assert entry.buffer_wait_ms == 0.7

    def test_generic_type_parameter(self) -> None:
        """BufferEntry[T] generic should work with different types."""
        int_entry: BufferEntry[int] = BufferEntry(
            submit_index=0,
            complete_index=0,
            result=42,
            submit_timestamp=0.0,
            complete_timestamp=0.0,
            buffer_wait_ms=0.0,
        )
        assert int_entry.result == 42

        str_entry: BufferEntry[str] = BufferEntry(
            submit_index=0,
            complete_index=0,
            result="hello",
            submit_timestamp=0.0,
            complete_timestamp=0.0,
            buffer_wait_ms=0.0,
        )
        assert str_entry.result == "hello"


class TestBufferEntryPostInit:
    """Tests for BufferEntry __post_init__ validation."""

    def test_rejects_negative_submit_index(self) -> None:
        with pytest.raises(ValueError, match="submit_index must be non-negative"):
            BufferEntry(submit_index=-1, complete_index=0, result="x", submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=0.0)

    def test_rejects_negative_complete_index(self) -> None:
        with pytest.raises(ValueError, match="complete_index must be non-negative"):
            BufferEntry(submit_index=0, complete_index=-1, result="x", submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=0.0)

    def test_rejects_nan_submit_timestamp(self) -> None:
        with pytest.raises(ValueError, match="submit_timestamp must be non-negative and finite"):
            BufferEntry(
                submit_index=0, complete_index=0, result="x", submit_timestamp=float("nan"), complete_timestamp=0.0, buffer_wait_ms=0.0
            )

    def test_rejects_inf_complete_timestamp(self) -> None:
        with pytest.raises(ValueError, match="complete_timestamp must be non-negative and finite"):
            BufferEntry(
                submit_index=0, complete_index=0, result="x", submit_timestamp=0.0, complete_timestamp=float("inf"), buffer_wait_ms=0.0
            )

    def test_rejects_negative_buffer_wait_ms(self) -> None:
        with pytest.raises(ValueError, match="buffer_wait_ms must be non-negative and finite"):
            BufferEntry(submit_index=0, complete_index=0, result="x", submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=-1.0)

    def test_rejects_nan_buffer_wait_ms(self) -> None:
        with pytest.raises(ValueError, match="buffer_wait_ms must be non-negative and finite"):
            BufferEntry(
                submit_index=0, complete_index=0, result="x", submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=float("nan")
            )

    def test_accepts_zero_values(self) -> None:
        entry = BufferEntry(submit_index=0, complete_index=0, result="x", submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=0.0)
        assert entry.submit_index == 0
        assert entry.buffer_wait_ms == 0.0


class TestPendingOutcomePostInit:
    """Tests for PendingOutcome __post_init__ validation."""

    def test_quarantined_requires_error_hash(self) -> None:
        with pytest.raises(ValueError, match="QUARANTINED outcome must have error_hash"):
            PendingOutcome(outcome=RowOutcome.QUARANTINED, error_hash=None)

    def test_failed_requires_error_hash(self) -> None:
        with pytest.raises(ValueError, match="FAILED outcome must have error_hash"):
            PendingOutcome(outcome=RowOutcome.FAILED, error_hash=None)

    def test_completed_rejects_error_hash(self) -> None:
        with pytest.raises(ValueError, match="COMPLETED outcome must not have error_hash"):
            PendingOutcome(outcome=RowOutcome.COMPLETED, error_hash="abc123")

    def test_quarantined_with_error_hash_accepted(self) -> None:
        po = PendingOutcome(outcome=RowOutcome.QUARANTINED, error_hash="abc123")
        assert po.error_hash == "abc123"

    def test_completed_without_error_hash_accepted(self) -> None:
        po = PendingOutcome(outcome=RowOutcome.COMPLETED)
        assert po.error_hash is None

    def test_routed_without_error_hash_accepted(self) -> None:
        po = PendingOutcome(outcome=RowOutcome.ROUTED)
        assert po.error_hash is None
