# ADR 012 – Global Observability Policy

## Status

**DRAFT** (2025-10-26)

**Priority**: P1 (Next Sprint)

## Context

Elspeth handles classified data and must provide comprehensive audit trails for compliance, security visibility, and operational monitoring. Multiple observability mechanisms exist:
- **Audit logging** (`docs/architecture/audit-logging.md`) – Security events, data access
- **Telemetry middleware** (Azure ML integration) – Performance metrics, cost tracking
- **Health monitoring** middleware – Component health, dependency status
- **Cost tracking** – LLM usage, storage costs

These mechanisms are **implemented and working**, but **not architecturally governed**. Key questions remain unanswered:
- What MUST be logged vs MAY be logged?
- What MUST NOT be logged (PII, classified content)?
- How long are logs retained?
- What correlation IDs propagate through the system?
- What happens when logging fails?

### Current State

**Implemented and Working**:
- ✅ Audit logging (`src/elspeth/core/security/audit.py`)
- ✅ Telemetry middleware (Azure ML)
- ✅ Health monitoring middleware
- ✅ Cost tracking (LLM usage)
- ✅ Correlation ID propagation (partial)

**Problems**:
1. **No Global Policy**: What to log decided ad-hoc per component
2. **Inconsistent PII Handling**: Some logs scrub PII, some don't
3. **Undefined Retention**: Log retention varies by implementation
4. **Logging Failures**: What happens if audit logging fails? Undefined.
5. **Environment-Specific**: Observability is environment-specific (Azure vs local) but no global policy

### Compliance Requirements

**Audit Trail Obligations**:
- Government classifications: PSPF (Australian), FedRAMP (US)
- Healthcare: HIPAA audit trail (access logs, data modification)
- Finance: PCI-DSS audit logs (cardholder data access)
- General: GDPR right to access (data processing logs)

**Retention Requirements**:
- Security events: 90 days minimum (compliance)
- Performance metrics: 30 days (operational)
- Cost data: 12 months (financial audit)

### Dual Architecture Requirement

> "Observability was originally left to middleware as it's environment specific, but all 'global observability questions' should be centralised in an ADR."

**Requirement**: Separate **policy** (global, this ADR) from **implementation** (environment-specific, middleware).

## Decision

We will establish a **Global Observability Policy** that defines:
1. What MUST be logged (required for compliance)
2. What MUST NOT be logged (PII, classified content)
3. Retention policy requirements
4. Correlation ID propagation rules
5. Failure handling (what happens when logging fails)

**Implementation** (environment-specific) remains in middleware (Azure ML telemetry, generic audit logger, health monitoring).

---

## Part 1: Mandatory Logging Requirements

### Category 1: Security Events (MUST LOG)

**Purpose**: Audit trail for security compliance, incident response

**Events**:
- **Authentication**: Login attempts, token issuance/revocation
- **Authorization**: Access denied (clearance violations), permission checks
- **Data Access**: Datasource loads, classified data retrieval
- **Classification Changes**: Security level upgrades/downgrades
- **Security Validation Failures**: ADR-002 clearance violations, ADR-004 plugin validation failures
- **Configuration Changes**: Security-related config modifications

**Log Fields** (minimum):
```json
{
  "event_type": "security_validation_failure",
  "timestamp": "2025-10-26T14:30:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "component": "ArtifactPipeline",
  "user_id": "user@example.com",
  "resource": "classified_dataframe",
  "security_level_required": "SECRET",
  "security_level_actual": "CONFIDENTIAL",
  "action": "denied",
  "reason": "insufficient_clearance"
}
```

**Retention**: **90 days minimum** (compliance requirement)

**Failure Handling**: **Abort operation** if audit logging fails (fail-closed, ADR-001)

---

### Category 2: Data Processing Events (MUST LOG)

**Purpose**: Provenance, reproducibility, compliance (GDPR right to access)

**Events**:
- **Datasource Loads**: Which data retrieved, when, by whom
- **Transform Executions**: LLM calls, middleware processing
- **Sink Writes**: Where data written, format, destination
- **Artifact Creation**: Artifact generation, signing (if applicable)
- **Pipeline Execution**: Start/end, duration, row count

**Log Fields** (minimum):
```json
{
  "event_type": "datasource_load",
  "timestamp": "2025-10-26T14:30:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "run_20251026_143000",
  "component": "CsvLocalDataSource",
  "datasource_type": "csv_local",
  "file_path": "/data/classified_data.csv",
  "row_count": 1000,
  "security_level": "OFFICIAL",
  "duration_ms": 150
}
```

**Retention**: **90 days** (compliance), **12 months** for cost data

**Failure Handling**: **Log warning, continue** (best-effort, availability over perfect observability)

---

### Category 3: Error Events (MUST LOG)

**Purpose**: Debugging, incident response, reliability monitoring

**Events**:
- **All Exceptions**: Stack traces, error context
- **Retry Attempts**: Transient errors, retry count, backoff delays
- **Checkpoint Failures**: Checkpoint save/load errors
- **Configuration Errors**: Validation failures, merge errors

**Log Fields** (minimum):
```json
{
  "event_type": "exception",
  "timestamp": "2025-10-26T14:30:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "error_type": "Transient",
  "error_class": "requests.Timeout",
  "component": "AzureOpenAIClient",
  "item_id": "row_123",
  "retry_count": 3,
  "message": "Request timeout after 30s",
  "stack_trace": "..."
}
```

**Retention**: **30 days** (operational monitoring)

**Failure Handling**: **Log warning, continue** (best-effort)

---

### Category 4: Cost & Usage (MAY LOG)

**Purpose**: Financial audit, cost optimization

**Events**:
- **LLM Usage**: Tokens consumed, model, cost
- **Storage Usage**: Blob storage operations, cost
- **Compute Usage**: Pipeline execution time, resource utilization

**Log Fields** (minimum):
```json
{
  "event_type": "llm_usage",
  "timestamp": "2025-10-26T14:30:00Z",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "gpt-4",
  "prompt_tokens": 500,
  "completion_tokens": 200,
  "total_tokens": 700,
  "cost_usd": 0.014
}
```

**Retention**: **12 months** (financial audit)

**Failure Handling**: **Best-effort** (cost tracking should not block pipeline)

---

## Part 2: Prohibited Logging (MUST NOT LOG)

### Prohibited Content

To prevent PII leakage and classified data exposure:

#### 1. PII (Personally Identifiable Information)

**MUST NOT log**:
- Full names (unless necessary for audit trail)
- Email addresses (log user ID instead)
- Phone numbers, addresses, SSNs
- IP addresses (unless security event)

**Exception**: User ID for audit trail (authenticated identity)

---

#### 2. Classified Content

**MUST NOT log**:
- **Prompt content**: Only log metadata (length, model, template name)
- **LLM responses**: Only log metadata (length, status, latency)
- **Datasource content**: Only log schema, row count, security level
- **Artifact payloads**: Only log artifact ID, type, size

**Log metadata instead**:
```json
{
  "event_type": "llm_call",
  "correlation_id": "...",
  "prompt_length": 500,
  "prompt_template": "summarization",
  "model": "gpt-4",
  "response_length": 200,
  "response_status": "success",
  "latency_ms": 1500
  // ❌ NO "prompt" or "response" fields
}
```

**Rationale**: Logging classified content creates additional classified data stores, violates data minimization.

---

#### 3. Secrets & Credentials

**MUST NOT log**:
- API keys, tokens, passwords
- Encryption keys, signing keys
- Connection strings with embedded credentials
- OAuth tokens, refresh tokens

**Log placeholder instead**:
```json
{
  "azure_openai_endpoint": "https://example.openai.azure.com",
  "api_key": "***REDACTED***"  // ✅ Redacted
}
```

**Rationale**: Credentials in logs create security vulnerabilities.

---

### Sensitive Data Scrubbing

**All logs MUST be scrubbed** before persistence:
1. **Regex-based scrubbing**: Remove API keys, emails, SSNs
2. **Field allowlist**: Only log approved fields
3. **Length limits**: Truncate long fields (prevent log injection)

**Example**:
```python
def scrub_log_entry(entry: dict) -> dict:
    """Scrub sensitive data from log entry."""
    # Redact known sensitive fields
    if "api_key" in entry:
        entry["api_key"] = "***REDACTED***"

    # Regex scrubbing for PII
    entry["message"] = re.sub(
        r'\b[\w\.-]+@[\w\.-]+\.\w+\b',  # Email regex
        "***EMAIL***",
        entry["message"]
    )

    return entry
```

---

## Part 3: Correlation ID Propagation

### Correlation ID Design

**Purpose**: Trace requests across components for debugging

**Format**: UUIDv4 (128-bit random)

**Example**: `550e8400-e29b-41d4-a716-446655440000`

### Propagation Rules

#### Rule 1: Generated at Entry Point

**Entry points**:
- Suite runner start: Generate `run_id`
- Experiment start: Generate `experiment_id`
- HTTP request: Extract from header or generate

**Example**:
```python
def run_suite():
    run_id = str(uuid.uuid4())  # Generate at entry
    context = PluginContext(run_id=run_id, ...)
    # Propagate through all components
```

---

#### Rule 2: Propagated Through Context

**Mechanism**: `PluginContext` object

**Example**:
```python
class PluginContext:
    run_id: str             # Suite-level correlation ID
    experiment_id: str      # Experiment-level correlation ID
    security_level: SecurityLevel
    audit_logger: AuditLogger
```

**All plugins receive context**:
```python
def datasource_load(self, context: PluginContext):
    self.audit_logger.log_event(
        "datasource_load",
        correlation_id=context.run_id,  # Propagate correlation ID
        ...
    )
```

---

#### Rule 3: Included in All Log Entries

**Mandatory field**: All log entries MUST include `correlation_id`

**Example**:
```json
{
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "...",
  ...
}
```

**Rationale**: Enables log aggregation and tracing across components.

---

## Part 4: Retention Policy

### Retention Periods

| Log Type | Retention | Rationale |
|----------|-----------|-----------|
| **Security Events** | **90 days** | Compliance minimum (PSPF, FedRAMP) |
| **Data Processing** | **90 days** | GDPR right to access, provenance |
| **Error Logs** | **30 days** | Operational debugging |
| **Cost/Usage** | **12 months** | Financial audit |
| **Performance Metrics** | **30 days** | Operational monitoring |

### Cleanup Mechanism

**Automatic Cleanup**:
- Daily cron job: Delete logs older than retention period
- Environment variable: `ELSPETH_LOG_MAX_AGE_DAYS` (override retention)
- Graceful degradation: If cleanup fails, log warning (don't block pipeline)

**Manual Cleanup**:
- CLI command: `elspeth logs clean --before 2025-09-26`
- Confirmation required for bulk deletion

---

## Part 5: Failure Handling

### Logging Failure Scenarios

#### Scenario 1: Audit Logging Fails (Security Events)

**Policy**: **Abort operation** (fail-closed, ADR-001)

**Rationale**: Security audit trail is non-negotiable. If we can't log security events, operation is insecure.

**Example**:
```python
try:
    audit_logger.log_security_event("clearance_violation", ...)
except Exception as exc:
    raise SecurityCriticalError(
        "Audit logging failed, aborting for security"
    ) from exc
# ✅ Operation aborted, user notified
```

---

#### Scenario 2: Performance Logging Fails (Non-Security)

**Policy**: **Log warning, continue** (best-effort)

**Rationale**: Observability is important but should not block pipeline execution (ADR-001 priority #3: Availability).

**Example**:
```python
try:
    telemetry_logger.log_performance("llm_latency", ...)
except Exception as exc:
    logger.warning(f"Telemetry logging failed: {exc}")
    # ✅ Continue pipeline, telemetry is best-effort
```

---

#### Scenario 3: Log Storage Full

**Policy**: **Rotate logs, emit warning**

**Rationale**: Disk full should trigger cleanup, not abort pipeline.

**Example**:
```python
try:
    log_file.write(log_entry)
except OSError as exc:
    if exc.errno == errno.ENOSPC:  # Disk full
        rotate_logs()  # Delete oldest logs
        log_file.write(log_entry)  # Retry
```

---

## Part 6: Environment-Specific Implementation

### Separation of Policy vs Implementation

**This ADR defines POLICY** (what to log, retention, failure handling)

**Middleware implements** environment-specific observability:

#### Implementation 1: Generic Audit Logger (All Environments)

**Purpose**: File-based audit logging (JSONL format)

**Location**: `logs/run_*.jsonl`

**Configuration**: Minimal (file path, retention)

**Example**:
```python
class GenericAuditLogger(AuditLogger):
    """Generic file-based audit logger."""

    def log_event(self, event_type, **kwargs):
        entry = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs
        }
        # Scrub sensitive data
        entry = scrub_log_entry(entry)

        # Write to JSONL file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
```

---

#### Implementation 2: Azure ML Telemetry Middleware (Azure Only)

**Purpose**: Azure ML workspace integration (performance, cost)

**Features**:
- Azure ML Run tracking
- Cost attribution (Azure Cost Management)
- Performance dashboards (Azure Monitor)

**Configuration**: Azure ML workspace, experiment name

**Example**:
```python
class AzureMLTelemetryMiddleware(TelemetryMiddleware):
    """Azure ML-specific telemetry."""

    def log_performance(self, metric, value):
        # Azure ML SDK
        mlflow.log_metric(metric, value)
```

---

#### Implementation 3: Health Monitoring Middleware (Custom)

**Purpose**: Component health checks, dependency monitoring

**Features**:
- HTTP health endpoints (`/health`, `/ready`)
- Dependency checks (database, blob storage)
- Circuit breaker integration

**Configuration**: Health check interval, timeout

---

### Middleware Registration

Middleware is **environment-specific** (not mandated by this ADR):

```yaml
# Azure environment
middleware:
  - type: generic_audit_logger  # ✅ REQUIRED (global policy)
    log_file: logs/audit.jsonl

  - type: azure_ml_telemetry     # ⚠️ OPTIONAL (Azure-specific)
    workspace: my-workspace

# Local environment
middleware:
  - type: generic_audit_logger  # ✅ REQUIRED (global policy)
    log_file: logs/audit.jsonl
  # No Azure ML telemetry (not available locally)
```

---

## Consequences

### Benefits

1. **Compliance-Ready**: Audit trail meets regulatory requirements (PSPF, HIPAA, PCI-DSS)
2. **Security Visibility**: All security events logged (clearance violations, access denied)
3. **Debuggability**: Correlation IDs enable tracing across components
4. **PII Protection**: Prohibited logging prevents PII leakage
5. **Clear Policy**: Separation of global policy (ADR) vs environment implementation (middleware)
6. **Fail-Closed**: Audit logging failures abort operation (security-first)

### Limitations / Trade-offs

1. **Logging Overhead**: Audit logging adds latency (~5-10ms per event)
   - *Mitigation*: Asynchronous logging (buffered writes)

2. **Storage Costs**: 90-day retention consumes disk space
   - *Mitigation*: Automatic cleanup, compression

3. **PII Scrubbing Complexity**: Regex-based scrubbing may miss edge cases
   - *Mitigation*: Allowlist approach (only log approved fields)

4. **Fail-Closed for Audit**: Audit logging failure aborts pipeline
   - *Mitigation*: Intentional (security > availability, ADR-001)

5. **Environment Complexity**: Middleware registration varies by environment
   - *Mitigation*: Clear documentation, configuration examples

### Future Enhancements (Post-1.0)

1. **Structured Logging**: OpenTelemetry integration (spans, traces)
2. **Log Aggregation**: Centralized log collection (ELK stack, Azure Monitor)
3. **Real-Time Alerting**: Security event alerts (email, Slack, PagerDuty)
4. **Log Anonymization**: K-anonymity for data analysis
5. **Compliance Reports**: Automated compliance report generation

### Implementation Checklist

**Phase 1: Policy Formalization** (P1, 1 hour):
- [ ] Formalize as ADR (this document)
- [ ] Update audit logging documentation

**Phase 2: Scrubbing Enhancement** (P1, 2 hours):
- [ ] Implement sensitive data scrubbing (regex + allowlist)
- [ ] Add PII detection (emails, SSNs, phone numbers)
- [ ] Test scrubbing with realistic data

**Phase 3: Compliance Validation** (P1, 1 hour):
- [ ] Verify 90-day retention for security events
- [ ] Verify correlation ID propagation
- [ ] Verify prohibited content not logged

### Related ADRs

- **ADR-001**: Design Philosophy – Security-first, fail-closed principle
- **ADR-002**: Multi-Level Security – Security events must be logged
- **ADR-010**: Error Classification – Error events must be logged

### Implementation References

- `src/elspeth/core/security/audit.py` – Generic audit logger
- `src/elspeth/plugins/nodes/transforms/llm/middleware_azure.py` – Azure ML telemetry
- `src/elspeth/core/base/plugin.py` – PluginContext propagation
- `docs/architecture/audit-logging.md` – Current audit logging guide

---

**Document Status**: DRAFT – Requires review and acceptance
**Next Steps**:
1. Review with team (retention periods, failure handling)
2. Implement sensitive data scrubbing
3. Validate compliance (90-day retention, correlation IDs)
4. Update middleware documentation
