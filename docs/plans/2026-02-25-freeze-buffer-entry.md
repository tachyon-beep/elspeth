# Freeze BufferEntry Dataclass Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `BufferEntry` in `contracts/engine.py` frozen and slotted, matching every other DTO in `contracts/`.

**Architecture:** `BufferEntry[T]` is a generic dataclass that carries audit-relevant timing metadata (submit/complete timestamps, buffer wait). It is constructed whole in `ReorderBuffer.get_ready_results()` and consumed read-only downstream. No mutation after construction exists — making it `frozen=True, slots=True` is a one-line change with a regression test.

**Tech Stack:** Python 3.12+ dataclasses with PEP 695 generics, pytest

---

### Task 1: Write Frozen Immutability Test

**Files:**
- Modify: `tests/unit/contracts/test_engine_contracts.py` (create if missing)

**Step 1: Check if test file exists**

Run: `ls tests/unit/contracts/test_engine_contracts.py 2>/dev/null; echo "exit: $?"`
Expected: File may or may not exist.

**Step 2: Write the failing test**

If the file doesn't exist, create it. If it does, add to it. The test follows the exact pattern from `tests/unit/contracts/test_node_state_context.py:88-91` (QueryOrderEntry frozen test):

```python
"""Tests for contracts/engine.py DTOs."""

import pytest
from dataclasses import FrozenInstanceError

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
        """BufferEntry must use slots — no arbitrary attribute assignment."""
        entry = BufferEntry(
            submit_index=0,
            complete_index=1,
            result="test",
            submit_timestamp=1.0,
            complete_timestamp=2.0,
            buffer_wait_ms=5.0,
        )
        with pytest.raises(AttributeError):
            entry.nonexistent_field = "should fail"  # type: ignore[attr-defined]

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
            submit_index=0, complete_index=0, result=42,
            submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=0.0,
        )
        assert int_entry.result == 42

        str_entry: BufferEntry[str] = BufferEntry(
            submit_index=0, complete_index=0, result="hello",
            submit_timestamp=0.0, complete_timestamp=0.0, buffer_wait_ms=0.0,
        )
        assert str_entry.result == "hello"
```

**Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_engine_contracts.py::TestBufferEntry::test_frozen -xvs`
Expected: FAIL — `FrozenInstanceError` is not raised because `BufferEntry` is currently mutable.

**Step 4: Commit failing test**

```bash
git add tests/unit/contracts/test_engine_contracts.py
git commit -m "test: add BufferEntry frozen/slots regression tests (currently failing)"
```

---

### Task 2: Make BufferEntry Frozen

**Files:**
- Modify: `src/elspeth/contracts/engine.py:10`

**Step 1: Apply the fix**

Change line 10 from:
```python
@dataclass
```
to:
```python
@dataclass(frozen=True, slots=True)
```

This is a one-line change. No other code modifications needed — verified by grep that no code mutates BufferEntry after construction.

**Step 2: Run the new tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/contracts/test_engine_contracts.py -xvs`
Expected: All 4 tests PASS.

**Step 3: Run the full reorder buffer test suite**

Run: `.venv/bin/python -m pytest tests/unit/plugins/llm/test_reorder_buffer.py tests/unit/plugins/llm/test_pooled_executor.py tests/unit/contracts/test_node_state_context.py -xvs`
Expected: All pass — these are the primary consumers of BufferEntry.

**Step 4: Run broader regression**

Run: `.venv/bin/python -m pytest tests/ -x --timeout=120`
Expected: Full suite passes. No code mutates BufferEntry after construction, so no breakage expected.

**Step 5: Run type checker**

Run: `.venv/bin/python -m mypy src/elspeth/contracts/engine.py`
Expected: Clean.

**Step 6: Commit**

```bash
git add src/elspeth/contracts/engine.py
git commit -m "fix: make BufferEntry frozen — enforce immutability for audit timing metadata"
```

---

## Verification Checklist

- [ ] `BufferEntry` has `@dataclass(frozen=True, slots=True)`
- [ ] Test confirms `FrozenInstanceError` on mutation attempt
- [ ] Test confirms `AttributeError` on arbitrary attribute assignment
- [ ] All existing ReorderBuffer tests pass
- [ ] All existing PooledExecutor tests pass
- [ ] All existing node_state_context tests pass
- [ ] Full test suite passes
- [ ] mypy clean
