## Summary

`ReorderBuffer` never resets its submission/completion counters after a batch is fully drained, so a reused `PooledExecutor` records per-batch query ordering with lifetime-wide indices instead of `0..n-1`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py
- Line(s): 71-73, 88-95, 117-120, 167-168
- Function/Method: `__init__`, `submit`, `complete`, `get_ready_results`

## Evidence

The buffer keeps three monotonic counters for its entire lifetime:

```python
self._next_submit: int = 0
self._next_emit: int = 0
self._complete_counter: int = 0
```

[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:71](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L71)  
[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:73](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L73)

`submit()` returns the current `_next_submit` and increments it, with no path that resets it when the buffer becomes empty:

```python
idx = self._next_submit
self._entries[idx] = _InternalEntry(...)
self._next_submit += 1
```

[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:89](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L89)  
[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:94](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L94)

Likewise `complete()` assigns `complete_index` from `_complete_counter` and increments it forever:

```python
entry.complete_index = self._complete_counter
...
self._complete_counter += 1
```

[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:117](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L117)  
[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:120](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L120)

`get_ready_results()` deletes emitted entries and advances `_next_emit`, but also never resets state when the buffer is drained:

```python
del self._entries[self._next_emit]
self._next_emit += 1
```

[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:167](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L167)  
[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py:168](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/reorder_buffer.py#L168)

This matters in real integration because the executor deliberately reuses one shared buffer across many `execute_batch()` calls:

```python
self._buffer: ReorderBuffer[TransformResult] = ReorderBuffer()
```

[/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py:122](/home/john/elspeth/src/elspeth/plugins/infrastructure/pooling/executor.py#L122)

The same executor is expected to process multiple batches sequentially; the test suite already does that:

[/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py:290](/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py#L290)

And the LLM transform keeps a `PooledExecutor` on the transform instance, so later rows reuse the same buffer:

```python
self._query_executor: PooledExecutor | None = PooledExecutor(pool_config) if pool_config is not None else None
```

[/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py:1036](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L1036)

So row 1 might record `submit_index` `[0,1,2]`, but row 2 on the same transform instance will record `[3,4,5]`. That contradicts the contract and current expectations that ordering metadata is per batch/query set:

```python
assert submit_indices == [0, 1, 2, 3, 4]
```

[/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py:750](/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py#L750)  
[/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py:752](/home/john/elspeth/tests/unit/plugins/llm/test_pooled_executor.py#L752)

## Root Cause Hypothesis

`ReorderBuffer` was implemented as if its counters described a single lifetime-wide stream, but the actual integration uses it as a per-batch ordering primitive inside a long-lived executor. The deletion logic drains entries correctly, yet it never reinitializes the indexing state once the buffer is empty, so later batches inherit stale counter offsets.

## Suggested Fix

Reset the indexing counters when `get_ready_results()` drains the last pending entry, for example:

```python
if not self._entries:
    self._next_submit = 0
    self._next_emit = 0
    self._complete_counter = 0
```

That reset belongs in `get_ready_results()` immediately after removing emitted entries, guarded by the existing lock. Add a regression test that runs two sequential batches through the same `PooledExecutor` and asserts the second batch again returns `submit_index == [0, ...]` and `complete_index` values in the second batch’s local range.

## Impact

The emitted query-order metadata becomes wrong after the first batch on any reused executor. Query results still arrive in the right order, but the audit context for later rows misstates “which query completed nth,” which weakens provenance and postmortem analysis. In ELSPETH terms, this is an audit-trail accuracy bug: the record stays complete, but part of the recorded ordering evidence is no longer truthful on a per-row basis.
