## Summary

The audited HTTP client constructs `request_data`, `response_data`, and `error_data` dicts as `dict[str, Any]` and passes them to `record_call()`. These have consistent shapes (method, url, headers for requests; status_code, headers, body_size, body for responses) but no type enforcement across 8+ construction sites.

## Severity

- Severity: moderate
- Priority: P2

## Location

- File: `src/elspeth/plugins/clients/http.py` — Lines 459, 496, 503, 505, 659, 729, 738

## Evidence

```python
# Request shape (http.py:459)
request_data: dict[str, Any] = {
    "method": method,
    "url": full_url,
    "headers": self._filter_request_headers(merged_headers),
}

# Response shape (http.py:496)
response_data: dict[str, Any] = {
    "status_code": response.status_code,
    "headers": self._filter_response_headers(dict(response.headers)),
    "body_size": len(response.content),
    "body": response_body,
}
```

Conditional fields are added via `request_data["json"] = json` and `request_data["params"] = params`, making the shape harder to track.

## Proposed Fix

Create frozen dataclasses in `contracts/call_data.py`:

```python
@dataclass(frozen=True, slots=True)
class HTTPCallRequest:
    method: str
    url: str
    headers: dict[str, str]
    json: dict[str, Any] | None = None
    params: dict[str, str | int | float] | None = None
    resolved_ip: str | None = None       # SSRF-safe requests (http.py:659)
    hop_number: int | None = None         # Redirect tracking (http.py:911)
    redirect_from: str | None = None      # Redirect tracking (http.py:911)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "method": self.method,
            "url": self.url,
            "headers": self.headers,
        }
        # Conditional inclusion — must match pre-migration dict construction
        if self.method == "POST" and self.json is not None:
            result["json"] = self.json
        if self.method == "GET" and self.params is not None:
            result["params"] = self.params
        if self.resolved_ip is not None:
            result["resolved_ip"] = self.resolved_ip
        if self.hop_number is not None:
            result["hop_number"] = self.hop_number
        if self.redirect_from is not None:
            result["redirect_from"] = self.redirect_from
        return result

@dataclass(frozen=True, slots=True)
class HTTPCallResponse:
    status_code: int
    headers: dict[str, str]
    body_size: int
    body: dict[str, Any] | str | None  # Narrowed from Any — see _parse_response_body()
    redirect_count: int = 0  # Default 0 instead of None — no semantic distinction

@dataclass(frozen=True, slots=True)
class HTTPCallError:
    type: str
    message: str
    status_code: int | None = None  # Present for HTTP errors, absent for network errors
```

Each provides explicit `to_dict()` for Landscape serialization. Never use `dataclasses.asdict()`.

## Affected Subsystems

- `plugins/clients/http.py` — construction
- `core/landscape/_call_recording.py` — consumption via `record_call()`

## Related Bugs

Part of a systemic pattern: 10 open bugs (all 2026-02-19) where `dict[str, Any]` crosses into the Landscape audit trail. See LLM client bug for full categorization (Category A/B split).

Precedent: `TokenUsage` frozen dataclass (`contracts/token_usage.py`, commit `dffe74a6`).

## Review Board Analysis (2026-02-19)

Four-agent review board assessed the proposed fix. Verdict: **Approve with changes**.

### Critical Design Changes Required

1. **Three distinct request shapes exist** — standard (`http.py:459`), SSRF-safe (`http.py:659`), and redirect hop (`http.py:911`) produce different key sets. One `HTTPCallRequest` with optional fields handles all three, but `to_dict()` must conditionally include only the keys that the original path included, or audit hashes diverge.
2. **Split error type: `HTTPCallError` (not shared `ExternalCallError`)** — HTTP errors at `http.py:505-509` include `status_code`, while network errors at `http.py:534-537` don't. LLM errors have `retryable` instead. These are structurally different and must not be collapsed.
3. **Method-conditional fields in `to_dict()`** — `http.py:464-467` adds `"json"` for POST, `"params"` for GET. `to_dict()` must replicate this exact conditional logic, not emit both as `None`.
4. **Narrow `body: Any`** — `_parse_response_body()` returns `dict | str | None`. Use `dict[str, Any] | str | None` instead of bare `Any` to preserve the migration's purpose on the response side.
5. **Use `redirect_count: int = 0`** instead of `int | None` — zero and None have no semantic distinction in the audit trail; `0` gives consumers a consistent integer.

### Hash Stability Risk (Critical)

Same as LLM client bug — RFC 8785 is sensitive to key presence. `to_dict()` must emit the exact same key set per request variant as the pre-migration dict construction. A `"json": null` key that was previously absent changes the hash of every historical POST audit record.

### record_call() Interface Design

Uses the same `CallData` protocol as the LLM client bug — see that bug for details.

### Required Tests

- **Shape-per-variant tests**: one test per HTTP path (POST, GET, SSRF, redirect hop) verifying exact key set from `to_dict()` matches pre-migration dict
- **Hash stability regression**: old dict vs new `to_dict()` must produce identical `stable_hash()`
- **Error shape tests**: HTTP error (has `status_code`) vs network error (no `status_code`)
- ~10 test assertion sites in `test_audited_http_client.py` will need updating
