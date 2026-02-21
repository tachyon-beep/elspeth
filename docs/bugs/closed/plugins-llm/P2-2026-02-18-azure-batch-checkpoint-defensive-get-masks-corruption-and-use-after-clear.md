## Summary

`AzureBatchLLMTransform` reads checkpoint data using `.get()` with fallback defaults instead of direct `[]` access. This masks Tier 1 data corruption (missing keys default silently) and hides a use-after-clear ordering bug where `submitted_at` and `row_count` are read after `_clear_checkpoint()` empties the dict.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `src/elspeth/plugins/llm/azure_batch.py`
- Lines: 720-722, 816, 826, 849-858, 869-878, 856, 866, 880, 890
- Functions: `_record_per_row_failure_calls`, `process` (resume path)

## Evidence

**Write side** (line 678) always produces:
```python
checkpoint_data = {
    "batch_id": batch.id,
    "input_file_id": batch_file.id,
    "row_mapping": row_mapping,
    "template_errors": template_errors,
    "submitted_at": datetime.now(UTC).isoformat(),
    "row_count": len(rows),
    "requests": requests_by_id,
}
```

**Read side** used `.get()` with silent fallbacks:
- `checkpoint.get("batch_id", "unknown")` — fabricates a batch ID
- `checkpoint.get("submitted_at")` → `latency_ms = 0.0` — fabricates a measurement
- `checkpoint.get("row_count", len(rows))` — silently guesses from current row count

**Use-after-clear bug:** In the `failed` and `cancelled` branches, `_clear_checkpoint(ctx)` was called before reading `submitted_at` and `row_count`. Since `checkpoint` is a reference to the same dict, the keys are gone by the time they're accessed. The `.get()` pattern masked this by returning `None`/defaults silently.

## Root Cause

Checkpoint data is Tier 1 (our serialization format). Defensive `.get()` access treats it as Tier 3, hiding both corruption and an ordering bug.

## Fix Applied

1. Changed all checkpoint reads from `.get()` to direct `[]` access
2. Reordered `failed` and `cancelled` branches to extract `submitted_at` and `row_count` before `_clear_checkpoint(ctx)`
3. Fixed test fixture (`TestAzureBatchLLMTransformTimeout`) that was missing `"requests"` key

## Impact

- Silent audit fabrication: `latency_ms = 0.0` and `batch_id = "unknown"` could appear in Langfuse traces, undermining audit integrity
- Data corruption goes undetected: missing checkpoint keys silently produce wrong values instead of crashing
