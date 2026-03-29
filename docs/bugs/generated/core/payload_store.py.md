## Summary

`FilesystemPayloadStore.store()` has a TOCTOU race: if a payload file is deleted after `path.exists()` returns `True` but before `path.read_bytes()`, the store raises `FileNotFoundError` instead of recreating the blob, so a concurrent purge can crash otherwise-valid audit writes.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/payload_store.py
- Line(s): 93-104
- Function/Method: `FilesystemPayloadStore.store`

## Evidence

`store()` checks for an existing blob, then immediately reads it:

```python
if path.exists():
    existing_content = path.read_bytes()
    actual_hash = hashlib.sha256(existing_content).hexdigest()
```

Source: `/home/john/elspeth/src/elspeth/core/payload_store.py:93-104`

That sequence is not atomic. If another process/thread removes the blob between `exists()` and `read_bytes()`, `read_bytes()` raises `FileNotFoundError`, which is not handled here.

That race is reachable in normal integration flow because payloads are written before the DB row/ref update is recorded:

- row payloads: `/home/john/elspeth/src/elspeth/core/landscape/data_flow_repository.py:338-347`
- operation input/output payloads: `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:670-675` and `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:740-746`
- call payloads: `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:540-548`

Purge runs delete by hash with no locking against concurrent `store()` calls:

- existence check + delete loop: `/home/john/elspeth/src/elspeth/core/retention/purge.py:352-380`

Because payloads are content-addressable, a new active run can legitimately reuse a hash that purge previously judged safe based on an earlier snapshot. If purge deletes that file during the `exists()`/`read_bytes()` window, `store()` crashes even though rewriting the same content would be correct.

## Root Cause Hypothesis

The implementation treats “file exists” and “read existing bytes” as a stable state, but the payload store is shared mutable filesystem state. The code verifies an existing blob by first doing a separate `exists()` probe, which introduces a race against deletion. The method should be robust to disappearance of the file and fall back to the write path.

## Suggested Fix

Remove the `exists()` pre-check as the control point. Instead:

1. Try to read and verify the existing file directly.
2. If that read raises `FileNotFoundError`, proceed to the atomic temp-file write path.
3. Keep the integrity check for the “file exists and is readable” case.

A simple shape is:

```python
try:
    existing_content = path.read_bytes()
except FileNotFoundError:
    existing_content = None

if existing_content is not None:
    actual_hash = hashlib.sha256(existing_content).hexdigest()
    if not hmac.compare_digest(actual_hash, content_hash):
        raise payload_contracts.IntegrityError(...)
else:
    # existing atomic temp-file write path
```

This keeps the corruption detection behavior but makes `store()` idempotent under concurrent deletion.

## Impact

A concurrent retention purge can cause valid row/call/operation payload persistence to fail spuriously. Since payload storage happens on the audit path before refs are recorded, the run can crash during audit recording even though the payload bytes are valid and should simply be re-stored. This is an integration-time reliability bug in a critical audit subsystem.
