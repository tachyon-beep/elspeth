## Summary

`AuditedLLMClient.chat_completion()` catches all exceptions across both external-call logic and internal/audit logic, so internal failures get misclassified as LLM call errors and can be turned into row-level `TransformResult.error` instead of crashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py
- Line(s): 318-464
- Function/Method: `AuditedLLMClient.chat_completion`

## Evidence

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/clients/llm.py:318-354
try:
    response = self._client.chat.completions.create(**sdk_kwargs)
    ...
    self._recorder.record_call(... status=CallStatus.SUCCESS, ...)
    ...
except Exception as e:
    ...
    self._recorder.record_call(... status=CallStatus.ERROR, ...)
    ...
    raise LLMClientError(str(e), retryable=False) from e
```

The `try` block includes not only the external SDK call, but also internal processing and audit recording. Any internal exception in that block is treated as an external LLM failure.

Downstream, non-retryable `LLMClientError` is converted into a non-crashing transform error:

```python
# /home/john/elspeth-rapid/src/elspeth/plugins/llm/base.py:338-346
except LLMClientError as e:
    if e.retryable:
        raise
    return TransformResult.error({"reason": "llm_call_failed", "error": str(e)}, retryable=False)
```

So internal bugs/audit-recording failures can be silently reclassified as "LLM call failed" row outcomes.

## Root Cause Hypothesis

Error-classification logic for external failures was implemented as a broad catch-all around the whole method, instead of being scoped to the external boundary (SDK call + boundary parsing). That violates the project rule that system-owned code bugs should crash, not be masked as data/external errors.

## Suggested Fix

Narrow exception handling to only external-boundary operations. Let internal/audit failures propagate.

- Wrap only the SDK call and immediate response-boundary parsing in `try/except`.
- Keep `self._recorder.record_call(...SUCCESS...)` and related internal operations outside that broad catch.
- Preserve current error-recording path for true external failures only.

## Impact

- Internal defects can be mislabeled as external-call failures.
- Rows may be quarantined/errored instead of hard-failing the run.
- Audit semantics become misleading ("provider failed" when the framework failed).
- Violates CLAUDE.md plugin-ownership/tier-model crash-vs-mask expectations.
