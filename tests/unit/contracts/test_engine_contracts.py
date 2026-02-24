"""Tests for contracts/engine.py DTOs."""

from dataclasses import FrozenInstanceError

import pytest

from elspeth.contracts.engine import BufferEntry


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
        """BufferEntry must use slots — verified by __slots__ presence."""
        # Direct check: slots=True generates __slots__ on the class.
        # (With PEP 695 generics + frozen + slots, the error type on
        # arbitrary-attribute assignment is TypeError rather than
        # AttributeError due to a super() resolution quirk, so we
        # verify the mechanism directly instead.)
        assert hasattr(BufferEntry, "__slots__")
        expected_slots = {"submit_index", "complete_index", "result", "submit_timestamp", "complete_timestamp", "buffer_wait_ms"}
        assert set(BufferEntry.__slots__) == expected_slots

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
