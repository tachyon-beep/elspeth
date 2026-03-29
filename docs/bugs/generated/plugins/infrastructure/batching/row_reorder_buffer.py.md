## Summary

`RowReorderBuffer.complete()` and `evict()` trust only `ticket.sequence`, so a mismatched or forged `RowTicket` can complete/evict the wrong pending row instead of crashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/row_reorder_buffer.py
- Line(s): 242-246, 349-358
- Function/Method: `complete`, `evict`

## Evidence

`RowTicket` carries three identity fields: `sequence`, `row_id`, and `submitted_at`.

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/row_reorder_buffer.py:242-252
with self._lock:
    if ticket.sequence not in self._pending:
        raise KeyError(...)
    entry = self._pending[ticket.sequence]
    if entry.is_complete:
        raise ValueError(...)
    entry.result = result
    entry.completed_at = time.perf_counter()
    entry.is_complete = True
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/row_reorder_buffer.py:349-358
with self._lock:
    if ticket.sequence not in self._pending:
        return False
    entry = self._pending[ticket.sequence]
    if entry.is_complete:
        return False
    del self._pending[ticket.sequence]
```

Both methods ignore `ticket.row_id` and `ticket.submitted_at`. That means any `RowTicket` with the same sequence number is accepted, even if it does not belong to that pending entry.

That is especially dangerous because the caller keeps `ticket` and row identity separately:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/mixin.py:205-221
ticket = self._batch_buffer.submit(row_id)
self._batch_executor.submit(
    self._process_and_complete,
    ticket,
    token,
    row,
    ctx,
    processor,
)
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/batching/mixin.py:276-277
self._batch_buffer.complete(ticket, (token, result, state_id))
```

`ctx.token` is documented as being used by this subsystem for “FIFO ordering and audit attribution”:

```python
# /home/john/elspeth/src/elspeth/contracts/plugin_context.py:90-95
# Used by RowReorderBuffer for FIFO ordering and audit attribution.
token: TokenInfo | None = field(default=None)
```

If internal code ever pairs the wrong `ticket` with the right `token`, the buffer will silently mutate the slot for sequence `N`, but the emitted payload still carries the other row’s token. That violates the project rule that system-owned bugs must crash, not silently produce wrong lineage. Existing tests validate empty `row_id`, duplicate complete, eviction behavior, and sequencing, but there is no test that a mismatched `RowTicket` is rejected:
- `/home/john/elspeth/tests/unit/plugins/batching/test_row_reorder_buffer.py`
- `/home/john/elspeth/tests/property/plugins/batching/test_reorder_buffer_properties.py`

## Root Cause Hypothesis

The buffer treats `sequence` as the only authoritative key, even though `RowTicket` was designed to carry full submission identity. That loses the offensive-programming safeguard that should detect “wrong ticket for this row” as an internal invariant violation. Because `complete()` and `evict()` do not verify the rest of the ticket, a caller bug becomes silent state corruption instead of a fast crash.

## Suggested Fix

In both `complete()` and `evict()`, verify that the pending entry matches the full ticket identity before mutating buffer state.

Example shape:

```python
entry = self._pending[ticket.sequence]
if entry.row_id != ticket.row_id or entry.submitted_at != ticket.submitted_at:
    raise RuntimeError(
        f"Ticket identity mismatch for sequence {ticket.sequence}: "
        f"pending row_id={entry.row_id!r}, ticket row_id={ticket.row_id!r}"
    )
```

Then keep the existing `is_complete` checks. Add regression tests that manually construct a `RowTicket` with a valid sequence but wrong `row_id` or `submitted_at` and assert that both `complete()` and `evict()` fail loudly.

## Impact

A caller bug can silently attach one row’s result or eviction to another row’s buffer slot. In batching mode that can corrupt FIFO release semantics and, more importantly, break audit attribution by emitting a token/result combination that does not correspond to the original submission. This is exactly the kind of system-owned integrity bug ELSPETH is supposed to crash on immediately rather than recording misleading lineage.
