## Summary

`LandscapeJournal` records SQL writes from rolled-back savepoints as if they committed, because it uses one flat per-connection buffer and only clears it on full connection rollback.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/landscape/journal.py`
- Line(s): 88-130
- Function/Method: `LandscapeJournal._after_cursor_execute`, `LandscapeJournal._after_commit`, `LandscapeJournal._after_rollback`

## Evidence

`_after_cursor_execute()` appends every write statement into a single `conn.info["landscape_journal_buffer"]` list, with no transaction-depth tracking:

```python
# src/elspeth/core/landscape/journal.py:109-115
if _BUFFER_KEY in conn.info:
    buffer = conn.info[_BUFFER_KEY]
else:
    buffer = []
    conn.info[_BUFFER_KEY] = buffer

buffer.append(record)
```

`_after_commit()` flushes that entire flat buffer on outer commit:

```python
# src/elspeth/core/landscape/journal.py:117-126
if _BUFFER_KEY not in conn.info:
    return
buffer = conn.info[_BUFFER_KEY]
...
self._append_records(buffer)
buffer.clear()
```

`_after_rollback()` only clears on the engine-level rollback event:

```python
# src/elspeth/core/landscape/journal.py:128-130
if _BUFFER_KEY in conn.info:
    conn.info[_BUFFER_KEY].clear()
```

There is no savepoint-specific handling anywhere in the file. `attach()` only registers `after_cursor_execute`, `commit`, and `rollback` listeners, so nested transaction rollback/release events are ignored ([`journal.py`](/home/john/elspeth/src/elspeth/core/landscape/journal.py#L82)).

I verified the behavior locally against SQLAlchemy 2.0.45 with the journal attached to an in-memory SQLite engine:

1. Outer transaction inserts row `1`
2. `begin_nested()` savepoint inserts row `2`
3. Savepoint rollback executes
4. Outer transaction inserts row `3`
5. Outer commit flushes the journal

Observed result:
- Database rows after commit: `[(1,), (3,)]`
- Journal buffer flushed: records for inserts `1`, `2`, and `3`

So the journal emits a committed backup record for row `2` even though that write was rolled back.

The existing tests only cover full commit/rollback of a single flat buffer and do not exercise nested transactions or savepoints ([`test_journal.py`](/home/john/elspeth/tests/unit/core/landscape/test_journal.py#L331), [`test_journal.py`](/home/john/elspeth/tests/unit/core/landscape/test_journal.py#L395), [`test_journal.py`](/home/john/elspeth/tests/unit/core/landscape/test_journal.py#L750)).

## Root Cause Hypothesis

The journal implementation assumes one connection equals one transaction buffer. That assumption is wrong once SQLAlchemy savepoints or nested transactions are used. Writes are buffered before commit, but rollback handling only understands full-connection rollback, not partial rollback of nested work. As a result, rolled-back inner statements remain in the buffer and are later flushed by the outer commit.

## Suggested Fix

Make buffering transaction-aware instead of connection-flat.

A safe approach is to maintain a stack of buffers in `conn.info`, one per transaction/savepoint depth:
- Append writes to the current top buffer.
- On savepoint begin, push a new buffer.
- On savepoint rollback, discard only the top buffer.
- On savepoint release/commit, merge the top buffer into its parent.
- On outer commit, flush only the root buffer.
- On outer rollback, clear the full stack.

If SQLAlchemy transaction/savepoint events are used, `attach()` should listen for the nested transaction/savepoint lifecycle in addition to `commit`/`rollback`. Add an integration test that reproduces:
- outer insert
- nested insert
- nested rollback
- outer insert
- outer commit

and asserts that only the outer committed writes reach the journal.

## Impact

The emergency JSONL backup stream can contain writes that never committed. In a recovery scenario, replaying the journal could resurrect rolled-back rows. That breaks the project’s auditability guarantee that recorded state reflects what actually happened, and it creates silent divergence between the database and the backup record.
