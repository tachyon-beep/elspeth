# Core Security Triage Notes

**Triaged:** 2026-02-14
**Scope:** `docs/bugs/open/core-security/` (6 findings from static analysis)
**Source code reviewed:** `web.py`, `fingerprint.py`, `secret_loader.py`, `config_secrets.py`

## Summary

| # | File | Original | Triaged | Verdict |
|---|------|----------|---------|---------|
| 1 | DNS timeout not effective | P1 | **P1 confirmed** | Real — `ThreadPoolExecutor.__exit__` defeats timeout |
| 2 | Port parsing zero/malformed | P1 | **P1 confirmed** | Real — port 0 misroute + ValueError leak |
| 3 | Empty HMAC key accepted | P1 | **P2 downgrade** | Real gap but no production caller passes `key=b""` |
| 4 | CachedSecretLoader race | P2 | **P3 downgrade** | Real race, no concurrent callers exist; merge with #5 |
| 5 | KeyVaultSecretLoader race | P2 | **P3 downgrade** | Real race, no concurrent callers exist; merge with #4 |
| 6 | Partial env mutation on failure | P2 | **P2 confirmed** | Real — CLI exit limits impact but atomicity gap is genuine |

## Detailed Assessment

### 1. DNS timeout not effective — CONFIRMED P1

The `with ThreadPoolExecutor(...)` at `web.py:226` calls `shutdown(wait=True)` on `__exit__`.
After `future.result(timeout=timeout)` raises `FuturesTimeoutError`, the context manager exit
still blocks until the DNS resolution thread completes. A slow/malicious resolver can stall
row processing indefinitely, defeating the configured timeout.

**Relationship to known P0 TOCTOU:** This is a separate concern from the known P0 DNS rebinding
TOCTOU (where `validate_ip` result is discarded and httpx re-resolves). The P0 is a security
bypass; this P1 is an availability/throughput issue.

**Fix:** Use `shutdown(wait=False, cancel_futures=True)` in a `finally` block instead of the
context manager, or move DNS to a process boundary (threads can't forcibly stop `getaddrinfo`).

### 2. Port parsing zero/malformed — CONFIRMED P1

Two distinct issues at `web.py:210-213`:

1. **Port 0 misrouting:** `if parsed.port:` is falsy for port 0, so it defaults to 443/80.
   The URL says `:0` but the connection goes to a different port. This undermines audit
   traceability (recorded URL doesn't match actual connection).

2. **ValueError leak:** `urlparse("https://example.com:99999").port` raises `ValueError`.
   The function's declared contract (line 196-199) promises only `SSRFBlockedError`/`NetworkError`.
   The downstream caller `web_scrape.py:185-187` catches those types but not `ValueError`,
   so malformed row URLs crash the transform instead of producing error results.

Both are fixable with the pattern in the bug report (try/except + is None check + port 0 rejection).

### 3. Empty HMAC key — DOWNGRADED to P2

The gap is real: `fingerprint.py:79-86` skips validation when `key` is explicitly provided.
`key=b""` produces a predictable HMAC (effectively a keyed hash with known key).

**However, no production caller passes an explicit key without going through `get_fingerprint_key()`:**

- `config_secrets.py:166` — passes `key=fingerprint_key` from `get_fingerprint_key()` (validates non-empty)
- `http.py:257`, `config.py:1507,1596`, `url.py:212` — all use `key=None` → `get_fingerprint_key()` path

The fix is a one-liner (`if len(key) == 0: raise ValueError(...)`) and worthwhile for a security
primitive. But the practical risk is theoretical since no caller provides empty keys.

### 4 & 5. Secret loader race conditions — DOWNGRADED to P3 (merge)

Both `KeyVaultSecretLoader` and `CachedSecretLoader` have classic check-then-act races in
their cache paths. The race is real in concurrent scenarios.

**However, the only production user is `config_secrets.py:153-160`, which iterates sequentially:**

```python
for env_var_name, keyvault_secret_name in ordered_mapping:
    secret_value, _ref = loader.get_secret(keyvault_secret_name)
```

No concurrent access exists. `CachedSecretLoader` is exported but unused in production code.

**These two bugs describe the same pattern** (unsynchronized cache in secret loaders) and should
be tracked as a single code-hardening item. Adding a lock is trivial but unnecessary given the
sequential access pattern.

### 6. Partial env mutation on failure — CONFIRMED P2

`config_secrets.py:153-160` injects each secret into `os.environ` immediately. If secret N+1
fails, secrets 1..N persist in the environment with no rollback.

**Mitigating factor:** CLI exits on `SecretLoadError` (cli.py:422-424), so the partial state
doesn't affect pipeline execution (process terminates). The gap matters only for:
- Programmatic use in the same interpreter
- Future retry-in-process patterns

The fix is clean: load all secrets into a temporary dict, inject only after all succeed,
rollback on failure. P2 is appropriate — real atomicity gap but limited by CLI exit behavior.

## Cross-Cutting Observations

1. **Bugs #4 and #5 are the same pattern.** Should be tracked as one item: "add synchronization
   to secret loader caches." Low priority since access is sequential.

2. **The `web.py` file has three independent issues:** P0 TOCTOU (known), P1 DNS timeout
   (this triage), P1 port parsing (this triage). Consider fixing all three together since they're
   in the same function.
