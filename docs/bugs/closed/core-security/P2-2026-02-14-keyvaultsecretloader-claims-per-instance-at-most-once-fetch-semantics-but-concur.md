## Summary

`KeyVaultSecretLoader` claims per-instance at-most-once fetch semantics, but concurrent `get_secret()` calls can race and issue duplicate Key Vault API calls for the same secret.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — no concurrent callers exist; only production user iterates sequentially in config_secrets.py; merge with CachedSecretLoader race as single item)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/security/secret_loader.py`
- Line(s): 141-143, 157, 159-163, 180-207
- Function/Method: `KeyVaultSecretLoader.get_secret`, `KeyVaultSecretLoader._get_client`

## Evidence

`KeyVaultSecretLoader` documents this guarantee:

```python
# secret_loader.py:141-143
This loader caches secrets to prevent repeated Key Vault API calls.
Each secret is fetched at most once per KeyVaultSecretLoader instance.
```

But the implementation is an unlocked check-then-fetch-then-store sequence:

```python
# secret_loader.py:181-207
if name in self._cache:
    return self._cache[name], ref
client = self._get_client()
secret = client.get_secret(name)
...
self._cache[name] = value
```

and client lazy-init is also unlocked:

```python
# secret_loader.py:161-163
if self._client is None:
    self._client = _get_keyvault_client(self._vault_url)
```

Under concurrent callers, two threads can both miss cache and both call `client.get_secret(name)`, violating the stated contract. Existing tests are single-threaded and do not cover this race (`/home/john/elspeth-rapid/tests/unit/core/security/test_secret_loader.py:115-129`).

## Root Cause Hypothesis

Shared mutable state (`_cache`, `_client`) is accessed with no synchronization, but behavior/docs assume atomic “first fetch wins” semantics.

## Suggested Fix

Add synchronization around client init and cache fill. Preferred pattern:

1. Lock-protect `_client` initialization.
2. Use per-secret lock (or single lock) around cache miss/fill path so only one fetch occurs per secret key.
3. Keep lock scope minimal to avoid unnecessary global serialization if using per-key locks.

## Impact

- Duplicate external calls to Azure Key Vault.
- Increased latency/cost and elevated risk of rate-limit failures.
- Violates module’s documented caching contract; callers relying on at-most-once behavior can get inconsistent startup performance.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/security/secret_loader.py.md`
- Finding index in source report: 1
- Beads: pending
