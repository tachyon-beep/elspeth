## Summary

On post-upload audit-recording failure, `AzureBlobSink` records incorrect request metadata (`overwrite=True`) for a call that was actually executed with `overwrite=False`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_sink.py
- Line(s): 578, 583, 587, 621-629
- Function/Method: `write`

## Evidence

Upload uses `upload_overwrite` at call time:

```python
upload_overwrite = self._overwrite or self._has_uploaded
blob_client.upload_blob(content, overwrite=upload_overwrite)
self._has_uploaded = True
ctx.record_call(status=SUCCESS, request_data={"overwrite": upload_overwrite}, ...)
```

If `ctx.record_call` in the success path fails, control enters `except`, where error call request metadata is recomputed from mutable state:

```python
ctx.record_call(
    status=ERROR,
    request_data={"overwrite": self._overwrite or self._has_uploaded},
    ...
)
```

Because `_has_uploaded` was set `True` immediately after upload, the error record can claim `overwrite=True` even when the actual upload call used `overwrite=False`.
Repro (executed): first upload argument was `overwrite=False`; subsequent error call recorded `overwrite=True`.

This path is reachable and tested for post-upload record failure in `tests/unit/plugins/transforms/azure/test_blob_sink.py:728-764` (but overwrite parity is not asserted).

## Root Cause Hypothesis

Error-path call metadata is recomputed from mutated instance state (`_has_uploaded`) instead of reusing the original per-attempt `upload_overwrite` value.

## Suggested Fix

Persist attempt-local overwrite intent and reuse it in both success and error `ctx.record_call` payloads, e.g., initialize `upload_overwrite` before `try` and use that variable in both branches.

## Impact

- Audit trail request metadata can be factually wrong in a failure mode.
- Complicates forensic reconstruction of what was actually sent to Azure.
- Violates strict audit integrity expectations for external call records.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/azure/blob_sink.py.md`
- Finding index in source report: 2
- Beads: pending
