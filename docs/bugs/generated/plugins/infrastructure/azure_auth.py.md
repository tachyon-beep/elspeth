## Summary

`use_managed_identity=true` does not guarantee managed-identity authentication; `AzureAuthConfig.create_blob_service_client()` uses `DefaultAzureCredential()`, which can silently authenticate with a different credential source than the configured auth mode.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/azure_auth.py
- Line(s): 176-187
- Function/Method: `create_blob_service_client`

## Evidence

`AzureAuthConfig` advertises a distinct “Managed Identity” mode:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/azure_auth.py:30-31
3. use_managed_identity + account_url - Azure Managed Identity
```

But the implementation for that branch constructs `DefaultAzureCredential()` instead of `ManagedIdentityCredential()`:

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/azure_auth.py:176-187
elif self.use_managed_identity:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as e:
        raise ImportError(...) from e

    account_url = cast(str, self.account_url)
    credential = DefaultAzureCredential()
    return BlobServiceClient(account_url, credential=credential)
```

`DefaultAzureCredential` is a credential chain, not a managed-identity-only credential. So when `use_managed_identity=True`, this code may authenticate via environment credentials, Azure CLI login, shared token cache, etc., depending on the host environment.

The rest of the repo treats “managed identity” as a concrete credential type, not the default chain:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/dataverse.py:252-266
from azure.identity import ClientSecretCredential, ManagedIdentityCredential
...
else:
    credential = ManagedIdentityCredential()
```

```python
# /home/john/elspeth/src/elspeth/plugins/sinks/dataverse.py:203-216
from azure.identity import ClientSecretCredential, ManagedIdentityCredential
...
else:
    credential = ManagedIdentityCredential()
```

```python
# /home/john/elspeth/src/elspeth/plugins/infrastructure/clients/dataverse.py:752-764
from azure.identity import ClientSecretCredential, ManagedIdentityCredential
...
else:
    self._credential = ManagedIdentityCredential()
```

The current tests lock in the wrong behavior by explicitly asserting `DefaultAzureCredential` for blob auth instead of managed-identity-only auth:

```python
# /home/john/elspeth/tests/unit/plugins/transforms/azure/test_auth.py:301-320
def test_managed_identity_creates_client_with_credential(self) -> None:
    ...
    patch.dict("sys.modules", {"azure.identity": MagicMock(DefaultAzureCredential=mock_default_azure_credential)})
```

```python
# /home/john/elspeth/tests/unit/plugins/transforms/azure/test_blob_source.py:943-967
def test_managed_identity_uses_default_credential(self, ctx: PluginContext) -> None:
    ...
    patch("azure.identity.DefaultAzureCredential")
```

```python
# /home/john/elspeth/tests/unit/plugins/transforms/azure/test_blob_sink.py:999-1024
def test_managed_identity_uses_default_credential(self, ctx: PluginContext) -> None:
    ...
    patch("azure.identity.DefaultAzureCredential")
```

What the code does: “managed identity” delegates to the ambient default Azure credential chain.

What it should do: `use_managed_identity=true` should instantiate `ManagedIdentityCredential()` so the configured auth mode is the credential actually used.

## Root Cause Hypothesis

The helper conflates “managed identity” with “Azure AD auth that often works in Azure-hosted environments.” That is convenient during development, but it breaks the config contract: a caller selecting managed identity expects a managed-identity-only credential, not a chain that can fall back to unrelated identities present on the machine.

The bug persisted because the blob auth tests were written to match the implementation rather than the declared auth mode semantics.

## Suggested Fix

In `AzureAuthConfig.create_blob_service_client()`, replace `DefaultAzureCredential` with `ManagedIdentityCredential` in the `self.use_managed_identity` branch.

Conceptually:

```python
from azure.identity import ManagedIdentityCredential

account_url = cast(str, self.account_url)
credential = ManagedIdentityCredential()
return BlobServiceClient(account_url, credential=credential)
```

Update the blob auth tests to assert `ManagedIdentityCredential` instead of `DefaultAzureCredential` in:

- `/home/john/elspeth/tests/unit/plugins/transforms/azure/test_auth.py`
- `/home/john/elspeth/tests/unit/plugins/transforms/azure/test_blob_source.py`
- `/home/john/elspeth/tests/unit/plugins/transforms/azure/test_blob_sink.py`

If user-assigned managed identity support is needed later, add an explicit config field for the managed identity client ID rather than relying on the default credential chain.

## Impact

Blob source and sink runs configured with `use_managed_identity=true` can authenticate as the wrong Azure principal whenever other default Azure credentials are available on the host. That creates environment-dependent behavior: the same pipeline may succeed locally, fail in production, or access storage under an unintended identity without any config change.

This is primarily a protocol/config-contract violation, but it also weakens explainability: the pipeline audit trail records blob operations, not which Azure credential in the default chain actually authenticated. When a run uses an unexpected principal, the behavior is harder to justify from the recorded configuration because the configured auth mode says “managed identity” while the implementation actually means “whatever `DefaultAzureCredential` finds first.”
