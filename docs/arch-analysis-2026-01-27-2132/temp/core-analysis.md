# ELSPETH Core Subsystem Analysis

**Analyst:** Architecture Review Agent
**Date:** 2026-01-27
**Scope:** `src/elspeth/core/` - Configuration, Canonicalization, DAG, Events, Logging, Payload Store, Checkpoint, Rate Limit, Retention, Security

---

## Executive Summary

The Core subsystem provides foundational infrastructure for the ELSPETH auditable pipeline framework. The code is generally well-structured and follows the documented architectural principles. However, this analysis identifies several non-obvious issues that could impact production readiness:

1. **Critical:** Rate limiting subsystem is completely disconnected from the engine
2. **Critical:** Multiple protocol definitions for the same abstraction (PayloadStore)
3. **High:** Retention policy creates silent data loss risk during resume
4. **High:** OpenTelemetry integration mentioned but not implemented
5. **Medium:** Secret fingerprinting has inconsistent behavior across different entry points

---

## 1. config.py - Configuration Loading

**Location:** `src/elspeth/core/config.py` (1228 lines)

### Design Issues

#### DI-1: Circular Import Pattern in Validators
**File:Line:** `config.py:91-102`, `config.py:201-214`, `config.py:281`
**Severity:** Medium

The config validators import `ExpressionParser` inside the validator methods:
```python
@field_validator("condition")
@classmethod
def validate_condition_expression(cls, v: str | None) -> str | None:
    if v is None:
        return v
    from elspeth.engine.expression_parser import (  # Deferred import
        ExpressionParser,
        ExpressionSecurityError,
        ExpressionSyntaxError,
    )
```

This creates a hidden dependency from core -> engine, which inverts the expected dependency direction. Configuration should be independent of engine internals.

**Impact:** Makes testing harder; prevents config validation without loading the full engine.

#### DI-2: Implicit Environment Variable Contract
**File:Line:** `config.py:746-789`
**Severity:** Low

The `_expand_env_vars` function silently preserves unexpanded variables when the env var is missing and no default is specified:
```python
if env_value is not None:
    return env_value
if default is not None:
    return default
# No env var and no default - keep original (will likely cause error)
return match.group(0)  # Returns "${VAR}" unchanged
```

**Impact:** Users get confusing validation errors downstream instead of a clear "missing env var" message at config load time.

### Functionality Gaps

#### FG-1: No Validation of Gate Route Destination Semantics
**File:Line:** `config.py:229-244`
**Severity:** Medium

The comment explicitly states validation is deferred:
```python
# Sink name validation is deferred to DAG compilation where we have
# access to the actual sink definitions.
```

While this is documented, it means configuration can pass validation but fail at graph compilation, giving a poor user experience.

### Configuration Issues

#### CI-1: PayloadStoreSettings Backend Field Not Validated
**File:Line:** `config.py:587-598`
**Severity:** Medium

```python
class PayloadStoreSettings(BaseModel):
    backend: str = Field(default="filesystem", ...)
```

The `backend` field accepts any string but only "filesystem" is implemented. There's no enum or validation to restrict to supported backends.

---

## 2. canonical.py - Deterministic JSON Serialization

**Location:** `src/elspeth/core/canonical.py` (287 lines)

### Design Issues

#### DI-3: repr_hash() Undermines Canonicalization Guarantee
**File:Line:** `canonical.py:263-287`
**Severity:** High

The `repr_hash()` function is documented as a fallback for non-canonical data:
```python
"""Generate SHA-256 hash of repr() for non-canonical data.

Used as fallback when canonical_json fails (NaN, Infinity, or other
non-serializable types). This provides deterministic hashing within
the same Python version, but is NOT guaranteed to be stable across
different Python versions due to repr() implementation differences.
```

**Critical Issue:** If `repr_hash()` is ever used for data that enters the audit trail, cross-version verification becomes impossible. There's no tracking of which hash method was used.

**Impact:** Audit integrity violation if repr_hash results are stored without marking them as non-canonical.

### Functionality Gaps

#### FG-2: No Hash Algorithm Negotiation
**File:Line:** `canonical.py:34-35`
**Severity:** Low

```python
CANONICAL_VERSION = "sha256-rfc8785-v1"
```

The version string is stored but there's no mechanism to verify or upgrade hash algorithms. If ELSPETH ever needs to move to SHA-3, there's no migration path.

---

## 3. dag.py - Execution Graph

**Location:** `src/elspeth/core/dag.py` (1025 lines)

### Design Issues

#### DI-4: NodeInfo is Mutable Despite Documentation
**File:Line:** `dag.py:41-55`
**Severity:** Medium

The docstring says schemas are immutable:
```python
@dataclass
class NodeInfo:
    """Information about a node in the execution graph.

    Schemas are immutable after graph construction.
    """
```

But the dataclass is not frozen, and line 754 directly mutates the config:
```python
graph.get_node_info(coalesce_id).config["schema"] = first_schema
```

**Impact:** Potential for subtle bugs where node info is inadvertently modified after construction.

#### DI-5: Internal Maps Exposed via Property Accessors
**File:Line:** `dag.py:761-840`
**Severity:** Low

All the getter methods return `dict(self._xxx_map)` creating shallow copies:
```python
def get_sink_id_map(self) -> dict[SinkName, NodeID]:
    return dict(self._sink_id_map)
```

This is defensive but creates unnecessary object churn. Consider `MappingProxyType` for true immutability.

### Functionality Gaps

#### FG-3: No Graph Serialization
**File:Line:** N/A (missing functionality)
**Severity:** Medium

The ExecutionGraph has no `to_dict()` or `from_dict()` methods. This means:
- Graphs cannot be persisted for debugging
- Replay/verify mode must reconstruct the graph from config (potential divergence)
- No way to diff graphs between runs

### Wiring Problems

#### WP-1: Schema Validation Only Catches Some Mismatches
**File:Line:** `dag.py:996-1024`
**Severity:** Medium

```python
def _get_missing_required_fields(
    self,
    producer_schema: type[PluginSchema] | None,
    consumer_schema: type[PluginSchema] | None,
) -> list[str]:
```

This only checks for missing required fields. It doesn't check:
- Type mismatches (producer says `int`, consumer expects `str`)
- Extra fields that might cause downstream issues
- Nested schema compatibility

---

## 4. events.py - Event Bus

**Location:** `src/elspeth/core/events.py` (112 lines)

### Design Issues

#### DI-6: No Event Type Registry
**File:Line:** `events.py:43-86`
**Severity:** Low

Event types are subscribed by class reference but there's no discovery mechanism. Code that wants to subscribe to all events must know all event types a priori.

### Observability Gaps

#### OG-1: No Event Metrics
**File:Line:** `events.py:63-85`
**Severity:** Medium

The event bus has no instrumentation:
- No count of events emitted
- No timing of handler execution
- No tracking of unhandled events (events with no subscribers)

---

## 5. logging.py - Structured Logging

**Location:** `src/elspeth/core/logging.py` (79 lines)

### Observability Gaps

#### OG-2: OpenTelemetry Integration Mentioned But Missing
**File:Line:** `logging.py:3-6`
**Severity:** High

The docstring claims:
```python
"""Structured logging configuration for ELSPETH.

Uses structlog for structured logging that complements
OpenTelemetry spans for observability.
"""
```

But there is no OpenTelemetry configuration anywhere in the core subsystem. The `events.py` module provides an event bus, but there's no:
- Tracer configuration
- Span creation utilities
- Trace context propagation

**Impact:** The advertised observability architecture is not implemented.

#### OG-3: No Log Correlation
**File:Line:** `logging.py:15-65`
**Severity:** Medium

While `structlog.contextvars.merge_contextvars` is configured, there's no:
- run_id injection
- token_id correlation
- span ID propagation from OpenTelemetry (since it's not configured)

---

## 6. payload_store.py - Large Blob Storage

**Location:** `src/elspeth/core/payload_store.py` (156 lines)

### Design Issues

#### DI-7: Protocol vs Implementation Mismatch
**File:Line:** `payload_store.py:28-83` vs `retention/purge.py:28-41`
**Severity:** Critical

There are TWO different Protocol definitions for PayloadStore:

In `payload_store.py`:
```python
@runtime_checkable
class PayloadStore(Protocol):
    def store(self, content: bytes) -> str: ...
    def retrieve(self, content_hash: str) -> bytes: ...
    def exists(self, content_hash: str) -> bool: ...
    def delete(self, content_hash: str) -> bool: ...
```

In `retention/purge.py`:
```python
class PayloadStoreProtocol(Protocol):
    def exists(self, content_hash: str) -> bool: ...
    def delete(self, content_hash: str) -> bool: ...
```

The retention module defines a minimal protocol to "avoid circular imports", but this creates fragmentation. There should be one canonical protocol.

### Functionality Gaps

#### FG-4: No Size Tracking
**File:Line:** `payload_store.py:108-118`
**Severity:** Low

The store method doesn't return or track content size:
```python
def store(self, content: bytes) -> str:
    content_hash = hashlib.sha256(content).hexdigest()
    # ... no size recorded
    return content_hash
```

This is noted in `purge.py:47-50` as a future compatibility concern but remains unimplemented.

#### FG-5: No Atomic Write Guarantee
**File:Line:** `payload_store.py:113-117`
**Severity:** Medium

```python
if not path.exists():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
```

This is not atomic. A crash during `write_bytes` leaves a partial file. Should use write-to-temp-then-rename pattern.

---

## 7. checkpoint/ - Checkpoint Storage and Recovery

**Location:** `src/elspeth/core/checkpoint/` (4 files, ~430 lines)

### Design Issues

#### DI-8: Hardcoded Compatibility Date
**File:Line:** `checkpoint/manager.py:202-233`
**Severity:** Medium

```python
def _validate_checkpoint_compatibility(self, checkpoint: Checkpoint) -> None:
    # Simple heuristic: if created_at before 2026-01-24, warn about incompatibility
    cutoff_date = datetime(2026, 1, 24, tzinfo=UTC)
```

This hardcodes a date for node ID format changes. Future format changes would require more date checks. Should use a version field instead.

### Functionality Gaps

#### FG-6: No Checkpoint Pruning Strategy
**File:Line:** `checkpoint/manager.py:186-200`
**Severity:** Low

```python
def delete_checkpoints(self, run_id: str) -> int:
    """Delete all checkpoints for a completed run."""
```

Checkpoints are only deleted on successful completion. There's no retention policy for:
- Failed runs with many checkpoints
- Orphaned checkpoints from runs that were abandoned
- Disk space management

### Wiring Problems

#### WP-2: Resume Requires Schema Class from Caller
**File:Line:** `checkpoint/recovery.py:133-226`
**Severity:** High

```python
def get_unprocessed_row_data(
    self,
    run_id: str,
    payload_store: PayloadStore,
    *,
    source_schema_class: type[PluginSchema],
) -> list[tuple[str, int, dict[str, Any]]]:
```

The recovery manager requires the caller to provide the source schema class. This creates a coupling issue:
- The schema must be identical to the original run
- There's no verification that the provided schema matches the original
- Silent data loss if wrong schema is provided

---

## 8. rate_limit/ - Token Bucket Rate Limiting

**Location:** `src/elspeth/core/rate_limit/` (3 files, ~250 lines)

### Wiring Problems

#### WP-3: Rate Limiting Not Connected to Engine
**File:Line:** N/A (missing wiring)
**Severity:** Critical

The rate limiting subsystem is completely implemented but never used:

1. `RateLimitSettings` is defined in config.py
2. `RateLimitRegistry` is implemented
3. BUT: There is no import or usage of `RateLimitRegistry` in the engine (`src/elspeth/engine/`)

```bash
# Search for RateLimitRegistry usage in engine:
grep -r "RateLimitRegistry" src/elspeth/engine/
# Result: No matches found
```

**Impact:** Rate limiting configuration in settings.yaml has no effect. External API calls are not rate limited despite configuration.

### Design Issues

#### DI-9: Global Thread Exception Hook Modification
**File:Line:** `rate_limit/limiter.py:27-75`
**Severity:** Medium

```python
# Track original thread excepthook
_original_excepthook = threading.excepthook

# ...

# Install custom excepthook
threading.excepthook = _custom_excepthook
```

This modifies global thread exception handling at module import time. This can interfere with:
- Other libraries that also override excepthook
- Test frameworks that rely on exception propagation
- Debugging tools

#### DI-10: Race Condition in Bucket Check
**File:Line:** `rate_limit/limiter.py:223-271`
**Severity:** Low

The `try_acquire` method has a TOCTOU (time-of-check-time-of-use) pattern:
```python
def try_acquire(self, weight: int = 1) -> bool:
    with self._lock:
        # First check if ALL buckets would accept (peek without consuming)
        if not self._would_all_buckets_accept(weight):
            return False

        # All buckets would accept, now actually acquire from all limiters
        # Since we checked capacity, these should all succeed
        for limiter in self._limiters:
            # ...
            limiter.try_acquire(self.name, weight=weight)
```

Between the check and the acquire, another thread could consume tokens (the lock only protects within this RateLimiter instance, not across processes with SQLite persistence).

---

## 9. retention/ - Data Retention Policy

**Location:** `src/elspeth/core/retention/` (2 files, ~315 lines)

### Functionality Gaps

#### FG-7: No Cross-Run Payload Reference Counting
**File:Line:** `retention/purge.py:120-270`
**Severity:** High

The current implementation uses set difference to find safe-to-delete refs:
```python
# Return refs that are ONLY in expired runs (not in any active run)
safe_to_delete = expired_refs - active_refs
return list(safe_to_delete)
```

This is correct but has a subtle issue: if a resume operation occurs between `find_expired_payload_refs()` and `purge_payloads()`, a payload could become "active" again and be incorrectly deleted.

**Impact:** Potential audit trail corruption during concurrent resume + purge operations.

#### FG-8: No Dry-Run Mode
**File:Line:** `retention/purge.py:272-313`
**Severity:** Low

The `purge_payloads` method immediately deletes without a preview option. Users cannot see what would be deleted before committing.

---

## 10. security/ - Secret Handling

**Location:** `src/elspeth/core/security/` (2 files, ~145 lines)

### Design Issues

#### DI-11: Key Vault Secret Caching Missing
**File:Line:** `security/fingerprint.py:58-99`
**Severity:** Medium

```python
def get_fingerprint_key() -> bytes:
    # Priority 2: Azure Key Vault
    vault_url = os.environ.get(_KEYVAULT_URL_VAR)
    if vault_url:
        # ... fetches from Key Vault on every call
        client = _get_keyvault_client(vault_url)
        secret = client.get_secret(secret_name)
```

Every call to `get_fingerprint_key()` makes a network request to Key Vault. For high-volume pipelines, this could:
- Hit Key Vault rate limits
- Add latency to every secret fingerprint operation
- Fail if network is intermittent

### Security Concerns

#### SC-1: Fingerprint Key in Memory
**File:Line:** `security/fingerprint.py:76-79`
**Severity:** Low

```python
env_key = os.environ.get(_ENV_VAR)
if env_key:
    return env_key.encode("utf-8")
```

The fingerprint key is kept as a plain bytes object. For high-security deployments, consider using:
- Memory protection (mlock)
- Key zeroing after use
- Hardware security module integration

---

## Summary of Critical Issues

| ID | Severity | Component | Issue |
|----|----------|-----------|-------|
| WP-3 | Critical | rate_limit | Rate limiting not connected to engine |
| DI-7 | Critical | payload_store | Duplicate PayloadStore protocols |
| OG-2 | High | logging | OpenTelemetry advertised but not implemented |
| WP-2 | High | checkpoint | Resume requires external schema without verification |
| FG-7 | High | retention | Race condition in purge during concurrent resume |
| DI-3 | High | canonical | repr_hash undermines audit integrity |

---

## Recommendations

1. **Immediate:** Wire RateLimitRegistry into the engine orchestrator and plugin context
2. **Immediate:** Consolidate PayloadStore protocols into single definition
3. **Short-term:** Implement OpenTelemetry tracer configuration or remove claims from docstrings
4. **Short-term:** Add transactional semantics to purge operations
5. **Medium-term:** Add graph serialization for debugging and verification
6. **Medium-term:** Add checkpoint version field instead of hardcoded dates

---

## Confidence Assessment

**Confidence:** High

Evidence:
- Read all 6 main files (config.py, canonical.py, dag.py, events.py, logging.py, payload_store.py) completely
- Read all 4 checkpoint files (manager.py, recovery.py, compatibility.py, __init__.py)
- Read all 3 rate_limit files (limiter.py, registry.py, __init__.py)
- Read all 2 retention files (purge.py, __init__.py)
- Read all 2 security files (fingerprint.py, __init__.py)
- Cross-verified wiring by searching for usage patterns across the codebase
- Confirmed rate limiting disconnection via grep showing no engine imports

---

## Information Gaps

1. **Engine integration details:** Did not read full orchestrator to verify rate limit wiring gap
2. **Test coverage:** Did not analyze tests to understand which issues have test coverage
3. **CLI integration:** Only spot-checked CLI usage of retention/purge
4. **Landscape subsystem:** Did not analyze core/landscape/ (separate subsystem)
