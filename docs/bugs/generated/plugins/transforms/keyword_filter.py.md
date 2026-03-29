## Summary

Explicitly configured scan fields that are absent from a row are silently skipped, so `keyword_filter` reports the row as successfully filtered even though one of the operator-required fields was never inspected.

## Severity

- Severity: major
- Priority: P1

## Location

- File: [/home/john/elspeth/src/elspeth/plugins/transforms/keyword_filter.py](/home/john/elspeth/src/elspeth/plugins/transforms/keyword_filter.py)
- Line(s): 155-163
- Function/Method: `KeywordFilter.process`

## Evidence

In the target file, explicitly configured fields are treated as optional at runtime:

```python
fields_to_scan = get_fields_to_scan(self._fields, row)
named_fields = self._fields != "all"

for field_name in fields_to_scan:
    if field_name not in row:
        continue  # Skip fields not present in this row
```

Source: [/home/john/elspeth/src/elspeth/plugins/transforms/keyword_filter.py#L155](/home/john/elspeth/src/elspeth/plugins/transforms/keyword_filter.py#L155)

That means a config like `fields: ["content", "optional_field"]` will return `TransformResult.success(..., success_reason={"action": "filtered"})` when `optional_field` is missing, even though the operator explicitly asked for that field to be scanned.

The repository’s other security transforms implement the opposite behavior: missing explicitly named fields fail closed with `missing_field`:

```python
if field_name not in row:
    if all_mode:
        continue
    return TransformResult.error(
        {"reason": "missing_field", "field": field_name},
        retryable=False,
    )
```

Source: [/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py#L245](/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py#L245)

The current test suite for `keyword_filter` encodes the unsafe behavior as expected success:

```python
def test_skips_missing_configured_field(self) -> None:
    ...
    row = {"content": "safe data", "id": 1}
    result = transform.process(make_pipeline_row(row), make_context())
    assert result.status == "success"
```

Source: [/home/john/elspeth/tests/unit/plugins/transforms/test_keyword_filter.py#L402](/home/john/elspeth/tests/unit/plugins/transforms/test_keyword_filter.py#L402)

When a transform returns success, the executor records the node as `COMPLETED` with the supplied success reason; only error results generate the failed state plus routed error audit record:

Source: [/home/john/elspeth/src/elspeth/engine/executors/transform.py#L399](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L399) and [/home/john/elspeth/src/elspeth/engine/executors/transform.py#L417](/home/john/elspeth/src/elspeth/engine/executors/transform.py#L417)

So today the audit trail can say the row was successfully “filtered” even though a configured field was never examined.

## Root Cause Hypothesis

`keyword_filter` was implemented with generic “optional field” semantics instead of security-transform fail-closed semantics. The nearby Azure safety base class shows the intended policy for this subsystem, but `keyword_filter` kept an older permissive branch and its tests were written to preserve that behavior.

## Suggested Fix

Change the missing-field branch to distinguish `"all"` mode from explicitly named fields:

```python
if field_name not in row:
    if not named_fields:
        continue
    return TransformResult.error(
        {"reason": "missing_field", "field": field_name},
        retryable=False,
    )
```

Then update the tests so missing explicitly configured fields return `error`, and keep `"all"` mode permissive.

## Impact

Rows can pass through a security filter without all configured fields being checked. That is fail-open behavior in a blocking transform, and it also creates an audit-trail integrity problem: the run records a successful filter action for rows that were only partially evaluated.
