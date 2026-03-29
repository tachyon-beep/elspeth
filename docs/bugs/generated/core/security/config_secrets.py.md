## Summary

`load_secrets_from_config()` can leak a bare `ValueError` when the fingerprint key loaded from Key Vault is empty or otherwise invalid, even though the function promises to fail with `SecretLoadError`.

## Severity

- Severity: major
- Priority: P2

## Location

- File: `src/elspeth/core/security/config_secrets.py`
- Line(s): 165-180, 184-206
- Function/Method: `load_secrets_from_config`

## Evidence

`load_secrets_from_config()` documents a single failure contract:

```python
# src/elspeth/core/security/config_secrets.py:71-73
Raises:
    SecretLoadError: If any secret cannot be loaded (fail fast)
```

But inside the per-secret loop it calls fingerprint helpers that can raise `ValueError`:

```python
# src/elspeth/core/security/config_secrets.py:165-170
if fingerprint_key is None:
    if env_var_name == _FP_KEY:
        fingerprint_key = str(secret_value).encode()
    else:
        fingerprint_key = get_fingerprint_key()
fp = secret_fingerprint(str(secret_value), key=fingerprint_key)
```

`secret_fingerprint()` explicitly raises on an empty HMAC key:

```python
# src/elspeth/contracts/security.py:91-95
if key is None:
    key = get_fingerprint_key()

if len(key) == 0:
    raise ValueError("Fingerprint key must not be empty ...")
```

The surrounding handler in `config_secrets.py` does not catch `ValueError`; it only catches Azure/loader-specific exceptions:

```python
# src/elspeth/core/security/config_secrets.py:184-206
except SecretNotFoundError as e:
    ...
except ImportError as e:
    ...
except ClientAuthenticationError as e:
    ...
except (HttpResponseError, ServiceRequestError) as e:
    ...
```

So if Key Vault returns `ELSPETH_FINGERPRINT_KEY=""`, or `get_fingerprint_key()`/`secret_fingerprint()` raises another validation `ValueError`, the raw exception escapes without vault URL, secret name, or env-var context. That is different from what the function says it does and weaker than the other error paths.

## Root Cause Hypothesis

The code treats fingerprinting as an infallible post-load step, but fingerprint key validation is part of the secret-loading boundary. Because that validation happens inside the loop and outside the caught exception set, the function’s public error contract is broken for this branch.

## Suggested Fix

Wrap fingerprint-key acquisition and fingerprint computation in a local `try/except ValueError` and re-raise `SecretLoadError` with the same actionable context used for other failures.

Example shape:

```python
try:
    if fingerprint_key is None:
        if env_var_name == _FP_KEY:
            fingerprint_key = str(secret_value).encode("utf-8")
        else:
            fingerprint_key = get_fingerprint_key()
    fp = secret_fingerprint(str(secret_value), key=fingerprint_key)
except ValueError as e:
    raise SecretLoadError(
        f"Invalid fingerprint key while loading secret '{keyvault_secret_name}' "
        f"for env var '{env_var_name}' from Key Vault ({config.vault_url})\n"
        f"Error: {e}"
    ) from e
```

It would also be reasonable to explicitly reject an empty `ELSPETH_FINGERPRINT_KEY` immediately when that secret is fetched.

## Impact

A bad fingerprint-key secret aborts startup with an undocumented raw exception instead of a structured `SecretLoadError`. Operators lose the secret name / env var / vault URL context needed to fix the configuration quickly, and callers expecting the documented exception type do not get it.
---
## Summary

`load_secrets_from_config()` measures `resolution_latency_ms` with `time.time()`, so a wall-clock adjustment can produce a negative latency and make an otherwise successful secret load fail DTO validation.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/core/security/config_secrets.py`
- Line(s): 153-180
- Function/Method: `load_secrets_from_config`

## Evidence

The function uses wall-clock time both for the audit timestamp and for latency measurement:

```python
# src/elspeth/core/security/config_secrets.py:153-156
start_time = time.time()
secret_value, _ref = loader.get_secret(keyvault_secret_name)
latency_ms = (time.time() - start_time) * 1000
```

That latency is then persisted into `SecretResolutionInput`:

```python
# src/elspeth/core/security/config_secrets.py:172-180
SecretResolutionInput(
    ...
    timestamp=start_time,
    resolution_latency_ms=latency_ms,
    ...
)
```

But the DTO enforces non-negative latency:

```python
# src/elspeth/contracts/audit.py:883-884
if self.resolution_latency_ms < 0:
    raise ValueError(...)
```

`time.time()` is not monotonic. If the system clock moves backward during the Key Vault call, `latency_ms` becomes negative and `SecretResolutionInput(...)` raises, even though the secret fetch itself succeeded.

## Root Cause Hypothesis

The code is using one clock source for two different jobs: audit timestamping and elapsed-duration measurement. Wall-clock time is correct for the former, but not safe for the latter.

## Suggested Fix

Use separate clocks:

- `time.time()` once for the audit timestamp
- `time.perf_counter()` for elapsed duration

Example:

```python
timestamp = time.time()
start_perf = time.perf_counter()
secret_value, _ref = loader.get_secret(keyvault_secret_name)
latency_ms = (time.perf_counter() - start_perf) * 1000
```

## Impact

On hosts with NTP corrections, VM clock drift, or manual clock changes, secret loading can fail intermittently during startup for no real Key Vault reason. The run never reaches secret-resolution audit recording even though the external call succeeded.
