## Summary

`validate_url_for_ssrf()` drops the explicit port from `SSRFSafeRequest.host_header`, so SSRF-safe requests to non-default ports send `Host: example.com` instead of `Host: example.com:8443`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/core/security/web.py`
- Line(s): 203-226, 266-279, 330-336
- Function/Method: `validate_url_for_ssrf`, `SSRFSafeRequest.sni_hostname`

## Evidence

`validate_url_for_ssrf()` correctly parses and preserves an explicit port:

```python
try:
    explicit_port = parsed.port
...
if explicit_port is not None:
    ...
    port = explicit_port
```

`web.py` then builds the request object with:

```python
return SSRFSafeRequest(
    original_url=url,
    resolved_ip=selected_ip,
    host_header=hostname,
    port=port,
    path=path,
    scheme=parsed.scheme.lower(),
)
```

That loses the original authority when the URL is `https://example.com:8443/...`; `hostname` is just `example.com`.

The caller in [`/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L510`](file:///home/john/elspeth/src/elspeth/plugins/infrastructure/clients/http.py#L510) uses that value verbatim:

```python
merged_headers = {
    **self._default_headers,
    **(headers or {}),
    "Host": request.host_header,
}
...
if request.scheme == "https":
    extensions["sni_hostname"] = request.sni_hostname
```

So the outbound SSRF-safe request to `https://93.184.216.34:8443/...` carries `Host: example.com`, not `Host: example.com:8443`. I also verified locally with `httpx.Request(...)` that httpx preserves exactly the supplied `Host` header; it does not add `:8443` for us.

The existing test coverage only checks that the numeric port is stored:

- [`/home/john/elspeth/tests/unit/core/security/test_web_ssrf_network_failures.py#L110`](file:///home/john/elspeth/tests/unit/core/security/test_web_ssrf_network_failures.py#L110) asserts `result.port == 8443`
- [`/home/john/elspeth/tests/unit/plugins/clients/test_http_redirects.py#L235`](file:///home/john/elspeth/tests/unit/plugins/clients/test_http_redirects.py#L235) only asserts `Host == "example.com"` for default-port cases

There is no test covering explicit-port `Host` header construction.

## Root Cause Hypothesis

`web.py` models `host_header` and `sni_hostname` as the same underlying value: the bare `parsed.hostname`. That is correct for TLS SNI, but not for HTTP authority. For non-default ports, the `Host` header must carry the authority including the port, while SNI must remain the hostname only. The current dataclass/API design conflates those two concepts.

## Suggested Fix

Compute and store `host_header` and `sni_hostname` separately in `validate_url_for_ssrf()`.

Suggested shape:

```python
hostname = parsed.hostname
scheme = parsed.scheme.lower()
default_port = 443 if scheme == "https" else 80

if ":" in hostname:
    authority_host = f"[{hostname}]"
else:
    authority_host = hostname

host_header = authority_host if port == default_port else f"{authority_host}:{port}"

return SSRFSafeRequest(
    original_url=url,
    resolved_ip=selected_ip,
    host_header=host_header,
    port=port,
    path=path,
    scheme=scheme,
    sni_hostname=hostname,
)
```

If changing the dataclass is too invasive, `sni_hostname` can stay as a computed property that returns the bare hostname, but `host_header` still needs to preserve explicit non-default ports and IPv6 bracket formatting.

Add tests for:

- `https://example.com:8443/...` -> `host_header == "example.com:8443"`
- `http://example.com:8080/...` -> `host_header == "example.com:8080"`
- default-port URLs still omit the port in `Host`
- IPv6 literals keep bracketed authority formatting in `Host`

## Impact

Legitimate SSRF-safe requests to services on custom ports can be misrouted, rejected with 400, or served by the wrong virtual host because the authority header no longer matches the original URL. This breaks integration behavior in the exact security path `web.py` is meant to protect, especially for redirects and web scraping against non-standard ports.
