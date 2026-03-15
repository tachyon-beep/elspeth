# Architecture Analysis: Core Services

**Date:** 2026-02-22
**Branch:** RC3.3-architectural-remediation
**Analyst:** Claude (automated first-principles review)
**Scope:** core/security/, core/rate_limit/, core/retention/, core utilities (logging, operations, payload_store, events)

---

## Per-File Analysis

### 1. `core/security/config_secrets.py`

**Purpose:** Loads secrets from Azure Key Vault based on pipeline YAML configuration and injects them into `os.environ`. Computes HMAC fingerprints immediately -- plaintext values never leave this module.

**Key classes/functions:**
- `SecretLoadError` -- Custom exception for secret loading failures with actionable error messages.
- `load_secrets_from_config(config: SecretsConfig) -> list[dict[str, Any]]` -- Main entry point. Two-phase design: Phase 1 fetches all secrets and computes fingerprints without mutating `os.environ`; Phase 2 applies all env vars atomically. Returns resolution records (with fingerprints, not plaintext) for deferred audit recording.

**Dependencies:**
- `core/security/secret_loader.py` (KeyVaultSecretLoader, SecretNotFoundError) -- imported lazily inside function
- `core/security/fingerprint.py` (get_fingerprint_key, secret_fingerprint)
- `core/config.py` (SecretsConfig, TYPE_CHECKING only)

**Security assessment:**
- Good: Two-phase design prevents partial state on failure.
- Good: ELSPETH_FINGERPRINT_KEY ordering logic ensures it is loaded before other secrets need it.
- Good: Preflight check for fingerprint key availability before any Key Vault calls.
- Concern (minor): Resolution records use `dict[str, Any]` rather than a frozen dataclass. This is one of the 10 open Tier 1 boundary bugs noted in MEMORY.md.

**Architectural patterns:**
- Two-phase commit (fetch all, then apply all)
- Lazy import for optional dependency (Azure SDK)
- Fail-fast on any secret loading failure

**Concerns:**
- **P3: Untyped resolution records.** Returns `list[dict[str, Any]]` instead of a frozen dataclass. This is a known open bug pattern (untyped dicts at Tier 1 boundary). The dict flows into the audit trail recorder.
- **P4: Duplicated Azure auth error detection.** String matching on `"ClientAuthenticationError"` and `"credential"` appears twice (lines 120-126 and 202-208). Could be extracted to a helper.

---

### 2. `core/security/fingerprint.py`

**Purpose:** HMAC-SHA256 fingerprinting for secrets. Produces a 64-char hex digest that can be stored in the audit trail without exposing the secret value.

**Key classes/functions:**
- `get_fingerprint_key() -> bytes` -- Reads `ELSPETH_FINGERPRINT_KEY` from `os.environ`. Raises `ValueError` if not set.
- `secret_fingerprint(secret: str, *, key: bytes | None = None) -> str` -- Computes HMAC-SHA256 digest. Accepts explicit key or reads from env.

**Dependencies:**
- Standard library only: `hashlib`, `hmac`, `os`

**Security assessment:**
- Good: Uses HMAC-SHA256 (not bare SHA256), preventing length-extension attacks.
- Good: Empty key rejection (line 82-83) prevents meaningless fingerprints.
- Good: Previous module-level cache removed -- simpler, less state to reason about.
- Sound: No timing-safe comparison needed here (this is one-way fingerprinting, not verification).

**Architectural patterns:**
- Pure function with optional dependency injection (key parameter)
- Environment variable as configuration fallback

**Concerns:**
- None. This is a clean, minimal module.

---

### 3. `core/security/secret_loader.py`

**Purpose:** General-purpose secret loading abstraction with multiple backends (env vars, Azure Key Vault), caching, and composite fallback chains.

**Key classes/functions:**
- `SecretNotFoundError` -- Exception for missing secrets.
- `SecretRef` -- Frozen dataclass for audit trail references (name, fingerprint, source). Does NOT contain the secret value.
- `SecretLoader` -- Protocol defining the `get_secret(name) -> tuple[str, SecretRef]` interface.
- `EnvSecretLoader` -- Reads from `os.environ`. Does not compute fingerprints (caller's responsibility).
- `KeyVaultSecretLoader` -- Azure Key Vault backend with thread-safe caching. Lazy client initialization. Only caches successful lookups.
- `CachedSecretLoader` -- Generic caching wrapper for any `SecretLoader`. Thread-safe.
- `CompositeSecretLoader` -- Tries backends in priority order, stops on first success.

**Dependencies:**
- Standard library: `os`, `threading`, `dataclasses`
- Optional: `azure.keyvault.secrets`, `azure.identity` (lazy import)

**Security assessment:**
- Good: `SecretRef` is frozen and never contains plaintext values.
- Good: Thread-safe caching with locks.
- Good: Only `AzureResourceNotFoundError` triggers fallback; auth errors and other operational failures propagate (fail-fast).
- Good: Sentinel class pattern for `AzureResourceNotFoundError` when azure.core is not installed prevents accidental broad exception catching.

**Architectural patterns:**
- Protocol-based abstraction (SecretLoader)
- Composite pattern (CompositeSecretLoader)
- Decorator/wrapper pattern (CachedSecretLoader)
- Lazy initialization (Key Vault client)

**Concerns:**
- **P4: Redundant caching layers.** `KeyVaultSecretLoader` has its own `_cache` dict AND `CachedSecretLoader` provides the same behavior as a wrapper. Both exist in the codebase but serve the same purpose. If `KeyVaultSecretLoader` is always wrapped in `CachedSecretLoader`, the internal cache is redundant; if used directly, `CachedSecretLoader` is dead code for that path. The code is sound but could be simplified.
- **P4: `SecretRef.fingerprint` is empty string from loaders.** Both `EnvSecretLoader` and `KeyVaultSecretLoader` return `SecretRef(fingerprint="")` and document that fingerprinting is the caller's responsibility. This is correct but means `SecretRef` is partially populated until the caller fills it in. The `fingerprint=""` sentinel could be confused with "no fingerprint available" vs "not yet computed."

---

### 4. `core/security/web.py`

**Purpose:** SSRF prevention infrastructure. Validates URLs, blocks private/loopback/metadata IPs, and provides DNS-pinning via `SSRFSafeRequest` to eliminate TOCTOU DNS rebinding attacks.

**Key classes/functions:**
- `SSRFBlockedError` -- Security policy violation.
- `NetworkError` -- DNS/connection failures.
- `ALLOWED_SCHEMES` -- `{"http", "https"}` only.
- `BLOCKED_IP_RANGES` -- Comprehensive blocklist (IPv4 private, loopback, link-local, CGNAT; IPv6 loopback, unique local, link-local, IPv4-mapped).
- `validate_url_scheme(url)` -- Scheme allowlist check.
- `_resolve_hostname(hostname) -> list[str]` -- DNS resolution via `getaddrinfo()` (IPv4+IPv6).
- `_validate_ip_address(ip_str)` -- Check IP against blocklist. Fail-closed on unparseable IPs.
- `SSRFSafeRequest` -- Frozen dataclass with `connection_url` (IP-based), `host_header`, `sni_hostname`. Eliminates rebinding by resolving once and pinning.
- `validate_url_for_ssrf(url, timeout) -> SSRFSafeRequest` -- Main entry point. Validates scheme, resolves DNS with timeout, validates all IPs, returns pinned request.

**Dependencies:**
- Standard library: `ipaddress`, `queue`, `socket`, `urllib.parse`, `concurrent.futures`, `dataclasses`
- No third-party dependencies

**Security assessment:**
- **RESOLVED: DNS rebinding TOCTOU.** The MEMORY.md P0 states "validate_ip result discarded, httpx re-resolves." However, the current code returns `SSRFSafeRequest` with a pinned IP and `connection_url` property that replaces the hostname with the resolved IP. **The TOCTOU vulnerability is architecturally solved in this module.** The remaining question is whether callers actually USE `SSRFSafeRequest.connection_url` + `host_header` rather than the `original_url`. This is a **caller-side concern**, not a defect in `web.py` itself.
- Good: Fail-closed on unparseable IP addresses (line 122-124).
- Good: Validates ALL resolved IPs, not just the first (attacker could return mix of safe/unsafe).
- Good: IPv4-mapped IPv6 (`::ffff:0:0/96`) is blocked, preventing a common bypass vector.
- Good: Port 0 explicitly rejected.
- Good: Bounded thread pool for DNS resolution (`_DNS_POOL_SIZE = 8`), preventing thread exhaustion under repeated timeouts.
- Concern: Fragment included in path (line 233-234). Fragments are not sent to the server per HTTP spec, but including them in the `connection_url` is harmless (httpx strips them).

**Architectural patterns:**
- Frozen dataclass as security boundary token (SSRFSafeRequest)
- Bounded thread pool for DNS resolution
- Queue-based timeout mechanism for DNS resolution
- Fail-closed design throughout

**Concerns:**
- **P1: Caller verification needed.** The SSRF defense is only effective if callers use `connection_url` + `host_header` instead of `original_url`. This needs an audit of all call sites (likely in `plugins/clients/`). If even one caller uses `safe_request.original_url` for the actual HTTP request, the TOCTOU is reintroduced.
- **P3: Module-level thread pool.** `_dns_pool` is created at import time as a module global. This is a `ThreadPoolExecutor` with 8 worker threads. It is never explicitly shut down. While daemon threads (the default) will be cleaned up at process exit, this could cause issues in test environments with module reloading or with `atexit` handlers that expect clean shutdown. In practice, the bounded size (8) makes this low-risk.
- **P4: Fragment in path.** URL fragments (`#...`) are included in `SSRFSafeRequest.path` (line 233-234), which will be included in `connection_url`. Per HTTP spec, fragments are client-side only and should not be sent. Most HTTP libraries strip them, so this is cosmetic rather than a bug.

---

### 5. `core/rate_limit/limiter.py`

**Purpose:** Rate limiter wrapper around `pyrate-limiter`, providing per-service sliding-window rate limiting with optional SQLite persistence.

**Key classes/functions:**
- `_suppressed_thread_idents` / `_custom_excepthook` -- Thread exception suppression for known benign `AssertionError` from pyrate-limiter's Leaker thread during cleanup. Lazy hook installation/uninstallation.
- `RateLimiter` -- Main class. Validates name (SQL-safe pattern), creates pyrate-limiter bucket (in-memory or SQLite-backed), provides `acquire()` (blocking with polling), `try_acquire()` (non-blocking), `close()`. Context manager support.

**Dependencies:**
- `pyrate-limiter` (BucketFullException, Duration, InMemoryBucket, Limiter, Rate, SQLiteBucket, SQLiteQueries)
- Standard library: `math`, `re`, `sqlite3`, `threading`, `time`

**Security assessment:**
- Good: Name validation via regex prevents SQL injection when name is used in table names (line 146).
- Good: SQLite `check_same_thread=False` is intentional for cross-thread access (protected by limiter's own lock).

**Architectural patterns:**
- Wrapper/adapter pattern around pyrate-limiter
- Thread exception hook for graceful cleanup of third-party library quirks
- Spin-wait polling in `acquire()` with configurable timeout
- Context manager protocol

**Concerns:**
- **P2: Spin-wait polling in `acquire()`.** The blocking acquire uses a 10ms sleep-and-retry loop (lines 213-226). For high-contention scenarios with many threads, this wastes CPU. A condition variable or event-based wake would be more efficient. However, rate limiters in ELSPETH are per-external-service (low contention), so this is likely acceptable in practice.
- **P3: `threading.excepthook` global mutation.** The custom excepthook replaces `threading.excepthook` globally (lines 43-46). While carefully managed (lazy install, uninstall when idle), this is inherently fragile in environments where other libraries also replace the hook. The save-and-restore pattern could silently drop the hook installed by another library if ordering is wrong. The narrow suppression scope (only registered thread idents, only AssertionError) mitigates the risk.
- **P3: `try_acquire` temporarily mutates `max_delay`.** Lines 239-247 temporarily set `self._limiter.max_delay = None` inside a lock to get immediate response, then restores it. This is a code smell -- it relies on the pyrate-limiter internal not reading `max_delay` from another thread during the window. The lock protects against concurrent `try_acquire` calls, but if pyrate-limiter's Leaker thread reads `max_delay`, there is a potential race. Low risk given pyrate-limiter's implementation, but fragile.
- **P4: Leaker thread internals.** `close()` accesses `self._limiter.bucket_factory._leaker` (line 258), which is a private attribute of pyrate-limiter. The code handles `AttributeError` gracefully, but this coupling to third-party internals means version upgrades could break cleanup.

---

### 6. `core/rate_limit/registry.py`

**Purpose:** Per-service rate limiter registry. Creates and caches `RateLimiter` instances on demand based on runtime configuration.

**Key classes/functions:**
- `NoOpLimiter` -- No-op implementation for when rate limiting is disabled. Same interface as `RateLimiter`.
- `RateLimitRegistry` -- Thread-safe registry. `get_limiter(service_name)` returns cached limiter or creates new one from config. `reset_all()` and `close()` for cleanup.

**Dependencies:**
- `core/rate_limit/limiter.py` (RateLimiter)
- `contracts/config/protocols.py` (RuntimeRateLimitProtocol, TYPE_CHECKING only)

**Security assessment:**
- No security concerns. Clean delegation pattern.

**Architectural patterns:**
- Registry pattern (lazy creation, caching)
- Null object pattern (NoOpLimiter)
- Protocol-based configuration injection (RuntimeRateLimitProtocol)

**Concerns:**
- **P4: `NoOpLimiter` is not a formal protocol implementation.** `NoOpLimiter` and `RateLimiter` share the same interface but neither implements a shared protocol. The return type annotation `RateLimiter | NoOpLimiter` (line 84) is a union rather than a common protocol. This makes type narrowing awkward for callers. A `RateLimiterProtocol` would formalize the interface.

---

### 7. `core/retention/purge.py`

**Purpose:** Identifies and deletes expired payloads from the `PayloadStore` based on retention policy, while preserving audit trail hashes in Landscape. Updates reproducibility grades after purge.

**Key classes/functions:**
- `PurgeResult` -- Dataclass with deletion statistics (deleted_count, bytes_freed, skipped_count, failed_refs, duration_seconds).
- `PurgeManager` -- Main class.
  - `find_expired_row_payloads(retention_days, as_of)` -- Finds row payloads from completed/failed runs older than cutoff.
  - `find_expired_payload_refs(retention_days, as_of)` -- Comprehensive: finds all payload refs (rows, operations, calls, routing) from expired runs, EXCLUDING refs still used by active runs (content-addressable dedup safety).
  - `purge_payloads(refs)` -- Deletes payloads, tracks success/failure, updates reproducibility grades for affected runs.

**Dependencies:**
- `contracts/payload_store.py` (PayloadStore protocol)
- `core/landscape/reproducibility.py` (update_grade_after_purge)
- `core/landscape/schema.py` (calls_table, node_states_table, operations_table, routing_events_table, rows_table, runs_table)
- `core/landscape/database.py` (LandscapeDB, TYPE_CHECKING only)
- SQLAlchemy (and_, or_, select, union)

**Security assessment:**
- Good: Active run exclusion prevents premature payload deletion that would break replay.
- Good: Content-addressable dedup handled correctly via set difference (expired_refs - active_refs).
- Good: Chunked queries (`_PURGE_CHUNK_SIZE = 100`) to avoid exceeding SQLite bind variable limits.
- Good: Uses `node_states.run_id` directly per composite PK pattern (avoids ambiguous join through nodes table).

**Architectural patterns:**
- Set-difference anti-join for safe deletion with content-addressable storage
- Chunked batch operations for SQLite limits
- Reproducibility grade degradation after purge

**Concerns:**
- **P2: `PurgeResult` is a mutable dataclass.** It is not frozen. While it is constructed once and returned, the lack of immutability is inconsistent with the project's preference for frozen dataclasses at boundaries. It also has `bytes_freed` that is always 0 with a comment saying "retained for future compatibility" -- this smells like the legacy/compatibility patterns CLAUDE.md prohibits.
- **P3: Serial deletion.** `purge_payloads()` deletes payloads one at a time in a loop (lines 455-479). For large purges, this could be slow. There is no batching or parallelism. However, since payloads are filesystem files, this is I/O-bound and parallelism might not help significantly on a single disk.
- **P3: Two `find_expired_*` methods with overlapping logic.** `find_expired_row_payloads()` is a subset of `find_expired_payload_refs()`. The former only covers `rows.source_data_ref`, while the latter covers all payload reference columns. Having both creates maintenance burden -- changes to the expiration logic must be reflected in both. `find_expired_row_payloads()` appears to be an older, narrower API that should potentially be deprecated in favor of the comprehensive method.
- **P3: `purge_payloads` checks `exists()` then `delete()` (TOCTOU).** Lines 457-479 call `self._payload_store.exists(ref)` and then `self._payload_store.delete(ref)` as separate operations. Between the two, another process could delete the file. The result would be that `delete()` returns `False` (file gone), and the ref would be counted as a failed deletion rather than already-skipped. This is a minor accounting error, not a data integrity issue. Could be simplified to just call `delete()` and handle the not-found case.

---

### 8. `core/logging.py`

**Purpose:** Configures both structlog and stdlib logging to produce consistent output (JSON or console). Routes stdlib log records through structlog's processor chain via `ProcessorFormatter`.

**Key classes/functions:**
- `_NOISY_LOGGERS` -- Tuple of third-party logger names to silence at WARNING level.
- `_remove_internal_fields()` -- Processor that removes structlog internal bookkeeping fields.
- `configure_logging(json_output, level)` -- Main configuration function. Sets up structlog, stdlib handler, and silences noisy loggers.
- `get_logger(name) -> BoundLogger` -- Factory for bound loggers.

**Dependencies:**
- `structlog` (stdlib, dev, contextvars, processors modules)
- Standard library: `logging`, `sys`

**Security assessment:**
- No security concerns. Logging configuration only.
- Note: No log redaction or secret scrubbing. If secrets accidentally appear in log messages, they will be emitted. This is acceptable because ELSPETH's design prevents secrets from reaching log calls (fingerprinting happens at the boundary), but there is no defense-in-depth here.

**Architectural patterns:**
- Dual-framework logging (structlog + stdlib unified)
- Processor pipeline for log enrichment

**Concerns:**
- **P4: `cache_logger_on_first_use=False`.** Line 116 disables structlog's logger caching for test reconfigurability. This has a small performance cost (logger setup on every `get_logger()` call). In production, caching could be enabled. This is documented in the comment and is a reasonable tradeoff.
- **P4: `root.handlers = []` replaces all handlers.** Line 133 clears all existing handlers on the root logger. If `configure_logging()` is called after another library has added handlers (e.g., OpenTelemetry log exporters), those handlers are lost. This is by design (ELSPETH owns the logging configuration) but worth noting for telemetry integration.

---

### 9. `core/operations.py`

**Purpose:** Operation lifecycle management for source/sink I/O. Provides `track_operation` context manager that handles operation creation, context wiring, duration tracking, exception capture, and audit integrity enforcement.

**Key classes/functions:**
- `OperationHandle` -- Mutable dataclass for capturing output data during operation execution.
- `track_operation(recorder, run_id, node_id, operation_type, ctx, input_data)` -- Context manager. Creates operation via recorder, wires `ctx.operation_id`, captures status/error/duration, calls `complete_operation()` in `finally`. Handles `BatchPendingError` as control flow (not error). Enforces audit integrity: if DB write fails and original operation succeeded, the DB error is raised.

**Dependencies:**
- `contracts` (BatchPendingError, Operation, PluginContext)
- `core/landscape/recorder.py` (LandscapeRecorder, TYPE_CHECKING only)
- Standard library: `logging`, `time`, `contextlib`, `dataclasses`

**Security assessment:**
- Good: Audit integrity enforcement -- if `complete_operation()` fails and the operation itself succeeded, the DB error propagates. This prevents silent audit gaps.
- Good: BaseException handler (line 142) catches `KeyboardInterrupt`/`SystemExit` to prevent interrupted operations from being recorded as "completed."
- Good: Context cleanup in `finally` (line 181) restores previous `operation_id`, preventing accidental reuse.

**Architectural patterns:**
- Context manager for resource lifecycle
- Audit integrity enforcement (fail the run on audit write failure)
- Mutable handle for output capture

**Concerns:**
- **P3: `OperationHandle` is a mutable dataclass.** Contains `Operation` (likely also mutable) and `output_data: dict[str, Any] | None`. The mutability is intentional (caller sets `output_data` during the context), but `output_data` being `dict[str, Any]` is another instance of the untyped-dict-at-boundary pattern.

---

### 10. `core/payload_store.py`

**Purpose:** Content-addressable filesystem storage for large payloads. Stores by SHA-256 hash with sharded directory structure (first 2 chars as subdirectory).

**Key classes/functions:**
- `FilesystemPayloadStore` -- Main implementation of `PayloadStore` protocol.
  - `_path_for_hash(content_hash)` -- Validates hash format (64 lowercase hex chars), constructs path, verifies no path traversal.
  - `store(content: bytes) -> str` -- Stores content, atomic write via temp file + `os.replace()` + `fsync()`. Verifies integrity of existing files on store.
  - `retrieve(content_hash) -> bytes` -- Reads and verifies integrity with timing-safe comparison.
  - `exists(content_hash) -> bool` -- Simple path check.
  - `delete(content_hash) -> bool` -- Unlink with FileNotFoundError handling.

**Dependencies:**
- `contracts/payload_store.py` (PayloadStore protocol, IntegrityError)
- Standard library: `hashlib`, `hmac`, `os`, `re`, `tempfile`, `pathlib`

**Security assessment:**
- Good: Path traversal prevention via regex validation + `resolve().is_relative_to()` defense-in-depth.
- Good: Timing-safe comparison (`hmac.compare_digest`) on retrieve and store to prevent timing attacks.
- Good: Atomic writes via `NamedTemporaryFile` + `os.replace()` + `fsync()` + directory `fsync()`. This resolves the "non-atomic file writes" concern from MEMORY.md for the store path.
- Good: Integrity verification on both store (existing file check) and retrieve.
- Note: `delete()` (lines 162-173) is NOT atomic -- `unlink()` followed by return. But for content-addressable storage, this is fine: the worst case is concurrent delete + retrieve, where retrieve sees `FileNotFoundError` and raises `KeyError`, which is the correct behavior.

**Architectural patterns:**
- Content-addressable storage (CAS)
- Sharded directory structure
- Atomic write with fsync
- Protocol-based contract

**Concerns:**
- **P3: `exists()` then `retrieve()` TOCTOU in callers.** `FilesystemPayloadStore` itself is sound, but callers that check `exists()` before `retrieve()` have a race. The `retrieve()` method properly handles `FileNotFoundError`, so callers should just call `retrieve()` and catch `KeyError`. This is a caller-side concern.
- **P4: No size tracking.** `PurgeResult.bytes_freed` is always 0 because the store doesn't track content size. To support size tracking, `store()` would need to return `(hash, size)` or `delete()` would need to return size. Minor -- size tracking is a nice-to-have for operational monitoring.

---

### 11. `core/events.py`

**Purpose:** Synchronous event bus for pipeline observability. Provides clean decoupling between orchestrator domain logic and CLI presentation.

**Key classes/functions:**
- `EventBusProtocol` -- Protocol defining `subscribe()` and `emit()`.
- `EventBus` -- Production implementation. Stores subscribers by event type, dispatches synchronously. Handler exceptions propagate (handlers are system code).
- `NullEventBus` -- No-op implementation for library/programmatic use. Does NOT inherit from EventBus (protocol-based design prevents substitution bugs).

**Dependencies:**
- Standard library only: `collections.abc`, `typing`

**Security assessment:**
- No security concerns. Pure in-process event dispatch.

**Architectural patterns:**
- Observer pattern (publish-subscribe)
- Null object pattern (NullEventBus)
- Protocol-based design (no inheritance)

**Concerns:**
- **P4: No unsubscribe mechanism.** Once a handler is subscribed, it cannot be removed. For the current use case (CLI formatters subscribe at startup and persist for the run lifetime), this is fine. If event bus usage expands, unsubscription may be needed.
- **P4: No handler ordering guarantee beyond insertion order.** Handlers run in subscription order, which is insertion order of `list.append()`. This is deterministic but implicit. For current usage (independent formatters), this is fine.

---

## Overall Architecture Analysis

### 1. Security Architecture

The security subsystem is well-designed with clear separation of concerns:

| Module | Responsibility |
|--------|---------------|
| `fingerprint.py` | HMAC-SHA256 fingerprinting (pure function) |
| `secret_loader.py` | Backend abstraction (env, Key Vault, composite) |
| `config_secrets.py` | Config-driven loading with two-phase commit |
| `web.py` | SSRF prevention with DNS pinning |

**Strengths:**
- Secrets never leave the boundary modules as plaintext (fingerprinted immediately).
- SSRF defense is architecturally sound -- `SSRFSafeRequest` is a frozen "security token" that carries the pinned IP.
- Azure Key Vault integration is cleanly isolated behind lazy imports and optional dependency patterns.
- Fail-fast semantics throughout: missing secrets, auth failures, and blocked IPs all raise immediately.

**Weaknesses:**
- The SSRF defense depends on callers using `connection_url` + `host_header`. A single call site using `original_url` re-introduces TOCTOU. This needs call-site audit.
- No log redaction / secret scrubbing as defense-in-depth.
- Resolution records at the `config_secrets` -> audit recorder boundary are untyped dicts.

### 2. Rate Limiting Model

Rate limiting uses a three-layer architecture:

```
RuntimeRateLimitConfig (frozen dataclass)
    -> RateLimitRegistry (per-service caching)
        -> RateLimiter (pyrate-limiter wrapper)
```

**Configuration flow:** Pipeline YAML -> `RateLimitSettings` (Pydantic) -> `RuntimeRateLimitConfig` (frozen dataclass) -> `RateLimitRegistry` -> per-service `RateLimiter` instances.

**Strengths:**
- Protocol-based configuration injection.
- Null object pattern (`NoOpLimiter`) for disabled state.
- SQLite persistence option for cross-process rate limiting.
- Thread-safe throughout.

**Weaknesses:**
- Spin-wait polling in `acquire()`. Under high contention, this wastes CPU. Low risk in practice (low contention per service).
- Heavy coupling to pyrate-limiter internals (Leaker thread, `_leaker` attribute) for graceful cleanup. This is well-guarded with `try/except AttributeError` but remains fragile across library versions.
- Global `threading.excepthook` mutation is the most fragile aspect. It works but is a source of subtle bugs if other libraries also hook exceptions.

### 3. Retention/Purge Architecture

The purge system correctly handles the most complex challenge of content-addressable storage: **shared refs across runs**.

**Flow:**
1. `find_expired_payload_refs()` identifies refs from expired runs.
2. Same method identifies refs from active runs.
3. Python set difference ensures only refs exclusive to expired runs are deleted.
4. `purge_payloads()` deletes blobs, preserving hashes in Landscape.
5. Reproducibility grades are downgraded for affected runs.

**Strengths:**
- Comprehensive coverage of all payload reference columns (rows, operations, calls, routing).
- Correct handling of content-addressable dedup (shared refs).
- Chunked queries for SQLite bind variable limits.
- Correct use of `node_states.run_id` (composite PK pattern compliance).

**Weaknesses:**
- Two overlapping `find_expired_*` methods (maintenance burden).
- `PurgeResult` is mutable with a vestigial `bytes_freed` field.
- Serial deletion (no batching/parallelism).
- TOCTOU between `exists()` and `delete()` in `purge_payloads()` (minor accounting error, not data loss).

### 4. Payload Store

Content-addressable storage is well-implemented:

**Strengths:**
- Atomic writes with `fsync()` -- resolves the known non-atomic write concern from MEMORY.md.
- Path traversal prevention with regex + `resolve().is_relative_to()`.
- Timing-safe integrity verification.
- Clean protocol contract in `contracts/payload_store.py`.

**Weaknesses:**
- No size tracking (minor).
- No concurrent write protection beyond atomic rename (acceptable for CAS -- concurrent writes produce the same content).

### 5. Event System

Simple, correct synchronous event bus:

**Strengths:**
- Protocol-based design (no inheritance).
- Handler exceptions propagate (system code = crash on bug).
- NullEventBus for library use.
- Zero dependencies.

**Weaknesses:**
- No unsubscribe (acceptable for current use case).
- Synchronous dispatch means slow handlers block the pipeline. If a formatter hangs, the pipeline hangs. Acceptable because formatters are simple print operations.

### 6. Cross-Cutting Dependencies

```
core/security/          -> contracts/ (TYPE_CHECKING), core/config (TYPE_CHECKING)
core/rate_limit/        -> contracts/config/protocols (TYPE_CHECKING), pyrate-limiter
core/retention/         -> contracts/payload_store, core/landscape/ (schema, database, reproducibility)
core/payload_store.py   -> contracts/payload_store
core/operations.py      -> contracts/ (BatchPendingError, Operation, PluginContext), core/landscape/recorder
core/events.py          -> (none)
core/logging.py         -> structlog
```

Dependency structure is clean. `core/events.py` and `core/logging.py` are leaf nodes. `core/retention/` has the most dependencies (Landscape schema, database, reproducibility). Security modules are well-isolated with lazy imports for optional Azure SDK.

### 7. Known Issues Assessment

| Known Issue | Status | Notes |
|-------------|--------|-------|
| DNS rebinding TOCTOU in web.py | **Architecturally resolved in web.py** | Caller-side audit needed |
| Non-atomic file writes in payload_store | **Resolved** | Atomic write with fsync implemented |
| Untyped dicts at Tier 1 boundary | **Open** | config_secrets.py resolution records, operations.py output_data |

### 8. Concerns and Recommendations (Ranked by Severity)

**P1 -- High Priority:**

1. **SSRF caller-site audit.** Verify all consumers of `validate_url_for_ssrf()` use `SSRFSafeRequest.connection_url` + `host_header`, not `original_url`. A single call site using `original_url` re-introduces the TOCTOU DNS rebinding vulnerability. This is the highest-priority item because it is a security concern that cannot be verified from `web.py` alone.

**P2 -- Medium Priority:**

2. **Untyped resolution records in `config_secrets.py`.** `load_secrets_from_config()` returns `list[dict[str, Any]]`. This should be a frozen dataclass (e.g., `SecretResolution`) for Tier 1 boundary compliance. This is part of the broader 10-bug pattern noted in MEMORY.md.

3. **`PurgeResult` should be frozen.** Make it `@dataclass(frozen=True, slots=True)` and remove the vestigial `bytes_freed` field (always 0, retained "for future compatibility" in violation of the No Legacy Code policy).

4. **Rate limiter `acquire()` spin-wait.** Replace 10ms polling loop with condition-variable or event-based wake for efficiency under contention. Low urgency given current usage patterns.

**P3 -- Low Priority:**

5. **Redundant caching in `secret_loader.py`.** `KeyVaultSecretLoader` has internal cache AND `CachedSecretLoader` wraps any loader with caching. Consolidate to one caching layer.

6. **Two overlapping `find_expired_*` methods in `purge.py`.** Consider deprecating `find_expired_row_payloads()` in favor of the comprehensive `find_expired_payload_refs()`, or have the former delegate to the latter with a filter.

7. **`purge_payloads()` TOCTOU between `exists()` and `delete()`.** Simplify to just call `delete()` directly and interpret the boolean return: `True` = deleted, `False` = already gone (count as skipped).

8. **`threading.excepthook` global mutation in limiter.** Document this as a known interaction risk for environments with other libraries that also hook thread exceptions.

9. **Module-level thread pool in `web.py`.** Consider lazy initialization or `atexit` cleanup registration.

**P4 -- Informational:**

10. **`NoOpLimiter` / `RateLimiter` lack shared protocol.** A formal `RateLimiterProtocol` would improve type safety.

11. **`SecretRef.fingerprint` empty string sentinel.** Consider `Optional[str]` or a more explicit "not yet computed" representation.

12. **No unsubscribe in `EventBus`.** Fine for current use, but may need extension.

13. **Fragment handling in `web.py` `SSRFSafeRequest.path`.** Cosmetic -- fragments are stripped by HTTP libraries.

### 9. Confidence

**High.** All 11 files were read in full. The code is well-documented with clear rationale for design decisions. The security architecture is sound in principle; the main risk is at integration points (callers of `SSRFSafeRequest`). The known issues from MEMORY.md are accurately categorized -- the payload_store non-atomic write concern has been resolved, and the DNS rebinding TOCTOU is architecturally addressed in `web.py` but requires caller verification.
