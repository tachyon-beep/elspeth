# ADR-013 – Global Observability Policy (LITE)

## Status

**DRAFT** (2025-10-26) | **Priority**: P1

## Context

Elspeth handles classified data → comprehensive audit trails required for compliance (PSPF, HIPAA, PCI-DSS, GDPR). Multiple observability mechanisms exist but not architecturally governed.

**Unanswered Questions**:
- What MUST be logged vs MAY?
- What MUST NOT be logged (PII, classified)?
- Retention periods?
- What happens when logging fails?

## Decision

Establish **Global Observability Policy** defining mandatory logging, PII handling, retention, failure modes.

## Part 1: Mandatory Logging Requirements

### Category 1: Security Events (MUST LOG)

**Events**:
- Authentication (login, token issuance/revocation)
- Authorization (access denied, clearance violations)
- Data Access (datasource loads, classified retrieval)
- Classification Changes (upgrades/downgrades)
- Security Validation Failures (ADR-002 violations)
- Configuration Changes (security-related)

**Log Fields**:
```json
{
  "event_type": "security_validation_failure",
  "timestamp": "2025-10-26T14:30:00Z",
  "correlation_id": "550e8400-...",
  "component": "ArtifactPipeline",
  "user_id": "user@example.com",
  "security_level_required": "SECRET",
  "security_level_actual": "CONFIDENTIAL",
  "action": "denied",
  "reason": "insufficient_clearance"
}
```

**Retention**: **90 days minimum** (compliance)
**Failure**: **Abort operation** (fail-closed, ADR-001)

### Category 2: Data Processing Events (MUST LOG)

**Events**:
- Datasource Loads (what, when, by whom)
- Transform Executions (LLM calls, middleware)
- Sink Writes (destination, format)
- Artifact Creation (signing if applicable)
- Pipeline Execution (start/end, duration, rows)

**Retention**: **90 days** (compliance), **12 months** for cost data
**Failure**: **Log warning, continue** (best-effort, availability > perfect observability)

### Category 3: Error Events (MUST LOG)

**Events**:
- All Exceptions (stack traces, context)
- Retry Attempts (transient errors, backoff)
- Checkpoint Failures
- Configuration Errors

**Retention**: **30 days** (operational)
**Failure**: **Best-effort**

### Category 4: Cost & Usage (MAY LOG)

**Events**:
- LLM Usage (tokens, model, cost)
- Storage Usage (blob operations)
- Compute Usage (execution time)

**Retention**: **12 months** (financial audit)
**Failure**: **Best-effort**

## Part 2: Sensitive Data Handling

### Critical Principle: Sink Clearance Enforced

**PII and classified content CAN be logged** because sink clearance is enforced at pipeline construction (Part 4).

**Security Model**:
- **MLS Enforcement**: Sink clearance validated at construction, mismatched sinks abort immediately
- **No Lower-Cleared Sinks**: Cannot connect UNOFFICIAL sink to SECRET pipeline (construction fails)
- **Data Minimization**: Scrubbing is operational choice (full vs metadata), not security requirement
- **Secrets**: NEVER log credentials (even to cleared sinks)

### Category 1: PII (MAY log to cleared sinks)

**Logging Matrix**:
| Content | Full Logging | Metadata-Only |
|---------|--------------|---------------|
| Names | ✅ Audit trail | ⚠️ user_id only |
| Emails | ✅ Debugging | ⚠️ user_id only |
| Phone/SSN/addresses | ⚠️ If critical | ✅ Omit |
| IP addresses | ✅ Security events | ⚠️ Scrub general logs |

**Scrubbing Recommendation**: Scrub PII even for cleared sinks (data minimization) unless operationally necessary.

### Category 2: Classified Content (MAY log to cleared sinks)

| Content | Full Logging | Metadata-Only |
|---------|--------------|---------------|
| Prompt content | ✅ Deep debugging | ⚠️ Length/template (saves 90%+ storage) |
| LLM responses | ✅ Audit | ⚠️ Status/length |
| Datasource content | ✅ Provenance | ⚠️ Schema/counts |
| Artifact payloads | ⚠️ Critical audit | ✅ Metadata (bundle captures payloads) |

### Category 3: Secrets (ALWAYS PROHIBITED)

**NEVER log**:
- API keys, tokens, passwords
- Encryption/signing keys
- Connection strings with credentials
- OAuth tokens
- Database passwords

**Example (correct)**:
```json
{
  "event_type": "azure_openai_configured",
  "api_key": "***REDACTED***",
  "key_length": 32,
  "key_rotation_date": "2025-10-01"
}
```

## Part 3: Correlation ID Propagation

### Three-Tier Hierarchy

**Tier 1: `run_id`** (Suite-Level)
- Scope: Entire experiment suite
- Format: `run_20251026_143000_550e8400`
- Generated: Suite runner start

**Tier 2: `experiment_id`** (Experiment-Level)
- Scope: Single experiment
- Format: `exp_baseline_comparison_abc123de`
- Parent: Links to `run_id`

**Tier 3: `item_id`** (Item-Level)
- Scope: Single row/item
- Format: `item_001`, `row_123`
- Parent: Links to `experiment_id`

**Propagation**:
```python
@dataclass
class PluginContext:
    run_id: str              # Tier 1
    experiment_id: str       # Tier 2
    item_id: str | None      # Tier 3 (optional)
    security_level: SecurityLevel
    audit_logger: AuditLogger
```

**HTTP Headers** (external systems):
```http
X-Elspeth-Run-ID: run_20251026_143000_550e8400
X-Elspeth-Experiment-ID: exp_baseline_comparison_abc123de
X-Elspeth-Item-ID: item_002
X-Request-ID: 550e8400-...
```

## Part 4: Log Sink Security

### Architectural Innovation: Logs Flow to Sinks

**Traditional** (insecure):
```python
# ❌ Direct file write - no clearance validation
with open(f"logs/run_{run_id}.jsonl", "a") as f:
    f.write(json.dumps(log_entry))
# Problem: Log file has no security level
```

**Elspeth** (secure):
```python
# ✅ Logs flow through artifact pipeline with clearance validation
audit_log = SecureAuditLog(
    security_level=pipeline.effective_level,  # Inherits from pipeline
    entries=[...],
)

# Route to sink with validated clearance
artifact_pipeline.route_artifact(audit_log.to_artifact(), sink=log_sink)

# Sink validation at construction (fail-fast)
if log_sink.security_level < audit_log.security_level:
    raise SecurityValidationError("Sink lacks clearance")
```

**Key Innovation**: Logs are security artifacts (same treatment as results). MLS enforcement prevents cross-level leakage structurally.

### Log Security Level Inheritance

**Critical Principle**: Logs are metadata about classified operations and inherit pipeline security level.

```python
# Audit log inherits pipeline effective level
pipeline_level = SecurityLevel.SECRET

audit_log = SecureAuditLog(
    security_level=pipeline_level,  # Inherits
    entries=[...],
)
# Even scrubbed logs (no payload) classified at pipeline level
```

### Log Sink Clearance Requirements

**Validation (fail-fast)**:
```python
def validate_log_sink_clearance(log: AuditLog, sink: ResultSink):
    if sink.security_level < log.security_level:
        raise SecurityValidationError(
            f"Log sink '{sink.name}' has insufficient clearance. "
            f"Required: {log.security_level}, Actual: {sink.security_level}."
        )
```

**Sink Selection Matrix**:
| Pipeline Level | Approved Log Sinks |
|----------------|-------------------|
| UNOFFICIAL | Local file, stdout |
| OFFICIAL | Azure Blob (restricted), AWS S3 (encrypted) |
| SECRET | Azure Blob (gov cloud), AWS GovCloud, on-prem secure |
| TOP SECRET | Air-gapped on-prem, HSM-backed |

## Part 5: Retention Policy

| Log Type | Retention | Rationale |
|----------|-----------|-----------|
| Security Events | **90 days** | Compliance minimum (PSPF, FedRAMP) |
| Data Processing | **90 days** | GDPR, provenance |
| Error Logs | **30 days** | Operational debugging |
| Cost/Usage | **12 months** | Financial audit |
| Performance | **30 days** | Operational monitoring |

**Cleanup**: Daily cron job deletes logs older than retention period.

## Part 6: Failure Handling

### Scenario 1: Audit Logging Fails (Security)

**Policy**: **Abort operation** (fail-closed, ADR-001)

```python
try:
    audit_logger.log_security_event("clearance_violation", ...)
except Exception as exc:
    raise SecurityCriticalError("Audit logging failed, aborting") from exc
```

### Scenario 2: Performance Logging Fails (Non-Security)

**Policy**: **Log warning, continue** (best-effort)

```python
try:
    telemetry_logger.log_performance("llm_latency", ...)
except Exception as exc:
    logger.warning(f"Telemetry failed: {exc}")
    # Continue pipeline
```

## Consequences

### Benefits
- **Compliance-ready** - Audit trail meets regulatory requirements
- **Security visibility** - All security events logged
- **Debuggability** - Correlation IDs enable tracing
- **PII protection** - Secrets never logged
- **Fail-closed** - Audit failures abort (security-first)
- **MLS enforcement** - Log sinks validated like result sinks

### Limitations
- **Logging overhead** - ~5-10ms per event
- **Storage costs** - 90-day retention consumes disk
- **PII scrubbing complexity** - Regex may miss edge cases
- **Fail-closed impact** - Audit failure aborts pipeline (intentional)

### Mitigations
- **Async logging** - Buffered writes
- **Compression** - Reduce size 60-80%
- **Allowlist approach** - Only log approved fields
- **Intentional** - Security > availability (ADR-001)

## Related

ADR-001 (Philosophy), ADR-002 (MLS), ADR-002-A (Trusted container), ADR-007 (Dual-output)

---
**Last Updated**: 2025-10-26
