## Summary

Unhandled missing-input-field errors in `_process_single_query()` can crash the entire pipeline instead of quarantining just the bad row.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_multi_query.py`
- Line(s): 187-188
- Function/Method: `_process_single_query`

## Evidence

`_process_single_query()` calls `spec.build_template_context(row)` before any `try/except`:

- `src/elspeth/plugins/llm/azure_multi_query.py:187-193`

That helper explicitly raises `KeyError` when an input field is missing:

- `src/elspeth/plugins/llm/multi_query.py:113-115`

Because the exception is uncaught in the transform path, BatchTransform machinery treats it as a plugin exception and re-raises to orchestrator (pipeline-level failure path):

- `src/elspeth/plugins/batching/mixin.py:248-264`
- `src/elspeth/engine/batch_adapter.py:121-122`
- `src/elspeth/engine/executors/transform.py:255-283`

This conflicts with project policy for user-data missing fields:

- `CLAUDE.md:205-207` ("User data missing field -> Quarantine row, continue")
- `CLAUDE.md:187-188` ("Operating on row field values -> wrap ops, return error result, quarantine row")

## Root Cause Hypothesis

The transform assumes missing `input_fields` is always a config/programming bug and allows `KeyError` to escape, but in production this can occur on per-row data variance. The method lacks a row-level error conversion at this boundary.

## Suggested Fix

Catch `KeyError` around template-context construction in this file and convert it to `TransformResult.error(...)` (non-retryable), including query/field context.

Example shape:

```python
try:
    synthetic_row = spec.build_template_context(row)
except KeyError as e:
    return TransformResult.error(
        {
            "reason": "missing_field",
            "error": str(e),
            "query": spec.output_prefix,
        },
        retryable=False,
    )
```

## Impact

A single malformed row can terminate transform execution for the attempt and fail pipeline progress, violating expected quarantine behavior and reducing resilience/audit continuity for mixed-quality input datasets.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/azure_multi_query.py.md`
- Finding index in source report: 1
- Beads: pending
