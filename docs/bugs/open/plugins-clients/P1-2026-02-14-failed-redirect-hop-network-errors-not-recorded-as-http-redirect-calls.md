## Summary

Failed redirect-hop network errors in `get_ssrf_safe()` are not recorded as `HTTP_REDIRECT` calls, creating an audit-trail gap for real external requests.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/clients/http.py
- Line(s): 900-914, 934-942, 788-803
- Function/Method: `_follow_redirects_safe`, `get_ssrf_safe`

## Evidence

`_follow_redirects_safe()` records redirect hops only after `hop_client.get(...)` returns successfully:

```python
with httpx.Client(...) as hop_client:
    response = hop_client.get(...)   # if this raises, no hop record is written

...
self._recorder.record_call(
    call_type=CallType.HTTP_REDIRECT,
    ...
)
```

In `get_ssrf_safe()`, the outer `except` records only the top-level HTTP call using the original request metadata:

```python
request_data = {
    "method": "GET",
    "url": request.original_url,
    "resolved_ip": request.resolved_ip,
    ...
}
...
except Exception as e:
    self._recorder.record_call(
        call_type=CallType.HTTP,
        request_data=request_data,
        error={"type": type(e).__name__, "message": str(e)},
    )
```

So if a redirect hop fails (timeout/connect error), the failing hop URL/IP/hop number are not captured as a redirect call, despite being a distinct outbound request.

## Root Cause Hypothesis

Hop-level recording is placed only on the success path in `_follow_redirects_safe()`. Exceptions from the hop request escape to `get_ssrf_safe()` before hop metadata is persisted.

## Suggested Fix

Wrap each redirect-hop request in `try/except` inside `_follow_redirects_safe()` and always record a `CallType.HTTP_REDIRECT` row for attempted hops, including failure details.

```python
hop_call_index = self._next_call_index()
hop_request_data = {...}

hop_start = time.perf_counter()
try:
    with httpx.Client(...) as hop_client:
        response = hop_client.get(...)
    hop_latency_ms = ...
    self._recorder.record_call(... status=CallStatus.SUCCESS/ERROR, response_data=...)
except Exception as e:
    hop_latency_ms = ...
    self._recorder.record_call(
        ...,
        call_type=CallType.HTTP_REDIRECT,
        status=CallStatus.ERROR,
        request_data=hop_request_data,
        error={"type": type(e).__name__, "message": str(e)},
        latency_ms=hop_latency_ms,
    )
    raise
```

## Impact

Audit completeness is broken for redirect-chain failures: real outbound calls disappear from redirect-hop lineage, weakening traceability and incident forensics.
