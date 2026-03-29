## Summary

Per-row LLM call audit writes fail open in `azure_batch.py`, so the transform can return success or terminal batch errors even when required call records were never persisted.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py
- Line(s): 733-746, 1314-1326, 1442-1453
- Function/Method: `_record_per_row_failure_calls`, `_download_results`

## Evidence

`azure_batch.py` explicitly documents that it will not fail when per-row audit recording fails:

```python
# src/elspeth/plugins/transforms/llm/azure_batch.py:733-745
# NOTE: Not wrapped in AuditIntegrityError — per-row recording in batch
# loop. Crashing here would lose all progress for remaining rows.
ctx.record_call(...)
```

The same fail-open pattern appears when recording missing-result errors and final per-row LLM calls after result assembly:

```python
# src/elspeth/plugins/transforms/llm/azure_batch.py:1311-1326
# NOTE: Not wrapping record_call in AuditIntegrityError here because this
# is a per-row error recording inside a batch result loop.
ctx.record_call(...)

# src/elspeth/plugins/transforms/llm/azure_batch.py:1439-1453
# NOTE: Not wrapping record_call in AuditIntegrityError here because this
# is a per-row result recording inside a batch loop.
ctx.record_call(...)
```

But ELSPETH’s audit contract says the opposite:

- `CLAUDE.md:17-18` says “No inference - if it's not recorded, it didn't happen” and requires complete lineage.
- `src/elspeth/contracts/plugin_context.py:198-205` defines `record_call()` as the audit write path.
- `src/elspeth/contracts/plugin_context.py:367-368` re-raises `AuditIntegrityError` because audit integrity violations must crash.

So this file knowingly suppresses the must-fire rule for the exact per-row LLM calls that make Azure batch outputs attributable. If any `ctx.record_call()` raises mid-loop, some rows will have output data but no corresponding `calls` record.

## Root Cause Hypothesis

The transform was optimized for “salvage the rest of the batch” behavior, but that trades away the repository’s core invariant: audit completeness has priority over partial progress. The code treats per-row call recording as optional bookkeeping inside a loop instead of mandatory provenance for each submitted request.

## Suggested Fix

Fail closed on any per-row audit write that corresponds to an already-observed batch outcome.

Practical fix in this file:
- Wrap each per-row `ctx.record_call()` in `try/except Exception as exc`.
- Re-raise `AuditIntegrityError` with batch id, custom id, row index, and whether this was success/error/missing-result recording.
- Do not clear the checkpoint after a successful download unless all required per-row call records were persisted.

Example pattern:

```python
try:
    ctx.record_call(...)
except Exception as exc:
    raise AuditIntegrityError(
        f"Failed to record per-row LLM call for batch {checkpoint.batch_id!r}, "
        f"custom_id={custom_id!r}, row_index={row_index}."
    ) from exc
```

## Impact

A run can produce Azure batch outputs that cannot be fully explained later. `explain(token_id)` may show the batch completed but omit the actual per-row LLM request/response/error record for some rows. That violates ELSPETH’s audit guarantees and creates silent lineage gaps in exactly the subsystem meant to preserve async batch traceability.
---
## Summary

Rows that fail inside Azure batch processing are emitted as successful output rows without `quarantined_indices`, so the engine records their original tokens as `CONSUMED_IN_BATCH` instead of `QUARANTINED`.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/llm/azure_batch.py
- Line(s): 1261-1272, 1296-1306, 1331-1398, 1504-1514
- Function/Method: `_download_results`

## Evidence

`azure_batch.py` turns multiple per-row failure modes into synthetic output rows:

```python
# src/elspeth/plugins/transforms/llm/azure_batch.py:1261-1272
output_row[self._response_field] = None
output_row[f"{self._response_field}_error"] = {
    "reason": "template_rendering_failed",
    "error": error_msg,
}
output_rows.append(output_row)

# src/elspeth/plugins/transforms/llm/azure_batch.py:1296-1306
output_row[self._response_field] = None
output_row[f"{self._response_field}_error"] = error_info
output_rows.append(output_row)
row_errors.append({"row_index": idx, "reason": error_reason})

# src/elspeth/plugins/transforms/llm/azure_batch.py:1331-1398
# api_error / invalid_response_structure / content_filtered all append output_rows
```

But the final `success_multi()` metadata contains only batch size and audit metadata:

```python
# src/elspeth/plugins/transforms/llm/azure_batch.py:1504-1514
return TransformResult.success_multi(
    ...,
    success_reason={
        "action": "enriched",
        "fields_added": [self._response_field],
        "metadata": {
            "batch_size": len(output_rows),
            **batch_audit,
        },
    },
)
```

The engine relies on `success_reason["metadata"]["quarantined_indices"]` to mark original buffered tokens as quarantined:

```python
# src/elspeth/engine/processor.py:717-745
if "quarantined_indices" in metadata:
    quarantined_index_set = set(metadata["quarantined_indices"])
...
if i in quarantined_index_set:
    outcome=RowOutcome.QUARANTINED
else:
    outcome=RowOutcome.CONSUMED_IN_BATCH
```

This is not theoretical; another batch transform documents and tests the required contract:

```python
# src/elspeth/plugins/transforms/batch_replicate.py:237-242
success_reason["metadata"] = {
    ...
    "quarantined_indices": quarantined_indices,
}

# tests/unit/plugins/transforms/test_batch_replicate_integration.py:223-258
# "Without this, quarantined rows silently get CONSUMED_IN_BATCH"
```

So when Azure batch hits `template_rendering_failed`, `api_error`, `result_not_found`, `invalid_response_structure`, or `content_filtered`, the original token is still recorded as consumed, not quarantined.

## Root Cause Hypothesis

The transform mixes two incompatible models:

- Batch-transform contract: bad rows should be surfaced via `quarantined_indices` so the processor records correct terminal states.
- Row-enrichment contract: every row gets an output row, even failed ones, with `*_error` markers.

Because it returns success rows for failures but never supplies `quarantined_indices`, the processor has no way to distinguish failed rows from successful ones.

## Suggested Fix

Align this transform with the existing batch-processing contract.

Primary fix in this file:
- Track failing row indices for every per-row failure path.
- Include `quarantined_indices` in `success_reason["metadata"]`.
- Prefer not emitting synthetic output rows for quarantined inputs; instead return only successful rows plus structured failure metadata, matching `batch_replicate`.

If preserving error rows is required, this file still needs to stop claiming pure enrichment success; otherwise the processor contract is violated.

## Impact

Audit lineage becomes misleading: rows that never rendered, never got a usable Azure response, or were content-filtered appear as normally consumed batch members. Downstream nodes can receive synthetic “error rows” as if they were legitimate transform outputs, while the originating tokens are not marked `QUARANTINED`. That breaks terminal-state accuracy and misstates what happened to the affected data.
