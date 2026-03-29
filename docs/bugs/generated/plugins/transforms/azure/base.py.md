## Summary

Azure safety transforms accept any non-empty `endpoint`, so a misconfigured `http://` or non-Azure URL will be used for live API calls with the subscription key header attached.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py`
- Line(s): 57-70
- Function/Method: `BaseAzureSafetyConfig._reject_empty_credentials`

## Evidence

`BaseAzureSafetyConfig` only checks that `endpoint` and `api_key` are non-empty:

```python
endpoint: str = Field(..., description="Azure Content Safety endpoint URL")
api_key: str = Field(..., description="Azure Content Safety API key")

@field_validator("endpoint", "api_key")
@classmethod
def _reject_empty_credentials(cls, v: str, info: Any) -> str:
    if not v.strip():
        raise ValueError(f"{info.field_name} must not be empty")
    return v
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py:57-70`

That unchecked `endpoint` is then concatenated directly into the request URL, and the API key is sent as a header on every request:

```python
url = f"{self._endpoint}/contentsafety/text:analyze?api-version={self.API_VERSION}"
response = http_client.post(url, json={"text": text})
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/azure/content_safety.py:166-169`

```python
headers={
    "Ocp-Apim-Subscription-Key": self._api_key,
    "Content-Type": "application/json",
}
```

Source: `/home/john/elspeth/src/elspeth/plugins/transforms/azure/base.py:342-350`

So `endpoint="http://example.com"` or `endpoint="http://169.254.169.254"` is currently accepted and used as-is. The transform will still send row text and the Azure subscription key to that host.

Comparable code elsewhere in the repo already treats external endpoints as security boundaries and validates them:

```python
parsed = urllib.parse.urlparse(v)
if parsed.scheme != "https":
    raise ValueError(f"endpoint must use HTTPS scheme, got {parsed.scheme!r}")
if not parsed.hostname:
    raise ValueError(f"endpoint must have a hostname, got {v!r}")
```

Source: `/home/john/elspeth/src/elspeth/plugins/infrastructure/clients/retrieval/azure_search.py:44-52`

```python
if parsed.scheme != "https":
    raise ValueError(
        f"environment_url must use HTTPS scheme, got {parsed.scheme!r}. "
        f"Bearer tokens are sent in Authorization headers — HTTP would expose them in transit."
    )
```

Source: `/home/john/elspeth/src/elspeth/plugins/sources/dataverse.py:122-132`

The Azure safety tests only cover presence/emptiness of `endpoint`; there is no rejection test for insecure or malformed URLs.

Source: `/home/john/elspeth/tests/unit/plugins/transforms/azure/test_content_safety.py:46-88`

## Root Cause Hypothesis

The shared Azure base config collapsed `endpoint` and `api_key` into a single “non-empty string” validator, so the transport-security requirements for an external call boundary were never enforced. The code assumes the operator will supply a correct Azure HTTPS base URL, but the config model does not actually encode that contract.

## Suggested Fix

Replace the combined validator with endpoint-specific validation that at minimum:

- Requires `https`
- Requires a hostname
- Rejects embedded credentials/userinfo
- Optionally rejects query strings/fragments and non-root paths if the plugin expects only an Azure resource base URL

Example shape:

```python
from urllib.parse import urlparse

@field_validator("endpoint")
@classmethod
def validate_endpoint(cls, v: str) -> str:
    parsed = urlparse(v)
    if parsed.scheme != "https":
        raise ValueError(f"endpoint must use HTTPS scheme, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError(f"endpoint must have a hostname, got {v!r}")
    if parsed.username or parsed.password:
        raise ValueError("endpoint must not contain embedded credentials")
    return v

@field_validator("api_key")
@classmethod
def validate_api_key(cls, v: str) -> str:
    if not v.strip():
        raise ValueError("api_key must not be empty")
    return v
```

Add unit tests in both Azure transform test files rejecting `http://...` and malformed endpoints.

## Impact

This is a security and boundary-validation bug in a shared base class used by both Azure safety transforms. A bad config can cause ELSPETH to send pipeline text and the Azure subscription key to an unintended host, including over plain HTTP. The audit trail would record that the call happened, but the data and secret exposure has already occurred, so the system’s external-call safety guarantees are broken before auditability can help.
