# Analysis: src/elspeth/core/security/config_secrets.py

**Lines:** 183
**Role:** Config-based secret loading from Azure Key Vault. Loads secrets specified in pipeline configuration, injects them into environment variables before Dynaconf config resolution, and returns resolution records for deferred audit trail recording.
**Key dependencies:** Imports `os`, `time`. TYPE_CHECKING import of `SecretsConfig` from `core/config.py`. Runtime import of `KeyVaultSecretLoader` and `SecretNotFoundError` from `secret_loader.py`. Consumed by `cli.py` (both `_load_settings_with_secrets` and the `run` command), and indirectly by the orchestrator which records the returned resolutions.
**Analysis depth:** FULL

## Summary

This is a critical security module that bridges pipeline configuration with secret loading. It has one significant finding: plaintext secret values are carried in the resolution records list (as `dict[str, Any]`) through multiple layers of the call stack and are never explicitly cleared. The preflight fingerprint key check is well-intentioned but has a subtle ordering dependency. Error handling is thorough but uses string-matching for exception classification, which is fragile.

## Critical Findings

### [152] Plaintext secret values persist in resolution records through the entire pipeline startup

**What:** The resolution records returned on line 183 contain `"secret_value": secret_value` for every Key Vault secret. These dict objects are passed from `load_secrets_from_config()` to `cli.py`, then to the orchestrator's `execute()` method, then to `recorder.record_secret_resolutions()`. The plaintext values travel through at least 4 stack frames and multiple module boundaries. After `record_secret_resolutions()` computes fingerprints (recorder.py line 569), the resolution list and its plaintext values are never cleared -- they remain on the stack and in local variables until garbage collection.

**Why it matters:** This is a government emergency dispatch system. The resolution records are `list[dict[str, Any]]` -- mutable, unprotected dicts containing every Key Vault secret in plaintext. If any exception handler, logger, or debugger captures the locals at any point in this chain, all secrets are exposed. The records also persist in the orchestrator's stack frame for the entire duration of `execute()` (which runs the full pipeline).

**Evidence:**
```python
# config_secrets.py line 152 - plaintext included
"secret_value": secret_value,  # For fingerprinting, NOT for storage

# cli.py line 297 - returned to CLI
secret_resolutions = load_secrets_from_config(secrets_config)

# cli.py line 484 - passed to orchestrator
secret_resolutions=secret_resolutions,

# orchestrator/core.py line 440 - passed to recorder
recorder.record_secret_resolutions(run_id=run.run_id, resolutions=secret_resolutions, ...)

# recorder.py line 569 - finally consumed, but never cleared
fp = secret_fingerprint(rec["secret_value"], key=fingerprint_key)
# rec still contains "secret_value" after this line
```

The resolution records are never mutated to remove `secret_value` after fingerprinting. The list reference exists in `cli.py`'s `run()` scope for the entire pipeline execution duration.

## Warnings

### [84-87] Fingerprint key preflight check has an ordering dependency that could pass preflight but fail at audit time

**What:** The preflight check on line 84-87 verifies that `ELSPETH_FINGERPRINT_KEY` is either already in the environment OR is listed in the mapping. If it is in the mapping, the check passes. However, the fingerprint key is not used until much later (in `recorder.record_secret_resolutions()`, via `get_fingerprint_key()`). If the Key Vault lookup for `ELSPETH_FINGERPRINT_KEY` itself fails during the loop on line 134, the `SecretLoadError` on line 158 will fire, which is correct. But there is a subtle gap: if `ELSPETH_FINGERPRINT_KEY` is in the mapping and loads successfully (line 141 sets it in `os.environ`), but the value is empty or whitespace, the `get_fingerprint_key()` call later in the orchestrator (line 439 of core.py) will fail with ValueError because `fingerprint.py` line 48 checks `if not env_key:`.

**Why it matters:** This creates a scenario where all secrets are loaded and injected into environment variables, but the pipeline crashes during audit recording because the fingerprint key value itself is empty. The preflight check does not validate the value, only the presence of the mapping entry. The pipeline would have already made Key Vault API calls for all other secrets (potentially expensive, rate-limited operations) before failing.

**Evidence:**
```python
# Preflight passes if key is in mapping (doesn't check value)
fingerprint_key_available = (
    os.environ.get("ELSPETH_FINGERPRINT_KEY")
    or "ELSPETH_FINGERPRINT_KEY" in config.mapping  # Only checks membership
)

# Later, after all secrets loaded, orchestrator calls:
fingerprint_key = get_fingerprint_key()  # Raises ValueError if empty
```

### [119-129] Exception classification by string matching is fragile

**What:** Lines 121-122 and 168-169 classify Azure exceptions by checking if `"ClientAuthenticationError"` appears in `str(e)` or if `"credential"` appears in the lowercase string representation. This is done twice: once for loader creation (line 119-129) and once per-secret (line 166-181).

**Why it matters:** String matching on exception messages is fragile across Azure SDK versions. If the Azure SDK changes error message wording, or if a non-auth exception happens to contain the word "credential" in its message (e.g., "Failed to read credential file at /path"), it would be misclassified. More critically, `KeyVaultSecretLoader.__init__` does NOT create the Azure client (it uses lazy init via `_get_client()`), so the try/except on line 115-129 for `KeyVaultSecretLoader(vault_url=config.vault_url)` will never catch Azure auth errors -- the constructor only stores the URL. The auth error would occur on the first `loader.get_secret()` call inside the loop, not during construction.

**Evidence:**
```python
# Line 116 - constructor does NOT create Azure client
loader = KeyVaultSecretLoader(vault_url=config.vault_url)
# KeyVaultSecretLoader.__init__ only stores vault_url and sets _client = None

# Line 119-129 catches Exception on construction, but auth errors can't happen here
except Exception as e:
    error_str = str(e)
    if "ClientAuthenticationError" in error_str or "credential" in error_str.lower():
        # This branch is unreachable for auth errors
```

The auth error handling on line 119-129 is dead code for its stated purpose. Auth errors will be caught by the per-secret handler on line 166-181, which does work correctly.

### [141] os.environ mutation is not thread-safe

**What:** Line 141 sets `os.environ[env_var_name] = secret_value` in a loop. `os.environ` modification is not atomic and not thread-safe in CPython. If another thread reads `os.environ` between iterations, it could see a partially-loaded set of secrets.

**Why it matters:** If `load_secrets_from_config` is called during application startup before worker threads are spawned, this is fine. The current call sites (cli.py) appear to call this before any threading. However, the function itself has no documentation about thread-safety requirements, and a future caller could invoke it in a threaded context.

## Observations

### [114] Assert statement for vault_url

**What:** Line 114 uses `assert config.vault_url is not None` which would be stripped in `-O` (optimized) mode. The comment says Pydantic guarantees this, but the Pydantic model shows `vault_url: str | None = Field(default=None)` with no validator enforcing it when `source == "keyvault"`.

**Why it matters:** If someone constructs `SecretsConfig(source="keyvault", vault_url=None, mapping={...})` manually (e.g., in tests), the assert would pass in normal mode but the subsequent code would pass `None` to `KeyVaultSecretLoader(vault_url=None)`. Worth checking if the Pydantic validator enforces this constraint. If not, this is a latent bug.

### [135] time.time() vs time.perf_counter() for latency

**What:** Line 135 uses `time.time()` for both the timestamp record and the latency calculation. `time.time()` is subject to system clock adjustments (NTP jumps) and has lower resolution than `time.perf_counter()` on some platforms. The latency should use `perf_counter()` while the timestamp should use `time.time()`.

**Why it matters:** Low severity. On systems with NTP adjustments, the latency_ms could be negative or anomalously large. This would produce misleading audit records but would not affect correctness.

### [104-110] Duplicate ImportError handling

**What:** The `ImportError` for Azure packages is caught at line 109 (import of `KeyVaultSecretLoader`), at line 117 (construction), and at line 163 (per-secret). The message is identical in all three. The line 117 catch is particularly redundant since `KeyVaultSecretLoader.__init__` does not import anything.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) The plaintext secret values in resolution records should be cleared after fingerprinting -- either by mutating the records to delete the `secret_value` key in `record_secret_resolutions()`, or by computing fingerprints in `load_secrets_from_config()` itself and returning fingerprints instead of values. (2) Remove the dead auth error handling on lines 119-129 (auth errors cannot occur during `KeyVaultSecretLoader` construction). (3) Validate that the Pydantic model enforces `vault_url is not None` when `source == "keyvault"`, or replace the assert with a proper check.
**Confidence:** HIGH -- All code paths were traced through the full call chain from CLI to recorder.
