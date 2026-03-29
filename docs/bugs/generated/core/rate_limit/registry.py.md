## Summary

`RateLimitRegistry.get_limiter()` forwards raw service names directly into `RateLimiter`, so common hostname-style keys like `api.example.com` crash at runtime instead of producing a limiter.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/rate_limit/registry.py`
- Line(s): 99-105
- Function/Method: `RateLimitRegistry.get_limiter`

## Evidence

`RateLimitRegistry` uses the caller-provided `service_name` as the `RateLimiter.name` without any normalization or validation:

```python
# src/elspeth/core/rate_limit/registry.py:99-105
if service_name not in self._limiters:
    service_config = self._config.get_service_config(service_name)
    self._limiters[service_name] = RateLimiter(
        name=service_name,
        requests_per_minute=service_config.requests_per_minute,
        persistence_path=self._config.persistence_path,
    )
```

But `RateLimiter` explicitly rejects anything except `^[a-zA-Z][a-zA-Z0-9_]*$`:

```python
# src/elspeth/core/rate_limit/limiter.py:145-152
if not _VALID_NAME_PATTERN.match(name):
    msg = (
        f"Invalid rate limiter name: {name!r}. "
        "Name must start with a letter and contain only "
        "alphanumeric characters and underscores."
    )
    raise ValueError(msg)
```

There is no earlier validation on rate-limit service keys:

```python
# src/elspeth/core/config.py:1094-1099
enabled: bool = Field(...)
default_requests_per_minute: int = Field(...)
persistence_path: str | None = Field(...)
services: dict[str, ServiceRateLimit] = Field(default_factory=dict, ...)
```

The public HTTP client example in the repo encourages exactly this invalid shape:

```python
# src/elspeth/plugins/infrastructure/clients/http.py:62-70
client = AuditedHTTPClient(
    ...
    base_url="https://api.example.com",
    headers={"Authorization": "Bearer ..."},
    limiter=registry.get_limiter("api.example.com"),
)
```

Tests also miss this path: the property tests only generate alphabetic limiter names, so dotted or hyphenated real-world service identifiers are never exercised (`tests/property/core/test_rate_limiter_properties.py:39-45`).

What the code does:
- Accepts any `service_name` at the registry boundary.
- Crashes later when `RateLimiter` tries to use that string as an internal bucket/table identifier.

What it should do:
- Accept real service identifiers at the registry API and translate them to a safe internal limiter key, or fail earlier with a registry-level contract that matches documented usage.

## Root Cause Hypothesis

The registry conflates two different concepts:
- External service identity used by callers/config (`api.example.com`, provider names, hostnames)
- Internal bucket identifier used by `RateLimiter`/SQLite table naming (`[A-Za-z][A-Za-z0-9_]*` only)

Because `RateLimitRegistry` passes the external identifier through unchanged, the first hostname-style caller hits a `ValueError` in the lower-level limiter.

## Suggested Fix

Keep `service_name` as the public lookup/config key, but derive a safe internal limiter name inside the registry before constructing `RateLimiter`.

For example:
- Look up config with the raw `service_name`
- Cache by raw `service_name`
- Convert the raw name to a safe bucket key for `RateLimiter.name`
- Detect collisions offensively if two raw names normalize to the same bucket key

A safe pattern would be something like:

```python
def _bucket_name(service_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", service_name)
    if not normalized or not normalized[0].isalpha():
        normalized = f"s_{normalized}"
    return normalized
```

Then use that derived name when instantiating `RateLimiter`, and add tests for:
- `api.example.com`
- names with hyphens
- names starting with digits
- collision handling

## Impact

Any caller that uses a hostname or other non-identifier service key will fail on first `get_limiter()` call, so rate limiting for generic HTTP-style integrations is not reliably usable. In practice this can abort plugin startup or the first external call path before work proceeds.
