## Summary

Azure Search retrieval never authenticates actual search requests when `use_managed_identity=True`, so every managed-identity configuration passes validation and readiness probing but fails at first real query.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py`
- Line(s): 159-176, 317-324
- Function/Method: `_execute_search`, `check_readiness`

## Evidence

`AzureSearchProviderConfig` explicitly allows managed identity as an alternative to `api_key`:

```python
# src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py:80-86
if not self.api_key and not self.use_managed_identity:
    raise ValueError("Specify either api_key or use_managed_identity=true")
if self.api_key and self.use_managed_identity:
    raise ValueError("Specify only one of api_key or use_managed_identity")
```

But the real search path only sets the `api-key` header and has no managed-identity branch at all:

```python
# src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py:159-176
headers = {"Content-Type": "application/json"}
if self._config.api_key:
    headers["api-key"] = self._config.api_key

body = self._build_request_body(query, top_k)
http_client = AuditedHTTPClient(..., headers=headers)
response = http_client.post(self._search_url, json=body)
```

By contrast, the readiness probe does implement managed identity and acquires a Bearer token:

```python
# src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py:317-324
if self._config.api_key:
    headers["api-key"] = self._config.api_key
elif self._config.use_managed_identity:
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://search.azure.com/.default")
    headers["Authorization"] = f"Bearer {token.token}"
```

The tests reinforce the mismatch: there is a readiness test for managed identity, but no search-path test for it.

```python
# tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py:472-506
def test_managed_identity_sends_bearer_token(self) -> None:
    ...
    result = provider.check_readiness()
    ...
    assert call_headers["Authorization"] == "Bearer managed-identity-token-123"
```

What the code does now:
- Accepts `use_managed_identity=True`
- Successfully probes readiness with a Bearer token
- Sends unauthenticated search requests during `search()`

What it should do:
- Authenticate the actual search request with the same managed-identity flow used by readiness.

## Root Cause Hypothesis

Managed-identity support was added only to the startup probe and not to the row-level search path. The config contract implies both auth modes are valid for the provider, but `_execute_search()` still only implements the API-key path.

## Suggested Fix

Add the same managed-identity branch to `_execute_search()` before constructing `AuditedHTTPClient`, for example by populating `Authorization: Bearer ...` when `use_managed_identity=True`.

Also add a unit test that exercises `search()` with managed identity and verifies the outgoing headers on the audited HTTP client.

## Impact

Any RAG pipeline configured for Azure Search managed identity is nonfunctional at runtime. Startup can report the index as ready, but the first retrieval call fails with 401/403, breaking retrieval and quarantining or failing rows despite valid configuration.
---
## Summary

Transient HTTP failures from Azure Search are not converted into `RetrievalError`, so retryable transport errors escape as raw `httpx` exceptions and bypass the transform’s retry/quarantine handling.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py`
- Line(s): 175-199
- Function/Method: `_execute_search`

## Evidence

The provider wraps the search call in `_execute_search()`, but its exception mapping only catches Python builtins:

```python
# src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py:175-199
try:
    response = http_client.post(self._search_url, json=body)
    ...
except RetrievalError:
    raise
except (ConnectionError, TimeoutError, OSError) as exc:
    raise RetrievalError(f"Search request failed: {exc}", retryable=True) from exc
```

However, the audited HTTP client documents and implements `httpx` exceptions, not builtin `ConnectionError`/`TimeoutError`:

```python
# src/elspeth/plugins/infrastructure/clients/http.py:426-427
Raises:
    httpx.HTTPError: For network/HTTP errors
```

```python
# src/elspeth/plugins/infrastructure/clients/http.py:382-402
except Exception as e:
    ...
    raise
```

So an `httpx.ConnectError`, `httpx.ReadTimeout`, or similar from `AuditedHTTPClient.post()` will bubble out unchanged. The RAG transform only handles `RetrievalError`:

```python
# src/elspeth/plugins/transforms/rag/transform.py:199-211
except RetrievalError as e:
    if e.retryable:
        raise  # Engine retry handles transient failures
    ...
    return TransformResult.error(error_reason, retryable=False)
```

What the code does now:
- Lets `httpx` transport errors escape as raw exceptions
- Skips the provider’s retryability classification
- Bypasses the transform’s intended `RetrievalError` path

What it should do:
- Catch `httpx.HTTPError` subclasses from the external call boundary
- Re-raise them as `RetrievalError(retryable=True)` or `False` as appropriate

There is no unit test covering raw `httpx` transport failures in `tests/unit/plugins/infrastructure/clients/retrieval/test_azure_search.py`; existing tests only inject `RetrievalError` directly.

## Root Cause Hypothesis

`_execute_search()` was written against generic builtin exception types, but the actual HTTP abstraction used here is `httpx` via `AuditedHTTPClient`. The provider’s transport-boundary error mapping no longer matches the client it calls.

## Suggested Fix

Catch `httpx.HTTPError` (and, if desired, narrower subclasses like `httpx.TimeoutException` / `httpx.NetworkError`) in `_execute_search()` and wrap them in `RetrievalError(..., retryable=True)`.

A focused test should patch `AuditedHTTPClient.post()` to raise `httpx.ConnectError` and assert that `provider.search(...)` raises `RetrievalError` with `retryable=True`.

## Impact

Transient Azure Search outages stop behaving like retryable provider failures. Instead of entering the engine’s retry flow or producing a controlled retrieval error, the transform can crash with raw `httpx` exceptions, turning recoverable network blips into pipeline failures.
