## Summary

For terminal non-completed batch statuses (`failed`, `cancelled`, `expired`, local `batch_timeout`), submitted per-row LLM calls are never recorded before checkpoint data is cleared.

## Severity

- Severity: major
- Priority: P2 (downgraded from P1: batch-level failure IS recorded; gap is per-row audit granularity, not silent failure)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py`
- Line(s): `749-767`, `769-854`, `1230-1265`
- Function/Method: `_check_batch_status`, `_download_results`

## Evidence

Per-row LLM call recording exists only in `_download_results()` (completed path):

```python
# azure_batch.py:1230-1262
for custom_id, result in results_by_id.items():
    ...
    ctx.record_call(call_type=CallType.LLM, ...)
```

`_check_batch_status()` invokes `_download_results()` only when `batch.status == "completed"`:

```python
# azure_batch.py:749-767
if batch.status == "completed":
    return self._download_results(...)
```

For `failed`/`cancelled`/`expired`/`batch_timeout`, it returns `TransformResult.error(...)` and clears checkpoint without per-row `CallType.LLM` recording:

```python
# azure_batch.py:769-854
self._clear_checkpoint(ctx)
return TransformResult.error(...)
```

Integration evidence: processor error handling records outcomes but does not synthesize missing call records (`/home/john/elspeth-rapid/src/elspeth/engine/processor.py:545-591`).

I also reproduced a failed-batch case with one submitted request: only one call was recorded (`batches.retrieve` HTTP), and zero per-row LLM calls were recorded.

## Root Cause Hypothesis

Audit-call recording is coupled to the completed-results assembly path, so terminal failure paths bypass call emission and erase request context via checkpoint clearing.

## Suggested Fix

Before clearing checkpoint in terminal non-completed states, iterate `checkpoint["requests"]`/`row_mapping` and emit `CallType.LLM` error calls for each submitted request (include `batch_id`, terminal status, and available error details). Then clear checkpoint.

Also add tests for failed/cancelled/expired/timeout asserting per-row LLM call records are present.

## Impact

Audit lineage for submitted LLM requests is incomplete on terminal failure paths: operators can see batch-level failure but not row-level request-call records, weakening explainability and external-call trace completeness.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/azure_batch.py.md`
- Finding index in source report: 2
- Beads: pending
