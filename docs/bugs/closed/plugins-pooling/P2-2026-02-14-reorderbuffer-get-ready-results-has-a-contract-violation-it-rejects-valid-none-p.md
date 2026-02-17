## Summary

`ReorderBuffer.get_ready_results()` has a contract violation: it rejects valid `None` payloads via `assert`, and behavior changes under `python -O` because those asserts are stripped.

## Severity

- Severity: trivial
- Priority: P3
- Triaged: downgraded from P2 -- ReorderBuffer is only instantiated with TransformResult (never None); assert is correct type-narrowing for actual usage; no production caller passes None

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/pooling/reorder_buffer.py`
- Line(s): 45, 147-149
- Function/Method: `_InternalEntry` / `ReorderBuffer.get_ready_results`

## Evidence

`_InternalEntry` stores `result` as `T | None`:

```python
# src/elspeth/plugins/pooling/reorder_buffer.py:45
result: T | None = None
```

But emission hard-asserts non-`None` result:

```python
# src/elspeth/plugins/pooling/reorder_buffer.py:147-149
assert entry.complete_timestamp is not None
assert entry.complete_index is not None
assert entry.result is not None
```

That means `complete(index, None)` crashes with `AssertionError` even though `T` can be optional (`ReorderBuffer[object | None]` is valid by signature).
I verified this behavior directly:

- normal mode: `AssertionError`
- optimized mode (`python -O`): assert removed, `BufferEntry(..., result=None, ...)` is emitted

So runtime semantics differ by interpreter flags.

Also, current tests only exercise `ReorderBuffer[str]` and `ReorderBuffer[int]`, so this path is untested (`tests/unit/plugins/llm/test_reorder_buffer.py:17,24,40,76,93,107,125,155,187`).

## Root Cause Hypothesis

The implementation uses `None` both as an internal “not yet completed” placeholder and as a forbidden emitted value, then relies on `assert` for invariant enforcement/type narrowing. This conflates state representation with payload validity and makes correctness depend on assert execution mode.

## Suggested Fix

Allow `None` as a legitimate `T` value and remove assert-dependent payload validation:

1. Replace internal placeholder with a private sentinel (not `None`) for `result`.
2. Replace `assert` checks with explicit runtime invariant checks for truly impossible internal states (e.g., missing `complete_timestamp`/`complete_index` when `is_complete=True`).
3. Do not reject `result is None` if completion is marked.
4. Add tests for `ReorderBuffer[object | None]` and parity checks for normal vs `-O` execution semantics.

## Impact

- Potential crash (`AssertionError`) on valid optional payloads.
- Non-deterministic behavior across runtime modes (`python` vs `python -O`).
- Weakens contract clarity for this shared pooling primitive and can produce inconsistent audit/diagnostic behavior depending on interpreter flags.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/pooling/reorder_buffer.py.md`
- Finding index in source report: 1
- Beads: pending
