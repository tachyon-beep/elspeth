# Analysis: src/elspeth/plugins/pooling/reorder_buffer.py

**Lines:** 162
**Role:** ReorderBuffer ensures results from concurrent thread pool workers are emitted in strict submission order. It captures timing metadata (submit timestamp, completion timestamp, buffer wait time) for the audit trail. Used exclusively within `PooledExecutor.execute_batch()` to reorder query-level results within a single row's parallel queries.
**Key dependencies:** Imports only stdlib (`time`, `dataclasses`, `threading.Lock`). Imported by `executor.py`. The `BufferEntry` dataclass is re-exported from `__init__.py` and consumed by `azure_multi_query.py`, `openrouter_multi_query.py`, and other LLM transforms for audit metadata.
**Analysis depth:** FULL

## Summary

This is a clean, focused module with correct thread safety and well-designed ordering semantics. The buffer is used in a tightly scoped context (within a single `execute_batch` call) where all submitters and completers are coordinated by the executor. I found one issue: the buffer's indices grow monotonically across batches without reset, which is benign for correctness but could theoretically cause confusion in audit metadata if indices are compared across batches. No critical issues found.

## Warnings

### [72-78] Buffer indices grow monotonically across batches, never reset

**What:** `_next_submit`, `_next_emit`, and `_complete_counter` are initialized once in `__init__` and never reset. Since `PooledExecutor` creates a single `ReorderBuffer` in its `__init__` and reuses it across all `execute_batch()` calls, indices increment forever. After batch 1 with 5 items (indices 0-4), batch 2 starts at index 5.

**Why it matters:** The `submit_index` and `complete_index` in `BufferEntry` represent global executor lifetime indices, not per-batch indices. The consumers in `azure_multi_query.py` use `entry.submit_index` for query ordering metadata in the audit trail. If the executor processes multiple batches (which happens when multiple rows flow through the pipeline), the `submit_index` for the second row's queries will start at N (where N is the first row's query count), not 0.

Looking at the consumer in `azure_multi_query.py` (line 802-808):
```python
query_ordering = [
    {
        "submit_index": entry.submit_index,
        "complete_index": entry.complete_index,
        "buffer_wait_ms": entry.buffer_wait_ms,
    }
    for entry in entries
]
```

This means the audit trail will have `submit_index` values like 0,1,2 for the first row and 3,4,5 for the second row, rather than 0,1,2 for both. The indices are still internally consistent (they monotonically increase and complete_index reflects true ordering), but they're not per-batch-relative.

**However:** The executor holds `_batch_lock` during `_execute_batch_locked`, and the buffer is only accessed under this lock, so there's no interleaving risk. The indices just aren't semantically "per batch." The existing test `test_stats_reset_between_batches` only checks `max_concurrent_reached`, not buffer indices.

### [147] `type: ignore[operator]` comment suggests type narrowing gap

**What:** Line 147 has `# type: ignore[operator]` for the subtraction `now - entry.complete_timestamp`. This is because `complete_timestamp` is declared as `float | None` on `_InternalEntry`, and while the code path guarantees it's `float` (because `is_complete` is `True`), mypy can't narrow it.

**Why it matters:** This is cosmetic -- the logic is correct since `is_complete` is only set to `True` when `complete_timestamp` is set. The same pattern applies to lines 152-155 with `# type: ignore[arg-type]`. This is a consequence of `_InternalEntry` using `None` defaults for fields that are always set together. An alternative would be to use a separate completed dataclass, but that would add complexity for minimal gain.

## Observations

### [16-17] Uses Python 3.12+ generic syntax `class BufferEntry[T]`

**What:** The file uses PEP 695 generic syntax (`class BufferEntry[T]`) rather than `Generic[T]`. This requires Python 3.12+. This is consistent with the project's Python version target.

### [49-70] ReorderBuffer is well-designed for its use case

**What:** The buffer's API is minimal and correct:
- `submit()` reserves a slot and returns an index
- `complete()` marks a slot as done
- `get_ready_results()` drains all completed-and-contiguous entries

The lock is held for each individual operation, and the operations are short (dict lookup/update), minimizing lock contention. The polling-based `get_ready_results()` is appropriate since the executor calls it in an `as_completed` callback loop.

### [159] Entry cleanup on emission via `del self._entries[self._next_emit]`

**What:** Entries are removed from the internal dict as they're emitted. This prevents memory growth proportional to total lifetime entries. Combined with the monotonically growing indices, the dict only ever holds entries for the current batch's unfinished items.

### Thread safety is correct but minimal

**What:** All public methods acquire `self._lock`. The lock is never held across `time.sleep()` or other blocking calls (there are none in this module). No deadlock is possible since there's only one lock and it's always acquired and released within a single method call.

### No eviction support (contrast with RowReorderBuffer)

**What:** Unlike `RowReorderBuffer` (in `plugins/batching/`), this buffer has no `evict()` method. This is correct because the executor guarantees all submitted items will complete (even if with an error result) -- the retry timeout in `_execute_single` ensures every future resolves. However, if a `process_fn` hangs indefinitely (no timeout), the buffer would block forever. This is mitigated by the `max_capacity_retry_seconds` timeout in the executor, but only for capacity errors -- a truly hanging `process_fn` is not handled.

## Verdict

**Status:** SOUND
**Recommended action:** Consider resetting buffer indices between batches (add a `reset()` method called from `_execute_batch_locked`), but this is low priority since the current behavior is correct and the indices aren't directly user-visible. The monotonic growth could actually be useful for debugging cross-batch ordering issues.
**Confidence:** HIGH -- The module is small, well-tested (including property-based tests with Hypothesis), and the threading model is straightforward.
