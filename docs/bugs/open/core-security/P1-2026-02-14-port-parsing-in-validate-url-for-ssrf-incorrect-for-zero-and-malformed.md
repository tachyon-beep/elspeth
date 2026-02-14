## Summary

Port parsing in `validate_url_for_ssrf()` is incorrect: explicit `:0` is silently rewritten to default port, and malformed ports leak raw `ValueError` outside the documented exception contract.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth-rapid/src/elspeth/core/security/web.py
- Line(s): 210-213
- Function/Method: validate_url_for_ssrf

## Evidence

Current logic:

```python
if parsed.port:
    port = parsed.port
else:
    port = 443 if parsed.scheme.lower() == "https" else 80
```

Problems:

1. `:0` is treated as falsy and replaced with default port.
   - Repro with mocked DNS: `validate_url_for_ssrf("https://example.com:0/path")` returned `port=443`, `connection_url=https://...:443/path`.

2. Invalid ports (e.g. `:99999`) raise `ValueError` from `parsed.port` and escape the function.
   - Repro: `validate_url_for_ssrf("https://example.com:99999/path")` raises `ValueError: Port out of range 0-65535`.

This violates the function's own declared raises contract (`SSRFBlockedError` / `NetworkError`) in `/home/john/elspeth-rapid/src/elspeth/core/security/web.py:196-199`.

Integration impact is visible in `/home/john/elspeth-rapid/src/elspeth/plugins/transforms/web_scrape.py:185-187`, which catches `SSRFBlockedError`, `SSRFNetworkError`, and `TypeError` but not `ValueError`, so malformed row URL values crash transform execution instead of returning `TransformResult.error`.

Existing property tests cover explicit ports only from `1..65535` (`tests/property/plugins/web_scrape/test_ssrf_properties.py:418-426`), so `0` and out-of-range ports are untested.

## Root Cause Hypothesis

Port normalization uses truthiness instead of `None` checks and does not wrap `parsed.port` access to convert parser errors into the module's security/network error types.

## Suggested Fix

In `validate_url_for_ssrf()`:

- Read `parsed.port` once inside `try/except ValueError`.
- Convert invalid-port parser errors into `SSRFBlockedError` (invalid URL input).
- Use `is None` checks, not truthiness.
- Explicitly reject `port == 0` as invalid instead of silently defaulting.

Example shape:

```python
try:
    parsed_port = parsed.port
except ValueError as e:
    raise SSRFBlockedError(f"Invalid URL port: {e}") from e

if parsed_port is None:
    port = 443 if parsed.scheme.lower() == "https" else 80
elif parsed_port == 0:
    raise SSRFBlockedError("Invalid URL port: 0")
else:
    port = parsed_port
```

## Impact

- Tier-2 row values can crash processing due to uncaught `ValueError` (instead of non-retryable error result/quarantine path).
- `:0` URLs are audited as one destination but executed against another port, weakening traceability guarantees for external calls.
