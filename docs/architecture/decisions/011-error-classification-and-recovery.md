# ADR-011 – Error Classification & Recovery Strategy

## Status

**DRAFT** (2025-10-26)

**Priority**: P1 (Next Sprint)

## Context

Elspeth orchestrates complex pipelines involving datasources, LLM transforms, sinks, and middleware. Each component can fail in different ways with different recovery strategies:
- **Transient failures**: Network timeouts, rate limits (should retry)
- **Permanent failures**: Schema mismatches, validation errors (should skip or abort)
- **Security failures**: Clearance violations, missing credentials (must abort)
- **Resource failures**: Disk full, memory exhausted (system-level)

ADR-006 "Security-Critical Exceptions" defines security error handling (`SecurityCriticalError` vs `SecurityValidationError`), but **non-security error handling remains fragmented**. The `on_error` policy exists (`abort|skip|log`) but semantics are not formalized:
- What does "skip" mean for datasources vs transforms vs sinks?
- When to retry vs skip vs abort?
- How many retries before giving up?
- What state is checkpointed for resume?

### Current State Problems

**Problem 1: Inconsistent Error Handling**
- Datasource failures: Some retry, some abort, some skip
- LLM failures: Rate limits sometimes retried, sometimes not
- Sink failures: Disk full behavior varies by sink implementation
- No unified error classification

**Problem 2: Undefined `on_error` Semantics**
```yaml
datasource:
  type: csv_local
  on_error: skip   # Skip what? Entire datasource? Individual rows? Unclear.

llm:
  type: azure_openai
  on_error: abort  # Abort on rate limit? Timeout? Bad JSON? All?

sink:
  type: excel_file
  on_error: log    # Log and continue? Log and skip? Undefined.
```

**Problem 3: No Retry Strategy**
- Which errors should retry? (Transient vs permanent)
- How many retries? (Max attempts, exponential backoff)
- When to give up? (Retry budget exhausted)

**Problem 4: Checkpoint Recovery Undocumented**
- Checkpoint recovery exists (`src/elspeth/core/experiments/runner.py:75-280`)
- Behavior: Resume from last successful item, skip previously processed identifiers
- **But**: Not architecturally documented, not formalized

### Resilience as Core Principle

**ADR-001 Priority #3**: Availability – Keep orchestration reliable and recoverable

> "Keep orchestration reliable and recoverable (checkpointing, retries, graceful failure), subject to security/integrity constraints."

Resilience is **non-negotiable** but currently underdefined.

## Decision

We will establish a **comprehensive error classification taxonomy** and **recovery strategy** that provides predictable, resilient behavior across all pipeline components.

---

## Part 1: Error Classification Taxonomy

### Error Categories

#### 1. Security Errors (Covered by ADR-006)

**Characteristics**:
- Clearance violations, authentication failures, missing credentials
- **MUST fail-closed** (ADR-001 security-first)
- **NO retry** (security policy, not transient failure)
- **NO skip** (security cannot be bypassed)

**Exception Types**:
- `SecurityCriticalError`: Invariant violations (fail-loud, escalate)
- `SecurityValidationError`: Expected security checks (fail-graceful, audit)

**Handling**: Abort immediately, audit log failure

**Example**:
```python
# ADR-006: Security error handling
if data.classification > sink.security_level:
    raise SecurityValidationError(
        f"Sink lacks clearance for {data.classification} data"
    )
# Result: Pipeline aborts, audit logged, NO retry
```

---

#### 2. Transient Errors (Retry-able)

**Characteristics**:
- Temporary infrastructure issues
- Likely to succeed on retry
- Not caused by bad data or configuration

**Error Types**:
- **Network timeouts**: Socket timeout, connection refused
- **Rate limits**: HTTP 429 (Azure OpenAI, external APIs)
- **Temporary unavailability**: HTTP 503 (service temporarily down)
- **Resource contention**: Database deadlock, file lock

**Handling**: Retry with exponential backoff

**Configuration**:

```yaml
llm:
  type: azure_openai
  on_error: retry
  retry:
    max_attempts: 4         # explicit budget
    backoff: exponential    # 1s, 2s, 4s, 8s
    jitter: 0.2             # ±20% jitter to avoid thundering herd
```

**Example**:
```python
# Transient error: Network timeout
try:
    response = llm_client.complete(prompt)
except requests.Timeout:
    # Retry with backoff
    retry_with_backoff(llm_client.complete, prompt)
```

**Retry Strategy**:
- Max attempts: 3-5 (configurable)
- Backoff: Exponential (1s, 2s, 4s, 8s)
- Jitter: ±20% randomization (prevent thundering herd)

---

#### 3. Permanent Errors (Skip-able)

**Characteristics**:
- Bad data or configuration
- Will NOT succeed on retry
- Isolated to specific item (row, experiment)

**Error Types**:
- **Schema mismatch**: Missing column, wrong type
- **Validation failure**: Regex mismatch, constraint violation
- **Parse error**: Malformed JSON, invalid CSV
- **Business rule violation**: Invalid state, constraint check

**Handling**: Skip item, log error, continue

**Example**:
```python
# Permanent error: Schema mismatch
try:
    datasource.load_row(row)
except SchemaValidationError as exc:
    logger.warning(f"Skipping row {row.id}: {exc}")
    continue  # Skip this row, process next
```

**Skip Semantics** (by component):
- **Datasource**: Skip row, continue to next row
- **Transform**: Skip item, pass NULL result downstream
- **Sink**: Skip item, do not write this item

Transform implementations that return `None` must still emit an explicit
`SkipResult` structure so downstream sinks can distinguish between "no output"
and "error". The standardized wrapper will convert `None` into the skip signal
and log the failure once, avoiding duplicated error handling in sinks.

#### SkipResult Protocol Specification

**Purpose**: Distinguish between "no output" (intentional) and "error occurred, skipping item" (failure with context).

**Protocol Definition**:
```python
from dataclasses import dataclass
from typing import Protocol

@dataclass
class SkipResult:
    """Indicates item was skipped due to error (not empty result).

    Attributes:
        item_id: Identifier for the skipped item (row ID, experiment ID)
        reason: Human-readable skip reason (e.g., "schema_mismatch", "rate_limit_exceeded")
        error: Original exception (if available) for debugging
        component: Component that initiated skip (datasource/transform/sink)
        retry_count: Number of retry attempts before skip (0 if not retried)
    """
    item_id: str
    reason: str
    error: Exception | None = None
    component: str = "unknown"
    retry_count: int = 0
```

**Transform Usage Example**:
```python
class CustomLLMTransform(BasePlugin, Transform):
    """Transform with skip-on-error handling."""

    def transform(self, item: dict) -> dict | SkipResult:
        """Transform item, skip on schema mismatch."""
        try:
            # Validate schema
            if "prompt" not in item:
                return SkipResult(
                    item_id=item.get("id", "unknown"),
                    reason="missing_required_field",
                    component="CustomLLMTransform",
                )

            # Perform transformation
            result = self._call_llm(item["prompt"])
            return {"result": result, "id": item["id"]}

        except requests.Timeout as exc:
            # Transient error after retries exhausted
            return SkipResult(
                item_id=item.get("id", "unknown"),
                reason="timeout_after_retries",
                error=exc,
                component="CustomLLMTransform",
                retry_count=self.config.get("max_retries", 3),
            )
```

**Sink Usage Example**:
```python
class CustomSink(BasePlugin, ResultSink):
    """Sink that handles SkipResult properly."""

    def write(self, item: dict | SkipResult) -> None:
        """Write item, skip SkipResult instances."""
        if isinstance(item, SkipResult):
            # Log skip but don't write
            self.logger.warning(
                f"Skipping item {item.item_id}: {item.reason}",
                extra={
                    "item_id": item.item_id,
                    "skip_reason": item.reason,
                    "component": item.component,
                    "retry_count": item.retry_count,
                }
            )
            return  # Don't write to output

        # Normal write path
        self._write_to_file(item)
```

**Semantics**:
- **`None` return**: Intentional empty result (e.g., filter excluded item)
- **`SkipResult` return**: Error occurred, item skipped with context
- **Exception raised**: Propagate error to `on_error` policy handler

**Audit Logging**:
All `SkipResult` instances are logged to audit trail with full context:
```json
{
  "event": "item_skipped",
  "item_id": "row_123",
  "reason": "schema_mismatch",
  "component": "CustomLLMTransform",
  "retry_count": 0,
  "timestamp": "2025-10-26T14:30:00Z"
}
```

---

#### 4. Fatal Errors (Abort-able)

**Characteristics**:
- System-level failures
- Cannot be recovered without external intervention
- Affect entire pipeline (not isolated to item)

**Error Types**:
- **Disk full**: Cannot write outputs
- **Out of memory**: System resource exhausted
- **Permission denied**: Missing file system access
- **Configuration invalid**: Missing required config field
- **Dependency missing**: Required module not installed

**Handling**: Abort pipeline, emit error, require user intervention

**Example**:
```python
# Fatal error: Disk full
try:
    sink.write_file(artifact)
except OSError as exc:
    if exc.errno == errno.ENOSPC:  # No space left on device
        raise FatalError("Disk full, cannot write outputs") from exc
# Result: Pipeline aborts, user must free disk space
```

**Abort Semantics**:
- Stop pipeline execution immediately
- Emit error to user
- Preserve checkpoints (enable resume after fix)
- Do NOT retry (requires external intervention)

---

### Error Classification Matrix

| `on_error` Policy | Error Category          | Default Action                 |
|-------------------|------------------------|--------------------------------|
| `abort`           | Security / Fatal       | Abort pipeline immediately     |
| `retry`           | Transient              | Retry using configured budget  |
| `skip`            | Permanent              | Skip item, log once, continue  |
| `log`             | Permanent (non-block)  | Log and continue (transform-only)|

Policies are resolved per component. If configuration omits `on_error`, the
system selects a safe default (`retry` for datasources/LLMs, `abort` for sinks,
`abort` for security errors). Overrides must be explicit in YAML/JSON config.

| Error Type | Example | Retry? | Skip? | Abort? | Checkpoint? |
|------------|---------|--------|-------|--------|-------------|
| **Security** | Clearance violation | ❌ | ❌ | ✅ | ✅ (audit) |
| **Transient** | Network timeout | ✅ (3-5x) | ❌ | After retries | ✅ |
| **Permanent** | Schema mismatch | ❌ | ✅ | On policy | ✅ (item) |
| **Fatal** | Disk full | ❌ | ❌ | ✅ | ✅ (state) |

---

## Part 2: `on_error` Policy Semantics

### Policy Options

#### Policy 1: `abort` (Fail-Fast)

**Behavior**: Stop pipeline on first error

**Use Cases**:
- Production pipelines (zero tolerance for errors)
- Security-critical data (ADR-001 priority #1)
- Data integrity requirements (ADR-001 priority #2)

**Semantics by Component**:
- **Datasource**: Abort on first row error
- **Transform**: Abort on first item error
- **Sink**: Abort on first write error

**Example**:
```yaml
datasource:
  type: csv_local
  on_error: abort  # Abort on first row error

# Result: First schema mismatch → pipeline aborts
```

**Rationale**: Fail-fast prevents cascading errors, preserves data integrity

---

#### Policy 2: `skip` (Continue on Error)

**Behavior**: Skip failed item, log error, continue

**Use Cases**:
- Exploratory data analysis (tolerate some errors)
- Best-effort processing (partial results acceptable)
- High-volume pipelines (some loss tolerable)

**Semantics by Component**:
- **Datasource**: Skip row, continue to next row
- **Transform**: Skip item, pass NULL result (or omit from output)
- **Sink**: Skip item, do not write this item

**Example**:
```yaml
datasource:
  type: csv_local
  on_error: skip  # Skip invalid rows

# Result: Schema mismatch → skip row, log warning, continue
```

**Rationale**: Partial results better than no results (availability > perfection)

---

#### Policy 3: `log` (DEPRECATED)

**Behavior**: Log error, continue without skip

**Status**: DEPRECATED (ambiguous semantics)

**Migration**: Use `skip` with audit logging

**Rationale**: "Log and continue" semantics unclear (what happens to failed item?)

---

### Policy Priority (Security Override)

**Security errors ALWAYS abort** regardless of `on_error` policy:

```yaml
datasource:
  type: csv_local
  on_error: skip  # Skip non-security errors

# Security error occurs (clearance violation)
# Result: ABORTS (security overrides on_error policy)
```

**Rationale**: ADR-001 priority #1 (Security) > priority #3 (Availability)

---

## Part 3: Retry Strategy

### Retry Decision Tree

```
Error occurs
   ↓
Is Security Error? → YES → Abort (no retry)
   ↓ NO
Is Transient Error? → NO → Permanent/Fatal → Skip or Abort
   ↓ YES
Retry count < max? → NO → Abort (retry budget exhausted)
   ↓ YES
Wait (exponential backoff + jitter)
   ↓
Retry operation
```

### Retry Configuration

**Per-Component Retry Budget**:
```yaml
llm:
  type: azure_openai
  retry:
    max_attempts: 5         # Max retry attempts
    backoff_base: 1.0       # Base delay (seconds)
    backoff_multiplier: 2.0 # Exponential multiplier
    backoff_jitter: 0.2     # Jitter (±20%)
    timeout: 30.0           # Per-attempt timeout
```

**Backoff Calculation**:
```python
def calculate_backoff(attempt: int, base: float, multiplier: float, jitter: float) -> float:
    """Exponential backoff with jitter."""
    delay = base * (multiplier ** attempt)
    jitter_amount = delay * jitter * (2 * random.random() - 1)  # ±jitter%
    return delay + jitter_amount

# Example: attempt=3, base=1.0, multiplier=2.0, jitter=0.2
# delay = 1.0 * (2.0 ** 3) = 8.0
# jitter = 8.0 * 0.2 * (rand(-1, 1)) = ±1.6
# Result: 6.4s to 9.6s (random)
```

**Retry Budget Exhaustion**:
- After max_attempts, treat as fatal error
- Emit error with retry history (attempted N times, delays: [1s, 2s, 4s])
- Checkpoint state for manual intervention

---

## Part 4: Checkpoint Recovery

### Checkpoint Strategy

**Checkpoint Granularity**:
- **Row-level**: Datasource processing (skip processed rows on resume)
- **Item-level**: Transform processing (skip processed items)
- **Experiment-level**: Suite runner (skip completed experiments)

**Checkpoint Format**:
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "checkpoint_time": "2025-10-26T14:30:00Z",
  "processed_items": [
    {"id": "row_001", "status": "success"},
    {"id": "row_002", "status": "success"},
    {"id": "row_003", "status": "failed", "error": "schema_mismatch"}
  ],
  "resume_from": "row_004"
}
```

**Resume Behavior**:
1. Load checkpoint (if exists)
2. Skip processed items (status: "success")
3. Retry failed items (status: "failed") if on_error=skip
4. Continue from resume_from

**Example** (resume after network failure):
```python
# Initial run: Process rows 1-50, network timeout at row 51
# Checkpoint: {"processed_items": [1-50], "resume_from": 51}

# Resume:
checkpoint = load_checkpoint(run_id)
for row_id in datasource.rows():
    if row_id in checkpoint.processed_items:
        continue  # Skip already processed
    process_row(row_id)
```

**Checkpoint Cleanup**:
- Successful runs: Delete checkpoint
- Failed runs: Preserve checkpoint for resume
- Retention: 7 days (configurable)

---

## Part 5: Error Context & Observability

### Error Metadata

**All errors include**:
- `error_type`: Security, Transient, Permanent, Fatal
- `component`: Datasource, Transform, Sink
- `item_id`: Row ID, experiment ID (if applicable)
- `retry_count`: Number of retry attempts
- `timestamp`: When error occurred
- `stack_trace`: Full traceback (debug mode)

**Example**:
```json
{
  "error_type": "Transient",
  "error_class": "requests.Timeout",
  "component": "AzureOpenAIClient",
  "item_id": "row_123",
  "retry_count": 3,
  "timestamp": "2025-10-26T14:30:00Z",
  "message": "Request timeout after 30s",
  "will_retry": true,
  "backoff_delay": 8.0
}
```

### Audit Logging

**All errors logged to audit trail** (`logs/run_*.jsonl`):
- Security errors: Full context, audit trail
- Transient errors: Retry attempts, delays
- Permanent errors: Skipped items, reasons
- Fatal errors: System state, intervention required

**Correlation IDs**: Propagate through pipeline for tracing

---

## Consequences

### Benefits

1. **Predictable Behavior**: Error handling consistent across components
2. **Resilience**: Retry strategy handles transient failures (ADR-001 priority #3)
3. **Debuggability**: Clear error classification aids troubleshooting
4. **Resumability**: Checkpoint recovery prevents re-processing
5. **Security**: Security errors always abort (ADR-001 priority #1)
6. **Observability**: Error metadata enables monitoring

### Limitations / Trade-offs

1. **Complexity**: Error taxonomy adds conceptual overhead
   - *Mitigation*: Clear documentation, examples for each error type

2. **Retry Latency**: Exponential backoff adds pipeline latency
   - *Mitigation*: Configurable retry budget, users control trade-off

3. **Checkpoint Storage**: Checkpoints consume disk space
   - *Mitigation*: Automatic cleanup after 7 days

4. **"Skip" Ambiguity**: Users may confuse skip semantics
   - *Mitigation*: Clear documentation, validation errors explain skip behavior

5. **No Partial Item Recovery**: Failed item retried from scratch
   - *Mitigation*: Intentional (stateless, reproducible), acceptable trade-off

### Future Enhancements (Post-1.0)

1. **Circuit Breaker**: Stop retrying after N consecutive failures
2. **Adaptive Retry**: Adjust backoff based on error pattern
3. **Dead Letter Queue**: Store failed items for manual review
4. **Error Aggregation**: Batch similar errors for debugging
5. **Retry Budget Sharing**: Share retry budget across pipeline

### Implementation Checklist

**Phase 1: Core Taxonomy** (P1, 3-4 hours):
- [ ] Define exception hierarchy (Transient, Permanent, Fatal)
- [ ] Implement retry logic with exponential backoff
- [ ] Formalize `on_error` semantics (abort/skip)
- [ ] Update error messages with error type

**Phase 2: Checkpoint Enhancement** (P1, 1-2 hours):
- [ ] Document checkpoint recovery architecture
- [ ] Add checkpoint cleanup (7-day retention)
- [ ] Emit checkpoint events to audit log

**Phase 3: Observability** (P1, 1 hour):
- [ ] Add error metadata (type, component, retry_count)
- [ ] Correlation ID propagation
- [ ] Error aggregation dashboard (post-1.0)

### Related ADRs

- **ADR-001**: Design Philosophy – Security-first, fail-closed, availability priority #3
- **ADR-005**: Security-Critical Exceptions – Security error taxonomy (extends this ADR)
- **ADR-008**: Configuration Composition – Configuration error handling
- **ADR-012**: Global Observability Policy – Audit logging requirements

### Implementation References

- `src/elspeth/core/errors.py` – Error taxonomy (to be created)
- `src/elspeth/core/experiments/runner.py:75-280` – Checkpoint recovery (existing)
- `src/elspeth/core/retry.py` – Retry manager (to be created)
- `src/elspeth/core/base/plugin.py` – Plugin error handling hooks

---

**Document Status**: DRAFT – Requires review and acceptance
**Next Steps**:
1. Review with team (error taxonomy approval)
2. Implement exception hierarchy
3. Add retry manager with exponential backoff
4. Update plugin authoring guide with error handling patterns
