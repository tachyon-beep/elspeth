## Summary

`AzureAuthConfig` incorrectly accepts an invalid mixed auth config when `connection_string` is set alongside `tenant_id`/`client_id`/`client_secret` but missing `account_url`, violating the "exactly one method" contract and silently selecting connection-string auth.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 -- config validation gap, not runtime correctness or audit integrity issue

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py`
- Line(s): `127-130` (partial SP detection), `99-112` (method counting gate)
- Function/Method: `validate_auth_method`

## Evidence

`validate_auth_method` detects partial Service Principal config using only three fields and ignores `account_url` in the partial-count gate:

```python
sp_fields = [self.tenant_id, self.client_id, self.client_secret]
sp_field_count = sum(1 for f in sp_fields if f is not None)
if 0 < sp_field_count < 3:
    ...
```

Because `account_url` is excluded from `sp_field_count`, this invalid config passes:

- `connection_string` set
- `tenant_id` set
- `client_id` set
- `client_secret` set
- `account_url` missing

Flow in current code:
- `has_conn_string=True`
- `has_service_principal=False` (missing `account_url`)
- `active_count=1` so no "multiple methods" error (`/home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py:99-112`)
- `sp_field_count=3` so partial-SP check is skipped (`/home/john/elspeth-rapid/src/elspeth/plugins/azure/auth.py:127-130`)
- Config is accepted and runtime uses connection string path.

Integration impact is real because both Azure plugins delegate auth validation directly to this class:
- `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_source.py:184-192`
- `/home/john/elspeth-rapid/src/elspeth/plugins/azure/blob_sink.py:165-173`

Test gap confirms this case is not covered:
- Existing test only checks `connection_string + tenant_id` partial case: `/home/john/elspeth-rapid/tests/unit/plugins/transforms/azure/test_auth.py:364-372`
- No test for `connection_string + tenant_id + client_id + client_secret` with missing `account_url`.

## Root Cause Hypothesis

Partial Service Principal validation logic is incomplete: it counts only three SP credential fields and omits `account_url`, so one invalid mixed-mode configuration bypasses both mutual-exclusivity and partial-field checks.

## Suggested Fix

In `validate_auth_method`, treat Service Principal as a 4-field method for partial detection, and use the same non-whitespace semantics consistently:

```python
sp_values = {
    "tenant_id": self.tenant_id,
    "client_id": self.client_id,
    "client_secret": self.client_secret,
    "account_url": self.account_url,
}
sp_present = {k: self._is_set(v) for k, v in sp_values.items()}

if any(sp_present.values()) and not all(sp_present.values()):
    missing = [k for k, present in sp_present.items() if not present]
    raise ValueError(f"Service Principal auth requires all fields. Missing: {', '.join(missing)}")
```

Also add regression tests for this exact invalid combo in:
- `/home/john/elspeth-rapid/tests/unit/plugins/transforms/azure/test_auth.py`
- optionally plugin-level coverage in `test_blob_source.py` and `test_blob_sink.py`.

## Impact

- Misconfigured credentials are silently accepted instead of failing fast.
- Runtime may use an unintended auth path (`connection_string`) despite partial Service Principal fields present.
- Violates plugin auth contract ("exactly one mutually exclusive method").
- Increases risk of security/configuration drift and harder incident diagnosis because config mistakes are masked instead of surfaced.
