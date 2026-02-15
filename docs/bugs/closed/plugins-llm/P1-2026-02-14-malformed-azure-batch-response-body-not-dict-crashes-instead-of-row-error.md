## Summary

Malformed Azure batch payloads with `response.body` not being a JSON object crash the transform instead of producing row-level errors.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/llm/azure_batch.py`
- Line(s): `1025-1032`, `1163-1169`
- Function/Method: `_download_results`

## Evidence

`_download_results()` validates that `response` is a dict and contains `"body"`, but it does not validate `response["body"]` type:

```python
# azure_batch.py:1025-1032
if has_response:
    response = result["response"]
    if not isinstance(response, dict):
        ...
    if "body" not in response:
        ...
```

Later it assumes `body` is a dict and calls `.get()`:

```python
# azure_batch.py:1163-1169
response = result["response"]
body = response["body"]
choices = body.get("choices")
```

I reproduced this with a synthetic output line `{"custom_id":"...","response":{"body":[]}}"`; the plugin raises `AttributeError: 'list' object has no attribute 'get'` (pipeline-crashing exception path).

## Root Cause Hypothesis

Boundary validation is incomplete at Tier-3 response parsing: it checks key presence but not structural type for `response.body`.

## Suggested Fix

At the Tier-3 validation block, enforce `response["body"]` is a dict before storing in `results_by_id`, and treat violations as malformed line/row error instead of letting later code access `.get()` on non-dicts.

Example direction:

```python
if "body" not in response or not isinstance(response["body"], dict):
    malformed_lines.append(...)
    continue
```

Optionally add a unit test for non-dict `response.body` to assert graceful error handling.

## Impact

A single malformed external response line can crash batch processing, turning a row-scoped external-data issue into a run-level failure and violating intended boundary handling behavior.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/llm/azure_batch.py.md`
- Finding index in source report: 1
- Beads: pending
