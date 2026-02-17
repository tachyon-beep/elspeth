## Summary

`OpenRouterMultiQuery._process_single_query()` calls `spec.build_template_context(row)` without wrapping in `try/except KeyError`. The Azure equivalent correctly catches the `KeyError` and returns `TransformResult.error()`, gracefully quarantining the row. OpenRouter lets the `KeyError` propagate and crashes the entire pipeline.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `src/elspeth/plugins/llm/openrouter_multi_query.py`
- Line(s): `198`
- Function/Method: `_process_single_query()`

## Evidence

Azure version (`azure_multi_query.py:189-198`) — correctly handles missing fields:

```python
try:
    synthetic_row = spec.build_template_context(row)
except KeyError as e:
    return TransformResult.error(
        {
            "reason": "missing_field",
            "error": str(e),
            "query": spec.output_prefix,
        }
    )
```

OpenRouter version (`openrouter_multi_query.py:198`) — bare call, no handling:

```python
synthetic_row = spec.build_template_context(row)
```

The `KeyError` raised at `multi_query.py:114` propagates uncaught, crashing the pipeline instead of quarantining the affected row.

## Root Cause Hypothesis

Code duplication between Azure and OpenRouter multi-query implementations. The Azure version was patched to handle the error; the OpenRouter version was not updated to match.

## Suggested Fix

Wrap `build_template_context` in OpenRouter's `_process_single_query()` with the same `try/except KeyError` pattern used in Azure:

```python
try:
    synthetic_row = spec.build_template_context(row)
except KeyError as e:
    return TransformResult.error(
        {
            "reason": "missing_field",
            "error": str(e),
            "query": spec.output_prefix,
        }
    )
```

## Trust Model

Per the Three-Tier Trust Model, `input_fields` referencing row data is a Tier 2 operation on row values — operations on row field values should be wrapped, not allowed to crash. The Azure version gets this right; OpenRouter should match.
