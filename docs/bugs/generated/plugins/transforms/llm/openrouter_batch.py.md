## Summary

`OpenRouterBatchLLMTransform` never reads or enforces `finish_reason`, so truncated, content-filtered, or tool-call responses can be emitted as successful batch outputs instead of terminal row errors.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [openrouter_batch.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py)
- Line(s): 691-743
- Function/Method: `_process_single_row`

## Evidence

In the target file, the response boundary validation stops after extracting `choices[0]["message"]["content"]` and only treats `None` as an error:

```python
# openrouter_batch.py
choices = data["choices"]
content = choices[0]["message"]["content"]
...
if content is None:
    return _RowFailure(error={"reason": "content_filtered", ...})

usage = TokenUsage.from_dict(data.get("usage"))
response_model = data.get("model")

self._tracer.record_success(... response_content=content, ...)
output[self._response_field] = content
```

Source: [openrouter_batch.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py#L691)

There is no extraction of `finish_reason`, no fail-closed check for `length`/`content_filter`/`tool_calls`, and no rejection of empty or non-string content before the row is marked successful.

The shared non-batch OpenRouter path does enforce exactly those conditions:

- Provider rejects non-string and empty content: [providers/openrouter.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/openrouter.py#L241), [providers/openrouter.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/openrouter.py#L246), [providers/openrouter.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/providers/openrouter.py#L255)
- Transform fails closed on bad `finish_reason`: [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L307)
- Tests assert truncated/content-filter/tool-calls must be errors, not successes: [test_transform.py](/home/john/elspeth/tests/unit/plugins/llm/test_transform.py#L286), [test_transform.py](/home/john/elspeth/tests/unit/plugins/llm/test_transform.py#L304), [test_transform.py](/home/john/elspeth/tests/unit/plugins/llm/test_transform.py#L321)

What the target code does:
- Treats any non-`None` `content` as success.

What it should do:
- Reject non-string and empty content at the Tier 3 boundary.
- Parse `finish_reason` and fail closed on non-`stop` terminal reasons, matching the shared provider/transform contract.

## Root Cause Hypothesis

`openrouter_batch.py` reimplements OpenRouter response parsing inline instead of reusing the validated provider path, and that duplicate logic omitted the later validation stages that the unified transform depends on.

## Suggested Fix

After extracting `choices[0]`, validate the same invariants the shared OpenRouter path enforces:

- Read `finish_reason`
- Reject non-string `content`
- Reject empty/whitespace content
- Convert non-`stop` finish reasons into `_RowFailure(...)`
- Only record tracer success and populate the output row after those checks pass

If possible, factor batch parsing through the same helper/provider logic used by the unified transform so both code paths share one validation contract.

## Impact

Rows can be recorded as successfully enriched when the provider actually signaled truncation, moderation, or tool-calls. That produces misleading batch output, incorrect downstream decisions, and an audit trail that says the row was enriched successfully even though the LLM completion was not a valid final text response.
---
## Summary

Successful batch rows omit `finish_reason` from `success_reason["metadata"]`, so the audit trail cannot distinguish confirmed `stop` from absent or unknown provider termination state.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: [openrouter_batch.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py)
- Line(s): 492-513, 717-720
- Function/Method: `_process_batch`, `_process_single_row`

## Evidence

The batch success metadata only includes batch size and template/lookup provenance:

```python
batch_audit = build_llm_audit_metadata(...)
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

Source: [openrouter_batch.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py#L492)

Earlier in `_process_single_row`, the code reads `usage` and `model`, but never extracts or preserves `finish_reason` at all:

```python
usage = TokenUsage.from_dict(data.get("usage"))
response_model = data.get("model")
```

Source: [openrouter_batch.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/openrouter_batch.py#L717)

The shared LLM transform explicitly records `finish_reason` into success metadata:

```python
"metadata": {
    "model": result.model,
    "finish_reason": _serialize_finish_reason(result.finish_reason),
    **result.usage.to_dict(),
    **audit_metadata,
}
```

Source: [transform.py](/home/john/elspeth/src/elspeth/plugins/transforms/llm/transform.py#L347)

There are dedicated tests asserting this audit requirement:

- [test_transform.py](/home/john/elspeth/tests/unit/plugins/llm/test_transform.py#L2492)
- [test_transform.py](/home/john/elspeth/tests/unit/plugins/llm/test_transform.py#L2508)

What the target code does:
- Drops `finish_reason` entirely for batch success cases.

What it should do:
- Persist serialized `finish_reason` in batch success metadata so the audit trail can distinguish `stop`, `None`, and unrecognized values.

## Root Cause Hypothesis

The batch plugin duplicated the success-metadata assembly instead of sharing the single-row transform’s audit metadata contract, and `finish_reason` was left out during that copy.

## Suggested Fix

Capture `finish_reason` during response parsing and include it in per-row or batch success metadata using the same serialization rule as the unified transform. If rows in a batch can have different finish reasons, store a per-row structure rather than a single batch-level scalar.

## Impact

Audit reconstruction loses a probative detail about how the provider terminated each completion. An investigator cannot tell whether a batch response ended cleanly (`stop`), had no reported finish reason (`null`), or returned an unrecognized termination state.
