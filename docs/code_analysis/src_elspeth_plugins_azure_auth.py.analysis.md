# Analysis: src/elspeth/plugins/azure/auth.py

**Lines:** 229
**Role:** Azure authentication configuration and client factory -- validates mutually exclusive auth methods (connection string, SAS token, managed identity, service principal) and creates `BlobServiceClient` instances. This is the credential boundary for all Azure Blob operations. A vulnerability here exposes the entire Azure storage infrastructure.
**Key dependencies:** Imports `pydantic.BaseModel`, `pydantic.model_validator`. Uses `azure.storage.blob.BlobServiceClient` and `azure.identity.DefaultAzureCredential`/`ClientSecretCredential` (lazy imports at runtime). Imported by `blob_source.py`, `blob_sink.py`, and `test_auth.py`.
**Analysis depth:** FULL

## Summary
This file is well-designed with a clear separation of concerns. The auth validation is thorough with good error messages. The main concern is that credentials (connection strings, SAS tokens, client secrets) are stored as plain text in the Pydantic model's attributes, which means they may appear in `repr()`, `str()`, error messages, logging output, or Pydantic validation error tracebacks. There is also a subtle validation gap where SAS token + managed identity could be ambiguous. The file is one of the strongest in the Azure plugin set.

## Critical Findings

### [57-69] Credentials stored as plain strings -- exposed via repr/str/logging
**What:** `connection_string`, `sas_token`, and `client_secret` are stored as plain `str | None` fields in the Pydantic model. Pydantic models expose all fields via `__repr__()`, `model_dump()`, and error messages on validation failure.
**Why it matters:** If this object is ever logged (e.g., `logger.debug("Auth config: %s", auth_config)`), included in an exception message, serialized for debugging, or printed by a developer, the raw credentials will be exposed. For an emergency dispatch system with HMAC fingerprinting requirements for secrets, having raw credential values freely available in a Pydantic model violates the security posture. Connection strings contain the storage account key. SAS tokens provide direct access to resources. Client secrets enable service principal authentication.
**Evidence:**
```python
connection_string: str | None = None
sas_token: str | None = None
client_secret: str | None = None
```
Pydantic provides `SecretStr` type specifically for this purpose -- it redacts the value in `repr()` and `str()` while still allowing access via `.get_secret_value()`. Using `SecretStr` would prevent accidental exposure in logs and error messages while preserving runtime functionality.

### [85-97] Validation logic counts "complete" methods but misses edge cases
**What:** The validator defines four boolean flags (`has_conn_string`, `has_sas_token`, `has_managed_identity`, `has_service_principal`) based on whether all required fields for each method are present and non-empty. Then it checks `active_count == 0` and `active_count > 1`.
**Why it matters:** There is a subtle gap: a user could provide `sas_token` (no account_url) AND `use_managed_identity=True` (no account_url). Both methods would be incomplete (each requires account_url), so `active_count` would be 0, and the error message would say "No authentication method configured" rather than the more helpful "Multiple incomplete methods configured -- provide account_url for either SAS token or managed identity." The additional validation on lines 121-139 catches some partial cases, but only when `active_count` was exactly 0 -- and the partial-SP check on line 129 has the complex condition `not has_conn_string and not has_sas_token and not has_managed_identity` which is fragile.
**Evidence:**
```python
has_sas_token = (
    self.sas_token is not None and bool(self.sas_token.strip())
    and self.account_url is not None and bool(self.account_url.strip())
)
has_managed_identity = (
    self.use_managed_identity
    and self.account_url is not None and bool(self.account_url.strip())
)
```
If both `sas_token` and `use_managed_identity` are set but `account_url` is missing, both `has_sas_token` and `has_managed_identity` are `False`, and the user gets the generic "no auth method" error instead of a specific diagnosis.

## Warnings

### [121-139] Partial-config validation has dead code paths
**What:** The partial configuration checks on lines 121-139 are intended to provide helpful error messages when a user partially configures an auth method. However, the check on line 121 (`if self.sas_token and not self.account_url`) can only trigger if `active_count == 0` AND no other method was detected. But if `self.sas_token` is set (non-None, non-empty) and `self.account_url` is None, then `has_sas_token` is already False. The `active_count == 0` check on line 102 would have already raised, so line 121 is reached only if `active_count` was exactly 0. The issue is: if `active_count > 0`, these partial checks are never reached, so a user with `connection_string + sas_token (no account_url)` gets "Multiple authentication methods" even though only connection_string is complete.
**Why it matters:** The error messages for partial configurations are less helpful than intended. The validation does prevent invalid configs from passing, but the user experience for common misconfiguration scenarios could be better.
**Evidence:**
```python
if active_count > 1:
    raise ValueError("Multiple authentication methods configured...")
    # RETURNS HERE - partial checks on 121-139 never reached

# These lines are only reached when active_count == 0:
if self.sas_token and not self.account_url:
    raise ValueError("SAS token auth requires account_url...")
```

### [143-205] No credential refresh or client caching strategy
**What:** `create_blob_service_client()` creates a new `BlobServiceClient` every time it is called. For managed identity and service principal, this creates a new credential object every time.
**Why it matters:** `DefaultAzureCredential` and `ClientSecretCredential` have internal token caches and refresh logic. Creating a new credential instance on every call discards the cached token and forces a new authentication request to Azure AD. In high-throughput scenarios, this could cause token acquisition rate limiting. The callers (blob_source, blob_sink) do cache the client via `_blob_client` / `_container_client`, so this is not currently triggered on every operation. But if `close()` is called and the source/sink is reused, a new credential is created.
**Evidence:**
```python
def create_blob_service_client(self) -> BlobServiceClient:
    # ... creates new credential on every call ...
    credential = DefaultAzureCredential()  # New instance, no shared cache
    return BlobServiceClient(account_url, credential=credential)
```

### [162-171] SAS token URL construction does not validate URL format
**What:** The SAS URL is constructed by string concatenation: `sas_url = f"{account_url.rstrip('/')}{sas}"`. This assumes `account_url` is a valid URL and the SAS token is a valid query string.
**Why it matters:** A malformed `account_url` (e.g., missing scheme, containing query parameters already) could produce an invalid URL that fails at the Azure SDK level with an unhelpful error. The `account_url` field has no format validation beyond "not empty, not whitespace."
**Evidence:**
```python
sas = sas_token if sas_token.startswith("?") else f"?{sas_token}"
sas_url = f"{account_url.rstrip('/')}{sas}"
return BlobServiceClient(sas_url)
```
If `account_url` already contains query parameters (e.g., `https://account.blob.core.windows.net?comp=properties`), the resulting URL would have malformed query string.

## Observations

### [54] Extra fields correctly forbidden
**What:** `model_config = {"extra": "forbid"}` prevents unrecognized fields from being silently accepted. This is correct for a configuration model where typos should be caught.
**Why it matters:** Good practice -- catches config typos like `conection_string` or `managed_identiy` at validation time rather than runtime.

### [215-229] auth_method property uses _is_set() consistently
**What:** The `auth_method` property uses the same `_is_set()` helper as the validator, ensuring runtime behavior matches validation semantics. This was a P2-2026-01-31 regression fix.
**Why it matters:** Good -- eliminates the whitespace-mismatch bug class documented in the test suite (`TestAzureAuthConfigWhitespaceConsistency`).

### [207-213] _is_set() helper is clean
**What:** Small utility method that encapsulates the "non-None and non-whitespace" check used throughout the class.
**Why it matters:** Good extraction -- prevents the `.strip()` logic from being duplicated across validator and runtime methods.

### No audit trail integration for credential resolution
**What:** The auth module creates clients but does not record which auth method was used in the Landscape audit trail. The `SecretResolution` table (referenced in CLAUDE.md) is designed for this, but `AzureAuthConfig` does not interact with it.
**Why it matters:** The audit trail cannot answer "which credential was used for this run's blob access." The `auth_method` property exists and could be recorded, but no caller currently does so. For compliance, knowing whether a run used a connection string vs. managed identity is important (different security postures).

### Shared between source and sink -- good factoring
**What:** The auth logic is correctly extracted into a shared module used by both `blob_source.py` and `blob_sink.py`, avoiding duplication of credential validation and client creation.
**Why it matters:** Good -- changes to auth logic only need to be made once.

## Verdict
**Status:** NEEDS_ATTENTION
**Recommended action:** Replace `str | None` with `SecretStr | None` for `connection_string`, `sas_token`, and `client_secret` fields to prevent credential exposure in logs, repr, and error messages. Add `account_url` format validation (at minimum, require `https://` prefix). Consider recording the auth method in the audit trail via the existing `SecretResolution` mechanism. The partial-config error messages are a lower priority improvement.
**Confidence:** HIGH -- The credential exposure risk is a well-understood pattern with a well-known Pydantic solution (`SecretStr`). The validation gap was verified by constructing test cases mentally. The SAS URL construction concern is based on standard URL parsing rules.
