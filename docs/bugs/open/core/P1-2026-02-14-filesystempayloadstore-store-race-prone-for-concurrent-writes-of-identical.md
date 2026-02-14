## Summary

`FilesystemPayloadStore.store()` is race-prone for concurrent writes of identical content because all writers use the same deterministic temp file path (`<hash>.tmp`), which can raise unexpected exceptions and abort audit recording.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/payload_store.py`
- Line(s): 108-124
- Function/Method: `FilesystemPayloadStore.store`

## Evidence

`store()` uses a single temp filename per hash:

```python
temp_path = path.with_suffix(".tmp")
...
with open(temp_path, "wb") as f:
...
os.replace(temp_path, path)
```

This is in `src/elspeth/core/payload_store.py:108-114`. If two threads store identical bytes concurrently, they target the same `temp_path`. One thread can rename/unlink it while the other is still using it, causing `os.replace(...)`/cleanup failures (`src/elspeth/core/payload_store.py:121-124`).

This is reachable in real code paths:
- Parallel worker threads are used (`src/elspeth/plugins/pooling/executor.py:99`, `src/elspeth/plugins/pooling/executor.py:269`).
- Multi-query execution dispatches parallel work with shared state context (`src/elspeth/plugins/llm/base_multi_query.py:399-417`).
- Each external call persists request/response payloads via `payload_store.store(...)` (`src/elspeth/core/landscape/_call_recording.py:139-147`, `src/elspeth/core/landscape/_call_recording.py:365-372`).

## Root Cause Hypothesis

The implementation assumes a single writer per content hash during the write phase. Deduplicated content-addressable storage makes same-hash concurrent writes normal, but using one shared temp path creates a write-write race.

## Suggested Fix

Use per-attempt unique temp files (not deterministic `<hash>.tmp`) and then atomically rename to final path. Example approach:
- Create temp file via `tempfile.NamedTemporaryFile(delete=False, dir=path.parent, prefix=f"{content_hash}.", suffix=".tmp")`.
- Write+fsync temp.
- `os.replace(temp_file, path)` to commit atomically.
- Cleanup only the temp file created by that attempt.

Add a concurrency test that runs parallel `store()` calls with identical content and asserts no exceptions.

## Impact

Parallel external-call recording can fail non-deterministically, causing pipeline crashes and incomplete audit capture for request/response payload references.
