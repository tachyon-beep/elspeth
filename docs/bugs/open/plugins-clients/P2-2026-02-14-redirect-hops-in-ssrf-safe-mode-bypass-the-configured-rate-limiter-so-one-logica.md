## Summary

Redirect hops in SSRF-safe mode bypass the configured rate limiter, so one logical call can issue many unthrottled network requests.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/clients/http.py
- Line(s): 640, 872-914
- Function/Method: `get_ssrf_safe`, `_follow_redirects_safe`

## Evidence

Rate limiting is acquired once at entry to `get_ssrf_safe()`:

```python
self._acquire_rate_limit()
```

But `_follow_redirects_safe()` performs additional outbound `hop_client.get(...)` calls per redirect without another limiter acquire.

A redirect chain can therefore make up to `max_redirects` extra requests while consuming only one limiter token.

## Root Cause Hypothesis

Limiter usage was implemented at the top-level API-call boundary, but redirect hops (which are separate outbound requests) were added later without integrating per-hop throttling.

## Suggested Fix

Acquire the limiter before each redirect-hop request in `_follow_redirects_safe()`:

```python
while response.is_redirect and redirects_followed < max_redirects:
    ...
    self._acquire_rate_limit()
    with httpx.Client(...) as hop_client:
        response = hop_client.get(...)
```

Optionally add a regression test asserting limiter `acquire()` count equals `1 + redirects_followed`.

## Impact

Quota/politeness enforcement is undercounted for redirect-heavy targets, which can trigger upstream rate-limit violations or burst traffic beyond configured limits.

## Triage

- Status: open
- Source report: `docs/bugs/generated/plugins/clients/http.py.md`
- Finding index in source report: 2
- Beads: pending
