## Summary

Initial Dataverse requests are sent without the promised IP-pinning SSRF validation; only `@odata.nextLink` hops get the second SSRF layer, so the first `GET`/`PATCH` can still reach a rebinding or misresolved internal IP.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py
- Line(s): 225-238, 277-311, 598-625
- Function/Method: `__init__`, `_validate_url_ssrf`, `get_page` / `upsert`

## Evidence

`DataverseClient` claims it provides “SSRF validation on all URLs (domain allowlist + IP-pinning)”:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:198-201
- SSRF validation on all URLs (domain allowlist + IP-pinning)
```

But the constructor only checks the hostname against the allowlist:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:225-238
parsed = urllib.parse.urlparse(self._environment_url)
hostname = parsed.hostname
...
if not _validate_domain_allowlist(hostname, self._additional_domains):
    raise DataverseClientError(...)
```

The actual IP-pinning logic exists in `_validate_url_ssrf()`:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:303-311
try:
    validate_url_for_ssrf(url)
except Exception as exc:
    raise DataverseClientError(...)
```

But `get_page()` and `upsert()` call `_execute_request()` directly and never invoke `_validate_url_ssrf()` first:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:598-625
def get_page(self, url: str) -> DataversePageResponse:
    return self._execute_request("GET", url)

def upsert(self, url: str, body: dict[str, Any]) -> DataversePageResponse:
    return self._execute_request("PATCH", url, json_body=body)
```

The only place `_validate_url_ssrf()` is used is when following `page.next_link`:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:669-671
self._validate_url_ssrf(page.next_link)
url = page.next_link
```

The tests also only cover SSRF checks on `nextLink`, not on the initial request URL:

```python
# tests/unit/plugins/infrastructure/clients/test_dataverse_client.py:575-630
class TestPaginateOdata:
    """OData nextLink pagination with SSRF validation."""
```

So page 1 and all sink upserts currently bypass the second SSRF layer.

## Root Cause Hypothesis

The SSRF hardening was implemented around pagination handoff (`@odata.nextLink`) and redirects, but not applied uniformly at the actual request entry points. The constructor’s hostname allowlist was treated as sufficient for the base URL, even though the code and docs require IP-pinning too.

## Suggested Fix

Validate every outbound URL immediately before request execution, not just pagination hops. The simplest fix is to call `_validate_url_ssrf(url)` at the start of `_execute_request()` or in both `get_page()` and `upsert()`.

Example shape:

```python
def _execute_request(...):
    self._validate_url_ssrf(url)
    self._acquire_rate_limit()
    ...
```

Add tests proving `get_page()` and `upsert()` reject URLs when `validate_url_for_ssrf()` fails.

## Impact

The Dataverse client can make its first external call to an IP that passes hostname-pattern checks but fails the required IP-pinning safety check. That weakens the repo’s SSRF guarantee for both reads and writes, especially for deployment-specific `additional_domains` and any DNS rebinding or resolver-compromise scenario.
---
## Summary

FetchXML pagination silently truncates result sets when Dataverse says `morerecords=True` but omits the paging cookie; the client breaks the loop instead of raising a protocol error.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py
- Line(s): 717-729
- Function/Method: `paginate_fetchxml`

## Evidence

The code correctly treats missing `@Microsoft.Dynamics.CRM.morerecords` as a protocol violation:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:717-727
if page.more_records is None:
    raise DataverseClientError(
        "FetchXML response missing '@Microsoft.Dynamics.CRM.morerecords' field ...",
        retryable=False,
        error_category="protocol_violation",
    )
```

But immediately after that it collapses two different cases into `break`:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:728-729
if not page.more_records or page.paging_cookie is None:
    break
```

That means this anomalous response:

- `page.more_records is True`
- `page.paging_cookie is None`

is treated as normal end-of-pagination, even though the server explicitly said more pages exist.

This is inconsistent with the surrounding comments and with the client’s general “absence is anomaly, don’t infer” stance. The current tests cover missing `morerecords`:

```python
# tests/unit/plugins/infrastructure/clients/test_dataverse_client.py:796-814
def test_missing_morerecords_crashes_fetchxml_pagination(...)
```

but there is no corresponding test for `morerecords=True` with a missing paging cookie.

## Root Cause Hypothesis

The termination condition was written as a convenience shortcut for “done if no more records or no cookie,” but a missing cookie when `morerecords=True` is not a clean terminal state; it is contradictory external data that should be surfaced, not silently interpreted.

## Suggested Fix

Split the conditions:

```python
if not page.more_records:
    break
if page.paging_cookie is None:
    raise DataverseClientError(
        "FetchXML response set '@Microsoft.Dynamics.CRM.morerecords' to true "
        "but omitted '@Microsoft.Dynamics.CRM.fetchxmlpagingcookie' ...",
        retryable=False,
        error_category="protocol_violation",
    )
```

Add a unit test for that exact anomaly.

## Impact

This can silently drop pages from FetchXML queries. The source plugin will record a clean-looking successful load and downstream rows simply never appear, violating the “no silent data loss” and complete-lineage expectations in `CLAUDE.md`.
---
## Summary

When a page fetch fails after pagination has started, the audit trail records the previous page’s URL instead of the URL that actually failed, because `DataverseClientError` carries no request metadata.

## Severity

- Severity: major
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py
- Line(s): 74-99, 425-465
- Function/Method: `DataverseClientError`, `_execute_request`

## Evidence

`DataverseClientError` only stores message, retryability, status code, latency, and category:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:86-99
def __init__(..., retryable: bool, status_code: int | None = None,
             latency_ms: float | None = None, error_category: str = "protocol_error"):
    ...
    self.retryable = retryable
    self.status_code = status_code
    self.latency_ms = latency_ms
    self.error_category = error_category
```

Every failure path in `_execute_request()` raises that exception without the attempted URL or fingerprinted request headers:

```python
# src/elspeth/plugins/infrastructure/clients/dataverse.py:425-465
raise DataverseClientError(...)
...
raise self._classify_error(response.status_code, resp_headers, latency_ms)
```

Downstream, the source plugin has to guess. Its own comment says it only has the “closest available context”:

```python
# src/elspeth/plugins/sources/dataverse.py:687-695
# For page N errors it's the last successfully-fetched page's URL
# (the closest available context for which page the client was
# attempting when it failed).
self._record_page_call(ctx, url=last_fetched_url, error=e, ...)
```

`last_fetched_url` is only updated after a successful page is yielded:

```python
# src/elspeth/plugins/sources/dataverse.py:595-597
for page in page_iterator:
    pages_fetched += 1
    last_fetched_url = page.request_url
```

So if page 2’s `nextLink` fetch fails, the recorded error URL is page 1’s URL, not the failing `nextLink`. That is an audit accuracy bug rooted in the client’s error object.

## Root Cause Hypothesis

The client was designed as a “pure protocol client” and only the success DTO (`DataversePageResponse`) was given request metadata. Error propagation stopped at a minimal exception shape, leaving the caller unable to record the actual failing request.

## Suggested Fix

Attach request metadata to `DataverseClientError`, at minimum:

- attempted `request_url`
- fingerprinted `request_headers` when available

Then populate those fields in every `_execute_request()` failure path, including classified HTTP errors. The source/sink plugins can then record the true failed URL instead of a stale fallback.

## Impact

Failed Dataverse calls can be misattributed in the Landscape audit trail, especially on paginated reads and auth-retry scenarios. That weakens traceability: an auditor investigating a failed fetch sees the wrong URL, which is exactly the kind of “I don’t know what happened” gap ELSPETH is supposed to prevent.
