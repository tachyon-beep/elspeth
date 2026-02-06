# Analysis: src/elspeth/core/security/secret_loader.py

**Lines:** 301
**Role:** General-purpose secret loading abstraction. Provides a unified interface for loading secrets from environment variables or Azure Key Vault, with caching, composite fallback chains, and SecretRef for audit trail integration.
**Key dependencies:** Imports `os`, standard library only. Conditionally imports `azure.keyvault.secrets.SecretClient` and `azure.identity.DefaultAzureCredential`. Consumed by `config_secrets.py`, `cli.py`, and indirectly by the orchestrator and landscape recorder.
**Analysis depth:** FULL

## Summary

This file is well-structured with clean separation of concerns across four loader classes (EnvSecretLoader, KeyVaultSecretLoader, CachedSecretLoader, CompositeSecretLoader). The Protocol-based design is solid. There are no critical findings, but there are two security-relevant warnings around secret value retention in memory and a race condition in the composite loader's fallback behavior when non-SecretNotFoundError exceptions occur at Azure boundaries.

## Warnings

### [157] KeyVaultSecretLoader caches plaintext secret values indefinitely

**What:** The `_cache: dict[str, str]` on line 157 stores plaintext secret values in memory with no eviction policy. The `CachedSecretLoader` (line 240) similarly holds `dict[str, tuple[str, SecretRef]]` with plaintext values. Neither cache has TTL, size limits, or any mechanism to clear values after they are no longer needed.

**Why it matters:** In a long-running pipeline process, secrets remain in plaintext in Python heap memory indefinitely. If the process is memory-dumped (core dump, debugging tools, crash reporter), all cached secrets are exposed. For a government emergency dispatch system, this extends the window of exposure unnecessarily. The `clear_cache()` method exists (line 221) but is never called by any consumer in the codebase.

**Evidence:**
```python
self._cache: dict[str, str] = {}  # line 157 - plaintext values, no TTL
# ...
self._cache[name] = value  # line 203 - cached forever
```

The `CachedSecretLoader` wrapper (line 240) compounds this:
```python
self._cache: dict[str, tuple[str, SecretRef]] = {}  # line 240 - also plaintext
```

### [191] AzureResourceNotFoundError fallback assignment is fragile

**What:** When `azure.core.exceptions` is not importable, line 191 sets `AzureResourceNotFoundError = Exception`. This means the `except AzureResourceNotFoundError` block on line 214 would catch ALL exceptions (since everything inherits from Exception), converting operational failures (auth errors, network timeouts, rate limits) into `SecretNotFoundError` and triggering silent fallback to the next backend.

**Why it matters:** If the Azure SDK is partially installed (keyvault package present but azure-core missing or corrupted), `_get_client()` would succeed (it imports from azure.keyvault and azure.identity), but the exception handling would be wrong. A rate limit or auth error would be caught as "not found" and the secret would silently fall back to environment variable lookup, potentially using a stale or wrong value.

**Evidence:**
```python
except ImportError:
    AzureResourceNotFoundError = Exception  # type: ignore[misc, assignment]
# ...
except AzureResourceNotFoundError as e:  # Now catches EVERYTHING
    raise SecretNotFoundError(...)  # Auth errors become "not found"
```

This is a narrow edge case (partially installed SDK), but in a security-critical system, exception handling paths should not degrade to catching broader exception classes.

### [295-299] CompositeSecretLoader swallows non-SecretNotFoundError from earlier backends

**What:** The `get_secret` method only catches `SecretNotFoundError` when iterating backends (line 298). If an earlier backend (e.g., EnvSecretLoader) raises an unexpected exception (not SecretNotFoundError), it propagates immediately without trying subsequent backends. This is actually correct behavior -- however, the design means that `KeyVaultSecretLoader` Azure operational errors (auth failures, network errors) propagate immediately and crash the pipeline even if the secret exists in a later backend. This is documented and intentional (line 218-219), but worth noting that the composite pattern provides no resilience against transient Azure failures.

**Why it matters:** In production with Azure Key Vault as the primary backend and env vars as fallback, a transient Azure auth token expiry would crash the entire pipeline startup rather than falling back to environment variables.

**Evidence:**
```python
for backend in self._backends:
    try:
        return backend.get_secret(name)
    except SecretNotFoundError:
        continue  # Only this exception triggers fallback
```

## Observations

### [134] EnvSecretLoader returns empty fingerprint

**What:** The SecretRef returned by EnvSecretLoader always has `fingerprint=""` (line 134). The comment on line 132-133 explains this is by design ("that's the caller's responsibility"), but this creates a contract where SecretRef.fingerprint is not always meaningful. Consumers must check if fingerprint is populated before using it for audit verification.

**Why it matters:** Low severity -- the fingerprint is computed later by the recorder (line 569 of recorder.py). But the empty string could be mistaken for a valid empty fingerprint rather than "not yet computed." A sentinel value or Optional[str] would make the contract clearer.

### [82-105] _get_keyvault_client creates a new credential per call

**What:** `_get_keyvault_client()` is a module-level function that creates a new `DefaultAzureCredential()` each time. The `KeyVaultSecretLoader._get_client()` method caches the client (lazy init), so this is only called once per loader instance. However, if `_get_keyvault_client` were called directly (it's not private by convention despite the leading underscore -- it's importable), it would create a new credential chain each time.

**Why it matters:** Negligible -- the function is only called through the cached `_get_client()` path. But the naming convention suggests internal use while Python's module system makes it importable.

### [42-57] SecretRef is well-designed as a frozen dataclass

**What:** Using `frozen=True, slots=True` is correct for an immutable audit record. The class correctly never holds the secret value itself.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Address the AzureResourceNotFoundError fallback on line 191 -- it should raise ImportError immediately if azure.core is not available rather than degrading exception handling. (2) Consider adding a TTL or explicit lifecycle to secret caches, or at minimum ensure `clear_cache()` is called after secrets are consumed and fingerprinted. (3) The empty-fingerprint contract on SecretRef should be documented or made type-explicit (Optional[str]).
**Confidence:** HIGH -- The code is straightforward with no complex control flow. All paths were traced.
