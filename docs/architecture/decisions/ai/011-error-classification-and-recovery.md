# ADR-011 – Error Classification and Recovery (LITE)

## Status

**DRAFT** (2025-10-26)

## Context

Elspeth processes 100s-1000s of rows. Errors occur: network timeouts, rate limits, malformed responses. Need consistent error handling strategy across all plugins.

**Problems**:
- Ad-hoc error handling (each plugin different)
- No retry strategy (fail immediately or retry forever?)
- Unclear which errors are transient vs permanent
- Pipeline aborts on single error (poor availability)

## Decision

Implement **Error Classification** with standardized recovery strategies.

### Error Taxonomy

```python
class ErrorType(Enum):
    TRANSIENT = "transient"      # Retry likely succeeds (network, rate limit)
    PERMANENT = "permanent"      # Retry won't help (malformed data, auth)
    SECURITY = "security"        # Security violation (ADR-006)
```

### Classification Examples

| Error | Type | Retry? | Example |
|-------|------|--------|---------|
| Network timeout | TRANSIENT | ✅ Yes | `requests.Timeout` |
| Rate limit | TRANSIENT | ✅ Yes | HTTP 429 |
| Auth failure | PERMANENT | ❌ No | HTTP 401 |
| Malformed data | PERMANENT | ❌ No | JSON decode error |
| Clearance violation | SECURITY | ❌ Abort | ADR-002 violation |

### Recovery Strategies

**Transient Errors** - Retry with exponential backoff:
```python
def process_with_retry(item):
    """Retry transient errors up to max_attempts."""
    max_attempts = 3
    backoff_ms = 1000

    for attempt in range(max_attempts):
        try:
            return process(item)
        except TransientError as e:
            if attempt == max_attempts - 1:
                raise  # Exhausted retries
            time.sleep(backoff_ms / 1000)
            backoff_ms *= 2  # Exponential backoff
```

**Permanent Errors** - Fail immediately:
```python
def process_item(item):
    """Process item, don't retry permanent errors."""
    try:
        return process(item)
    except PermanentError as e:
        raise  # No retry, fail immediately
```

**Security Errors** - Abort pipeline:
```python
def process_item(item):
    """Process item, abort on security violations."""
    try:
        return process(item)
    except SecurityCriticalError as e:
        # ❌ DO NOT CATCH (ADR-006)
        # Let propagate to platform termination
        raise
```

### Per-Plugin Error Policy

Plugins declare error handling via `on_error` policy:

```yaml
datasource:
  type: csv_local
  path: data.csv
  on_error: abort     # abort | skip | log

llm:
  type: azure_openai
  on_error: skip      # Skip failed items, continue

sinks:
  - type: csv_file
    on_error: abort   # Abort on write failures
```

**Policy Semantics**:
- `abort` - Raise exception, terminate pipeline (default for datasources/sinks)
- `skip` - Log error, skip item, continue (default for transforms)
- `log` - Log error, use fallback value, continue

### Error Context Propagation

```python
@dataclass
class ErrorContext:
    """Error context for debugging."""
    item_id: str
    plugin_name: str
    error_type: ErrorType
    attempt: int
    max_attempts: int
    traceback: str
    metadata: dict

# Logged to audit trail
audit_logger.log_error(ErrorContext(...))
```

## Consequences

### Benefits
- **Consistent handling** - All plugins use same taxonomy
- **Intelligent retry** - Transient errors retry, permanent don't
- **Pipeline resilience** - `skip` policy continues on errors
- **Security enforcement** - Security errors abort (ADR-006)

### Limitations
- **Classification burden** - Plugins must classify every error type
- **Retry overhead** - Exponential backoff adds latency
- **Partial results** - `skip` policy may produce incomplete datasets

### Mitigations
- **Default classification** - Common errors pre-classified
- **Max backoff** - Cap at 30 seconds
- **Result metadata** - Flag partial results for downstream

## Related

ADR-001 (Philosophy - fail-fast), ADR-006 (Security-critical exceptions), ADR-010 (Lifecycle)

---
**Last Updated**: 2025-10-26
