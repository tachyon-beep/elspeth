## Summary

`load()` re-wraps Azure download exceptions with `type(e)(...)`, which can fail for Azure SDK exceptions with non-trivial constructors and mask the real failure.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py
- Line(s): 427-447
- Function/Method: `AzureBlobSource.load`

## Evidence

`blob_source.py` currently does:

```python
except Exception as e:
    ...
    raise type(e)(f"Failed to download blob '{self._blob_path}' from container '{self._container}': {e}") from e
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:427` and `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:446`

The sister Azure plugin already documents this constructor hazard and avoids it:

```python
# Use RuntimeError wrapper instead of type(e)(...) because Azure SDK
# exceptions ... have multi-parameter constructors ...
raise RuntimeError(...)
```

Source: `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_sink.py:641`

What it does now: may raise a new constructor error (or lose SDK exception context).
What it should do: raise a stable wrapper (or re-raise original) after audit recording.

## Root Cause Hypothesis

Exception wrapping pattern in `blob_source.py` diverged from the corrected Azure error-handling pattern used in `blob_sink.py`.

## Suggested Fix

Replace `raise type(e)(...)` with a stable wrapper (or plain `raise`), e.g.:

```python
raise RuntimeError(
    f"Failed to download blob '{self._blob_path}' from container '{self._container}': {e}"
) from e
```

## Impact

Download failures can become misreported or masked, reducing debuggability and making operational error handling inconsistent with the rest of the Azure plugin pack.
