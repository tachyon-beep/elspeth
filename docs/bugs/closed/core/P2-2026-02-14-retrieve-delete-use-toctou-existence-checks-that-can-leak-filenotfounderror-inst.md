## Summary

`retrieve()`/`delete()` use TOCTOU existence checks that can leak `FileNotFoundError` instead of contractually expected missing-payload semantics (`KeyError` / `False`).

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/payload_store.py`
- Line(s): 136-139, 160-163
- Function/Method: `FilesystemPayloadStore.retrieve`, `FilesystemPayloadStore.delete`

## Evidence

Current code checks existence first, then performs file operation:

```python
if not path.exists():
    raise KeyError(...)
content = path.read_bytes()
```

and:

```python
if not path.exists():
    return False
path.unlink()
```

(see `src/elspeth/core/payload_store.py:136-139`, `src/elspeth/core/payload_store.py:160-163`).

If a file is removed between the check and `read_bytes()`/`unlink()`, `FileNotFoundError` can escape.

Protocol expects missing retrieval to manifest as `KeyError` (`src/elspeth/contracts/payload_store.py:53-56`), and callers rely on that:
- `src/elspeth/core/landscape/_query_methods.py:143-156` catches `KeyError` to map to `PURGED`.
- `src/elspeth/core/landscape/_call_recording.py:591-597` catches `KeyError` to return `None` for purged payload.

## Root Cause Hypothesis

Non-atomic “check then act” patterns were used for readability, but they break under concurrent filesystem changes and violate the payload-store contract expected by integration call sites.

## Suggested Fix

Make operations atomic from the caller perspective:
- `retrieve()`: attempt `read_bytes()` directly; convert `FileNotFoundError` to `KeyError`.
- `delete()`: attempt `unlink()` directly; return `False` on `FileNotFoundError`.

This preserves contract behavior under concurrent purge/delete activity.

## Impact

Replay/explain/verification paths may crash unexpectedly instead of cleanly reporting payloads as purged/missing, reducing reliability of audit introspection workflows.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/payload_store.py.md`
- Finding index in source report: 2
- Beads: pending
