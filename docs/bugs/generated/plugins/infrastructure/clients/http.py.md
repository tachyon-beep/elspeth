## Summary

Broad `except Exception` handling in the HTTP client misclassifies internal/audit failures as HTTP call failures, and can write a false `CallStatus.ERROR` record for a request that actually succeeded.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py
- Line(s): 320-402, 536-714
- Function/Method: `_execute_request`, `get_ssrf_safe`

## Evidence

`_execute_request()` wraps the entire post-response path in a broad `try/except`:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:320-402
try:
    response = self._client.post(...) / get(...)
    ...
    response_body = self._parse_response_body(response, full_url)
    ...
    self._record_and_emit(...)
    return response
except (FrameworkBugError, AuditIntegrityError):
    raise
except Exception as e:
    self._record_and_emit(... status=CallStatus.ERROR, error_data=HTTPCallError(...))
    raise
```

That means all of these are treated as if the external HTTP call failed:

- response parsing bugs in our code
- DTO construction bugs in `HTTPCallResponse(...)`
- generic `record_call()` failures from Landscape/payload-store persistence

The recorder path does raise ordinary exceptions, not only `FrameworkBugError`/`AuditIntegrityError`; `record_call()` goes through payload serialization and DB insert work in [`/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:560-623`](/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py#L560). If that first audit write fails after the HTTP response was already received, the `except Exception` block records a second synthetic error for the same call index, turning an audit-system failure into a fake HTTP failure.

`get_ssrf_safe()` has the same shape:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:616-714
call = self._recorder.record_call(...)
...
except Exception as e:
    _ = self._recorder.record_call(... status=CallStatus.ERROR, error=HTTPCallError(...))
    ...
    raise
```

So a successful SSRF-safe fetch can also be mis-recorded as an HTTP error if the success-path audit write or response-processing code throws.

The LLM client explicitly avoids this exact pattern by keeping the success path outside the network `try/except` so internal bugs crash instead of being misclassified as provider failures: [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py:385-387`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/llm.py#L385).

Existing tests only cover the permanent-failure case where *every* `record_call()` attempt fails (`tests/unit/plugins/clients/test_http_telemetry.py:210-250`), so they do not catch the intermittent/first-write-only failure that produces the false error record.

## Root Cause Hypothesis

The request-execution methods were written with one catch-all recovery path for “anything went wrong,” but the code does not distinguish:

- real external-call failures
- internal response-processing bugs
- audit persistence failures after the external call already succeeded

That collapses different failure domains into a single `HTTPCallError`, which violates the repo rule that plugin/system bugs should crash, not be hidden as data/provider errors.

## Suggested Fix

Narrow the `try/except` blocks so they only cover the actual external request, then handle the success path outside that block.

For example:

- Catch request-layer exceptions around `self._client.post/get(...)` or `ssrf_client.get(...)`.
- Record `CallStatus.ERROR` only for genuine network/request failures.
- Move `_parse_response_body(...)`, DTO construction, and `record_call()` success recording outside the broad catch.
- If `record_call()` or DTO construction fails, re-raise immediately without writing a synthetic HTTP error record or emitting telemetry.

A safe shape is:

```python
try:
    response = self._client.post(...)
except Exception as exc:
    record_http_error(...)
    raise

# Success path outside catch: internal bugs/audit failures must crash
response_body = self._parse_response_body(response, full_url)
response_dto = HTTPCallResponse(...)
self._record_and_emit(...)
return response
```

Apply the same separation to `get_ssrf_safe()`.

## Impact

This can corrupt the legal audit trail by recording “HTTP failed” when the provider actually returned a response and the real failure was in ELSPETH’s own processing or audit subsystem. That breaks explainability, misleads retry/error handling, and makes incident analysis attribute blame to the external service instead of the real root cause.
---
## Summary

Malformed JSON responses are logged with raw body previews, creating an unauthorized parallel record of external call payloads outside the Landscape audit trail.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py
- Line(s): 165-181, 570-586
- Function/Method: `_parse_response_body`, `get_ssrf_safe`

## Evidence

Both JSON-parse-failure paths log raw response content:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:165-181
if "application/json" in content_type:
    parsed, error = _parse_json_strict(response.text)
    if error is not None:
        logger.warning(
            "JSON parse failed despite Content-Type: application/json",
            extra={
                "url": full_url,
                "status_code": response.status_code,
                "body_preview": response.text[:200],
                "error": error,
            },
        )
        return {
            "_json_parse_failed": True,
            "_error": error,
            "_raw_text": response.text[:10_000],
        }
```

The SSRF-safe path duplicates the same pattern at [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py:570-586`](/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L570).

The project’s logging policy says logging is not a parallel record of pipeline activity, and explicitly forbids logging call results because they belong in the `calls` table: [`/home/john/elspeth/.agents/skills/logging-telemetry-policy/SKILL.md:24-44`](/home/john/elspeth/.agents/skills/logging-telemetry-policy/SKILL.md#L24).

This client already records the parse failure and raw text into the audited response payload (`_json_parse_failed`, `_error`, `_raw_text`), so the log entry is duplicative and less controlled than the Landscape record.

## Root Cause Hypothesis

The warning was likely added for debugging malformed upstream responses, but it bypasses the repo’s observability model: once the response payload is already captured in `record_call()`, logging the same content is both redundant and policy-violating.

## Suggested Fix

Remove the `logger.warning(...)` calls that include response-body material. If operators still need visibility:

- rely on the audited `HTTPCallResponse.body` fields already being recorded, or
- emit telemetry without raw payload content, or
- log only a minimal non-payload message if the audit/telemetry systems themselves fail

At minimum, do not log `body_preview`.

## Impact

Malformed external responses can contain tokens, error pages, PII, or other sensitive data. This code copies part of that payload into ephemeral logs, outside the canonical audit store and its retention/query model. It also violates the project rule that external call results should be recorded in Landscape, not duplicated in logs.
