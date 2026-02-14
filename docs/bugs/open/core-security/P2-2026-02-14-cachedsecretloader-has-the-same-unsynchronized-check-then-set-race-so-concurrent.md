## Summary

`CachedSecretLoader` has the same unsynchronized check-then-set race, so concurrent callers can invoke the inner loader multiple times for the same secret despite caching.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P2 — no concurrent callers exist; only production user iterates sequentially in config_secrets.py; merge with KeyVaultSecretLoader race as single item)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/core/security/secret_loader.py`
- Line(s): 243, 257-262
- Function/Method: `CachedSecretLoader.get_secret`

## Evidence

Current logic:

```python
# secret_loader.py:257-262
if name in self._cache:
    return self._cache[name]

result = self._inner.get_secret(name)
self._cache[name] = result
return result
```

This is not atomic. Two concurrent threads can both miss cache and both call `self._inner.get_secret(name)`. Unit tests only validate sequential behavior (`/home/john/elspeth-rapid/tests/unit/core/security/test_secret_loader.py:222-245`), so race behavior is untested.

## Root Cause Hypothesis

The cache wrapper assumes single-threaded access, but class design does not enforce that assumption or protect shared state.

## Suggested Fix

Add a lock-protected critical section for cache miss/fill, ideally with per-key locks to preserve parallelism for different secret names.

## Impact

- Duplicate backend secret lookups under concurrency.
- Unexpected load spikes on underlying secret stores.
- Caching behavior becomes timing-dependent rather than deterministic.

## Triage

- Status: open
- Source report: `docs/bugs/generated/core/security/secret_loader.py.md`
- Finding index in source report: 2
- Beads: pending
