## Summary

Successful rows are misclassified as failures when input data contains a field named `error`, causing silent output corruption.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py
- Line(s): 510, 514, 750, 761
- Function/Method: `_process_batch`, `_process_single_row`

## Evidence

In `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py:750`, success returns the full row dict (`output = row.to_dict()`), which preserves arbitrary source fields.

In `/home/john/elspeth-rapid/src/elspeth/plugins/llm/openrouter_batch.py:510`, batch assembly treats any result containing key `"error"` as a failure branch:

```python
elif "error" in result:
    output_row = rows[idx].to_dict()
    output_row[self._response_field] = None
    output_row[f"{self._response_field}_error"] = result["error"]
```

So if input row already has `{"error": ...}` and the LLM call succeeds, that successful row is still routed into the error path, `llm_response` is overwritten to `None`, and model output is dropped.

## Root Cause Hypothesis

The method uses a plain dict sentinel (`"error" in result`) that collides with legitimate user fields from `row.to_dict()`.

## Suggested Fix

Use a collision-proof internal result type instead of key-presence detection. For example, return a typed wrapper from `_process_single_row`:

```python
@dataclass
class _RowOutcome:
    ok: bool
    row: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
```

Then branch on `outcome.ok` in `_process_batch`, not on `"error" in result`.

## Impact

Rows with an `error` field can be silently rewritten as failed, losing valid LLM outputs and producing incorrect audit-visible row data. This is silent data loss/corruption in batch output semantics.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/openrouter_batch.py.md`
- Finding index in source report: 1
- Beads: pending
