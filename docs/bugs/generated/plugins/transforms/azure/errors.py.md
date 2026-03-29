## Summary

No concrete bug found in /home/john/elspeth/src/elspeth/plugins/transforms/azure/errors.py

## Severity

- Severity: trivial
- Priority: P3

## Location

- File: /home/john/elspeth/src/elspeth/plugins/transforms/azure/errors.py
- Line(s): 4-10
- Function/Method: MalformedResponseError

## Evidence

`[errors.py](/home/john/elspeth/src/elspeth/plugins/transforms/azure/errors.py#L4)` defines a single sentinel exception, `MalformedResponseError`, for Azure responses with invalid structure/types. On its own, that is not a bug.

The surrounding integration path appears consistent:

- `[base.py](/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py#L293)` catches `MalformedResponseError` and converts it into `TransformResult.error(..., retryable=False)`, which keeps malformed external responses row-scoped rather than crashing the run.
- `[content_safety.py](/home/john/elspeth/src/elspeth/plugins/transforms/azure/content_safety.py#L174)` raises `MalformedResponseError` for invalid JSON/response structure and `[content_safety.py](/home/john/elspeth/src/elspeth/plugins/transforms/azure/content_safety.py#L198)` explicitly fails closed when expected categories are missing.
- `[prompt_shield.py](/home/john/elspeth/src/elspeth/plugins/transforms/azure/prompt_shield.py#L149)` raises the same exception for invalid JSON, wrong top-level types, missing keys, wrong boolean types, and mismatched `documentsAnalysis` cardinality.
- `[http.py](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L219)` records HTTP request/response payloads to Landscape before telemetry, so malformed-response handling does not appear to break audit capture.
- Tests exercise these paths:
  - `[test_content_safety.py](/home/john/elspeth/tests/unit/plugins/transforms/azure/test_content_safety.py#L1145)` verifies non-capacity HTTP failures become non-retryable error results.
  - `[test_prompt_shield.py](/home/john/elspeth/tests/unit/plugins/transforms/azure/test_prompt_shield.py#L1288)` documents and tests the fail-closed regression around empty `documentsAnalysis`.
  - `[test_azure_safety_properties.py](/home/john/elspeth/tests/property/plugins/transforms/azure/test_azure_safety_properties.py#L341)` encodes malformed-response/fail-closed invariants for Azure safety parsing.

Given that evidence, I did not find a credible defect whose primary fix belongs in `errors.py`.

## Root Cause Hypothesis

No bug identified.

## Suggested Fix

No fix recommended for `/home/john/elspeth/src/elspeth/plugins/transforms/azure/errors.py`.

## Impact

No concrete breakage attributable to this file was confirmed. The current exception type appears to support the intended fail-closed behavior and integrates cleanly with audit recording and transform error propagation.
