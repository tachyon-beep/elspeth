# ADR-013 – Global Observability Policy

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

## Part 2: Sensitive Data Handling & Scrubbing Policy

### Policy Overview

**Critical Principle**: PII and classified content **CAN be logged** because sink clearance is **enforced at pipeline construction** (Part 4). Lower-clearance sinks are **rejected immediately** (fail-fast), making cross-level leakage structurally impossible.

**Security Model**:

- **MLS Enforcement** (Part 4): Sink clearance validated at construction, mismatched sinks **abort pipeline immediately**
- **No Lower-Cleared Sinks**: You cannot connect an UNOFFICIAL sink to a SECRET pipeline (construction fails)
- **Data Minimization** (Part 2): Scrubbing is **operational choice** (full content vs metadata), not security requirement
- **Secrets** (Always prohibited): Never log credentials, even to cleared sinks

**Key Insight**: Security is enforced by **infrastructure** (clearance validation), not **content filtering** (scrubbing). Scrubbing is for efficiency/minimization, not security.

---

### Category 1: PII (Personally Identifiable Information)

**Policy**: **MAY log** PII to cleared sinks (sink clearance enforced at construction). Scrubbing is **operational choice** for data minimization.

**Important**: Lower-clearance sinks are **rejected at construction** (ADR-002 fail-fast). There is no runtime scenario where PII logs to an unchecked sink.

**Logging Decision Matrix**:

| Content Type | Full Content Logging | Metadata-Only Logging | Rationale |
|--------------|---------------------|----------------------|-----------|
| **Full names** | ✅ Log for audit trail | ⚠️ Log user_id only | Audit requires identity, but user_id reduces breach impact |
| **Email addresses** | ✅ Log for debugging | ⚠️ Log user_id only | Contact info helps triage, but scrubbing reduces storage |
| **Phone, SSN, addresses** | ⚠️ Log if operationally critical | ✅ Omit entirely | Highly sensitive, only log if compliance requires |
| **IP addresses** | ✅ Log for security events | ⚠️ Scrub for general logs | Security triage needs IP, but scrub non-security logs |

**Example 1** (full context logging - operational choice):

```json
{
  "event_type": "authentication_failure",
  "timestamp": "2025-10-26T14:30:00Z",
  "user_email": "john.doe@example.com",  // ✅ Full PII (sink already cleared)
  "ip_address": "192.168.1.100",         // ✅ Security event
  "failure_reason": "invalid_password"
}
// OFFICIAL pipeline → Azure Blob OFFICIAL sink
// Sink clearance validated at construction ✅
// Full context aids debugging, compliance audit
```

**Example 2** (metadata-only logging - data minimization choice):

```json
{
  "event_type": "authentication_failure",
  "timestamp": "2025-10-26T14:30:00Z",
  "user_id": "user_550e8400",            // ⚠️ Metadata only (still traceable)
  "ip_address_prefix": "192.168.xxx",    // ⚠️ Scrubbed for efficiency
  "failure_reason": "invalid_password"
}
// OFFICIAL pipeline → Azure Blob OFFICIAL sink
// Sink clearance validated at construction ✅
// Metadata reduces storage, still enables triage
```

**Note**: Both examples use OFFICIAL-cleared sinks (construction validated). The difference is **operational choice** (full vs metadata), not security validation.

**Scrubbing Recommendation**: Scrub PII even for cleared sinks unless full context operationally necessary (data minimization, efficiency).

---

### Category 2: Classified Content

**Policy**: **MAY log** classified content to cleared sinks (sink clearance enforced at construction). Use metadata-only for efficiency, full content for debugging/audit.

**Important**: Sink clearance is **binary** - either validated at construction (pass) or pipeline aborts (fail). There is no "lower-cleared sink" scenario at runtime.

**Logging Decision Matrix**:

| Content Type | Full Content Logging | Metadata-Only Logging | Rationale |
|--------------|---------------------|----------------------|-----------|
| **Prompt content** | ✅ Log full text for debugging | ⚠️ Log length/template for efficiency | Full prompt aids deep debugging, metadata saves 90%+ storage |
| **LLM responses** | ✅ Log full text for audit | ⚠️ Log status/length for efficiency | Compliance may require response, metadata sufficient for triage |
| **Datasource content** | ✅ Log rows for provenance | ⚠️ Log schema/counts for efficiency | Reproducibility may need snapshot, metadata reduces cost |
| **Artifact payloads** | ⚠️ Log for critical audit | ✅ Log metadata only | Bundle sink captures payloads, log metadata avoids duplication |

**Example 1** (full content logging - debugging/audit choice):

```json
{
  "event_type": "llm_call",
  "correlation_id": "550e8400-...",
  "prompt": "Summarize this SECRET intelligence report: ...",  // ✅ Full text (sink cleared)
  "response": "Summary: The report indicates...",             // ✅ Full response
  "model": "gpt-4",
  "latency_ms": 1500
}
// SECRET pipeline → Azure Blob Gov Cloud SECRET sink
// Sink clearance validated at construction ✅
// Full content enables deep debugging, compliance audit
```

**Example 2** (metadata-only logging - efficiency choice):

```json
{
  "event_type": "llm_call",
  "correlation_id": "550e8400-...",
  "prompt_length": 500,                   // ⚠️ Metadata (90%+ storage savings)
  "prompt_template": "intelligence_summary",
  "response_length": 200,                 // ⚠️ Metadata only
  "response_status": "success",
  "model": "gpt-4",
  "latency_ms": 1500
}
// SECRET pipeline → Azure Blob Gov Cloud SECRET sink
// Sink clearance validated at construction ✅
// Metadata sufficient for performance monitoring, cost analysis
```

**Note**: Both examples use SECRET-cleared sinks (construction validated). The difference is **operational choice** (full text vs metadata), not security validation.

**Scrubbing Recommendation**:

- **For debugging/audit**: Log full content (sink already cleared, security enforced at construction)
- **For performance/cost**: Log metadata only (reduces storage 90%+, sufficient for monitoring)
- **Decision**: Based on compliance requirements vs operational efficiency

---

### Category 3: Secrets & Credentials (ALWAYS PROHIBITED)

**Policy**: **MUST NOT log** secrets, even to cleared sinks. Credentials are **never safe** in logs.

**Prohibited Content** (no exceptions):

- API keys, tokens, passwords
- Encryption keys, signing keys (HMAC, RSA, ECDSA)
- Connection strings with embedded credentials
- OAuth tokens, refresh tokens
- Database passwords, service account credentials

**Rationale**:

- Credentials enable impersonation (lateral movement)
- Log breaches would compromise authentication
- No legitimate debugging use case for credential values
- Key rotation invalidates logged credentials (noise)

**Example** (correct handling):

```json
{
  "event_type": "azure_openai_configured",
  "endpoint": "https://example.openai.azure.com",
  "api_key": "***REDACTED***",           // ✅ Redacted
  "key_length": 32,                       // ✅ Metadata OK
  "key_rotation_date": "2025-10-01"      // ✅ Operational info
}
```

**Example** (violation):

```json
{
  "event_type": "azure_openai_configured",
  "endpoint": "https://example.openai.azure.com",
  "api_key": "sk-abc123def456..."        // ❌ CRITICAL VIOLATION
}
// Even in SECRET sink, this is a security vulnerability
```

---

### Scrubbing Implementation (Optional, Recommended)

**When to Scrub**:

- **Lower-cleared sinks**: MUST scrub classified content exceeding sink clearance
- **Data minimization**: SHOULD scrub PII even for cleared sinks (reduce breach impact)
- **Storage efficiency**: SHOULD use metadata instead of full payloads (reduce costs)
- **Secrets**: MUST scrub always (no exceptions)

**Scrubbing Mechanisms**:

#### 1. Regex-Based Scrubbing

```python
import re

def scrub_pii(text: str) -> str:
    """Scrub PII patterns from text."""
    # Email addresses
    text = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w+\b', '***EMAIL***', text)

    # SSNs (US format)
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '***SSN***', text)

    # Credit cards (simple pattern)
    text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '***CC***', text)

    # IP addresses (optional)
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***IP***', text)

    return text
```

#### 2. Field Allowlist

```python
def scrub_log_entry(entry: dict, allowed_fields: set[str]) -> dict:
    """Scrub log entry to allowlist fields only."""
    return {k: v for k, v in entry.items() if k in allowed_fields}

# Example usage
ALLOWED_FIELDS = {
    "event_type", "timestamp", "correlation_id", "component",
    "latency_ms", "status", "error_type"
}

scrubbed = scrub_log_entry(raw_entry, ALLOWED_FIELDS)
# Result: Only allowlisted fields remain
```

#### 3. Content-Based Scrubbing

```python
def scrub_classified_content(entry: dict, sink_level: SecurityLevel) -> dict:
    """Scrub content exceeding sink clearance."""
    if "prompt" in entry and entry.get("prompt_classification", SecurityLevel.OFFICIAL) > sink_level:
        # Replace with metadata
        entry["prompt_length"] = len(entry.pop("prompt"))
        entry["prompt_scrubbed"] = True

    if "response" in entry and entry.get("response_classification", SecurityLevel.OFFICIAL) > sink_level:
        # Replace with metadata
        entry["response_length"] = len(entry.pop("response"))
        entry["response_scrubbed"] = True

    return entry
```

**Scrubbing at Sink Boundary** (recommended):

```python
class AuditLogSink(BasePlugin, ResultSink):
    """Audit log sink with automatic scrubbing."""

    def write(self, log: SecureAuditLog) -> None:
        """Write logs with optional scrubbing based on sink clearance."""
        scrubbed_entries = []

        for entry in log.entries:
            # Scrub if log level exceeds sink clearance
            if log.security_level > self.security_level:
                raise SecurityValidationError(
                    f"Cannot write {log.security_level} logs to {self.security_level} sink"
                )

            # Optional: Scrub for data minimization even if cleared
            if self.config.get("scrub_pii", False):
                entry = scrub_pii_fields(entry)

            scrubbed_entries.append(entry)

        # Write scrubbed logs
        self._write_to_storage(scrubbed_entries)
```

---

### Summary: Scrubbing vs Sink Clearance

**Two Independent Security Mechanisms**:

| Mechanism | Purpose | When Applied | Mandatory? |
|-----------|---------|--------------|------------|
| **Sink Clearance** (Part 4) | Prevent cross-level leakage | At sink boundary | ✅ YES (ADR-002) |
| **Content Scrubbing** (Part 2) | Data minimization, efficiency | Optional, at logging or sink | ⚠️ Recommended |

**Example**:

```python
# SECRET pipeline with SECRET sink
log = SecureAuditLog(security_level=SecurityLevel.SECRET)
sink = AzureBlobSink(security_level=SecurityLevel.SECRET)

# Sink clearance: PASS (SECRET ≥ SECRET)
validate_clearance(log, sink)  # ✅ OK

# Content scrubbing: Optional
if sink.config.get("scrub_for_efficiency"):
    log.entries = [scrub_pii(e) for e in log.entries]  # ⚠️ Recommended
```

**Result**: Security enforced by clearance, efficiency improved by scrubbing.

---

### Key Architectural Innovation: Logs Flow to Sinks

**Traditional Observability** (pre-ADR-013):

```python
# ❌ Direct file writes - no clearance validation
with open(f"logs/run_{run_id}.jsonl", "a") as f:
    f.write(json.dumps(log_entry) + "\n")

# Problems:
# - Log file has no security level (unclassified by default?)
# - No validation that /logs/ directory has appropriate clearance
# - SECRET metadata could leak to world-readable filesystem
# - Log rotation/retention handled separately from pipeline
```

**Elspeth Observability** (ADR-013):

```python
# ✅ Logs flow through artifact pipeline with clearance validation
audit_log = SecureAuditLog(
    security_level=pipeline.effective_level,  # Inherits from pipeline
    entries=[...],
)

# Route to sink with validated clearance
artifact_pipeline.route_artifact(
    audit_log.to_artifact(),
    sink=log_sink,  # Azure Blob Gov Cloud (SECRET clearance)
)

# Sink validation at construction (fail-fast)
if log_sink.security_level < audit_log.security_level:
    raise SecurityValidationError("Sink lacks clearance")  # ✅ Aborts before data

# Benefits:
# - Log sink clearance validated at construction (fail-fast)
# - Logs are security artifacts (same treatment as results)
# - MLS enforcement prevents cross-level leakage structurally
# - Sink handles retention, encryption, access controls
```

**Key Innovation**: **Logs are routed to sinks, not written to disk**. This enables:

1. **Security by Construction**: Lower-clearance sinks rejected at pipeline construction (impossible to leak)
2. **Uniform Treatment**: Logs treated as security artifacts (SecureAuditLog ≈ SecureDataFrame)
3. **Environment Portability**: Same pipeline works with local file (dev) or Azure Blob Gov Cloud (prod)
4. **Separation of Concerns**:
   - **Part 2 (Scrubbing)**: Operational efficiency (full content vs metadata)
   - **Part 4 (Sinks)**: Security enforcement (MLS clearance validation)

**Example Configuration** (environment-specific sinks):

```yaml
# Development environment
audit_logging:
  sinks:
    UNOFFICIAL:
      type: local_file
      path: logs/run_{run_id}.jsonl

# Production environment
audit_logging:
  sinks:
    OFFICIAL:
      type: azure_blob
      container: elspeth-audit-official
      encryption: aes256
    SECRET:
      type: azure_blob
      container: elspeth-audit-secret-govcloud
      region: us-gov-virginia
      encryption: fips140_2
```

**Result**: Same pipeline code works across environments. Security enforced by sink configuration, not code logic.

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

### Hierarchical Correlation IDs

Elspeth uses a **three-tier correlation ID hierarchy** for granular tracing:

#### Tier 1: `run_id` (Suite-Level)

**Scope**: Entire experiment suite execution

**Generated**: At suite runner start (`ExperimentSuiteRunner`)

**Format**: `run_<timestamp>_<uuid>`

**Example**: `run_20251026_143000_550e8400`

**Usage**: Groups all experiments in a single suite execution

```python
# Generated once per suite run
run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
```

---

#### Tier 2: `experiment_id` (Experiment-Level)

**Scope**: Single experiment within suite

**Generated**: At experiment orchestrator start

**Format**: `exp_<experiment_name>_<uuid>`

**Example**: `exp_baseline_comparison_abc123de`

**Parent**: Links to `run_id`

**Usage**: Trace all rows/items within one experiment

```python
# Generated per experiment
experiment_id = f"exp_{experiment_name}_{uuid.uuid4().hex[:8]}"
```

---

#### Tier 3: `item_id` (Item-Level)

**Scope**: Single row/item being processed

**Generated**: At datasource row iteration

**Format**: `item_<row_number>` or datasource-defined ID

**Example**: `item_001`, `row_123`

**Parent**: Links to `experiment_id`

**Usage**: Trace single item through pipeline (datasource → transform → sink)

```python
# Datasource assigns item_id
for idx, row in enumerate(datasource.load_data()):
    item_id = row.get("id", f"item_{idx:03d}")
```

---

### Correlation ID Propagation Examples

#### End-to-End Trace Example

**Suite execution trace**:

```
run_20251026_143000_550e8400          (Suite starts)
  ├─ exp_baseline_comparison_abc123de  (Experiment 1 starts)
  │   ├─ item_001                      (Row 1: datasource → LLM → sink)
  │   ├─ item_002                      (Row 2: datasource → LLM → sink)
  │   └─ item_003                      (Row 3: datasource → LLM → sink)
  └─ exp_variant_test_def456gh         (Experiment 2 starts)
      ├─ item_001                      (Row 1: datasource → LLM → sink)
      └─ item_002                      (Row 2: datasource → LLM → sink)
```

**Log Query** (find all logs for Experiment 1):

```bash
jq 'select(.experiment_id == "exp_baseline_comparison_abc123de")' logs/run_*.jsonl
```

**Log Query** (find all logs for Item 2 in Experiment 1):

```bash
jq 'select(.experiment_id == "exp_baseline_comparison_abc123de" and .item_id == "item_002")' logs/run_*.jsonl
```

---

#### Cross-Component Propagation

**PluginContext Structure**:

```python
@dataclass
class PluginContext:
    """Propagates correlation IDs through pipeline."""
    run_id: str                      # Tier 1: Suite-level
    experiment_id: str               # Tier 2: Experiment-level
    item_id: str | None = None       # Tier 3: Item-level (optional)
    security_level: SecurityLevel
    audit_logger: AuditLogger
```

**Propagation Flow**:

```python
# Suite runner creates context
context = PluginContext(
    run_id=run_id,
    experiment_id=experiment_id,
    security_level=SecurityLevel.OFFICIAL,
    audit_logger=audit_logger,
)

# Datasource receives context, adds item_id
for row in datasource.load_data(context):
    item_context = context.with_item_id(row["id"])  # Add item_id

    # Transform receives item context
    result = transform.transform(row, item_context)

    # Sink receives item context
    sink.write(result, item_context)
```

**All log entries include full hierarchy**:

```json
{
  "run_id": "run_20251026_143000_550e8400",
  "experiment_id": "exp_baseline_comparison_abc123de",
  "item_id": "item_002",
  "event_type": "llm_call",
  "component": "AzureOpenAIClient",
  "timestamp": "2025-10-26T14:30:15Z"
}
```

---

### HTTP Header Propagation (External Systems)

When Elspeth calls external APIs (Azure OpenAI, blob storage), correlation IDs propagate via HTTP headers:

**Outbound HTTP Headers**:

```http
X-Elspeth-Run-ID: run_20251026_143000_550e8400
X-Elspeth-Experiment-ID: exp_baseline_comparison_abc123de
X-Elspeth-Item-ID: item_002
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000  # Standard header
```

**Implementation**:

```python
import requests

def call_azure_openai(prompt: str, context: PluginContext):
    """Call Azure OpenAI with correlation headers."""
    headers = {
        "X-Elspeth-Run-ID": context.run_id,
        "X-Elspeth-Experiment-ID": context.experiment_id,
        "X-Request-ID": str(uuid.uuid4()),  # Unique per HTTP request
    }

    if context.item_id:
        headers["X-Elspeth-Item-ID"] = context.item_id

    response = requests.post(
        "https://example.openai.azure.com/completions",
        json={"prompt": prompt},
        headers=headers,
    )

    # Log with correlation IDs
    audit_logger.log_event(
        "llm_call",
        correlation_id=context.run_id,
        experiment_id=context.experiment_id,
        item_id=context.item_id,
        request_id=headers["X-Request-ID"],
        latency_ms=response.elapsed.total_seconds() * 1000,
    )
```

**Benefit**: Azure Application Insights can correlate Elspeth logs with Azure OpenAI logs using `X-Request-ID`.

---

### Debugging Workflow with Correlation IDs

#### Scenario 1: User reports "Experiment failed"

**Step 1**: Find run_id from user report

```bash
# User provides: "My suite failed at 2:30 PM on Oct 26"
ls logs/ | grep "run_20251026_1430"
# Result: run_20251026_143000_550e8400.jsonl
```

**Step 2**: Find all errors in that run

```bash
jq 'select(.run_id == "run_20251026_143000_550e8400" and .event_type == "exception")' \
  logs/run_20251026_143000_550e8400.jsonl
```

**Step 3**: Identify failing experiment

```bash
jq 'select(.event_type == "exception") | .experiment_id' \
  logs/run_20251026_143000_550e8400.jsonl | sort | uniq
# Result: exp_baseline_comparison_abc123de
```

**Step 4**: Trace specific item that failed

```bash
jq 'select(.experiment_id == "exp_baseline_comparison_abc123de" and .event_type == "exception") | .item_id' \
  logs/run_20251026_143000_550e8400.jsonl
# Result: item_002
```

**Step 5**: Get full trace for failing item

```bash
jq 'select(.item_id == "item_002")' \
  logs/run_20251026_143000_550e8400.jsonl
```

**Output** (chronological trace):

```json
{"event_type": "datasource_load", "item_id": "item_002", "timestamp": "14:30:10Z"}
{"event_type": "llm_call", "item_id": "item_002", "timestamp": "14:30:11Z"}
{"event_type": "exception", "item_id": "item_002", "error_class": "Timeout", "timestamp": "14:30:41Z"}
{"event_type": "retry_attempt", "item_id": "item_002", "retry_count": 1, "timestamp": "14:30:43Z"}
{"event_type": "exception", "item_id": "item_002", "error_class": "Timeout", "timestamp": "14:31:13Z"}
```

**Root Cause**: Item 002 timed out twice, exhausted retry budget.

---

#### Scenario 2: Performance Investigation

**Query**: "Which items took longest in experiment X?"

```bash
jq 'select(.experiment_id == "exp_baseline_comparison_abc123de" and .event_type == "llm_call") |
    {item_id: .item_id, latency_ms: .latency_ms}' \
  logs/run_*.jsonl | \
jq -s 'sort_by(.latency_ms) | reverse | .[0:10]'
```

**Output** (top 10 slowest items):

```json
[
  {"item_id": "item_042", "latency_ms": 15000},
  {"item_id": "item_017", "latency_ms": 12500},
  {"item_id": "item_089", "latency_ms": 11000},
  ...
]
```

---

### Correlation with External Systems

**Azure Application Insights Integration**:

- Elspeth logs include `run_id`, `experiment_id`, `item_id`
- Azure OpenAI logs include `X-Request-ID` (from HTTP header)
- Join on `request_id` field to correlate Elspeth → Azure

**Example Query** (Azure Kusto KQL):

```kql
// Find all Azure OpenAI calls for Elspeth run
requests
| where customDimensions.["X-Elspeth-Run-ID"] == "run_20251026_143000_550e8400"
| project timestamp, resultCode, duration, itemId=customDimensions.["X-Elspeth-Item-ID"]
```

**SonarQube/Security Scanning Integration**:

- Elspeth logs include `run_id` in security events
- SonarQube analysis includes `run_id` in scan metadata
- Join on `run_id` to correlate pipeline execution with security scan

---

### Implementation References

- `src/elspeth/core/context.py` – `PluginContext` dataclass with correlation IDs
- `src/elspeth/core/security/audit.py` – Audit logger enforcing correlation ID presence
- `src/elspeth/core/experiments/suite_runner.py` – `run_id` generation
- `src/elspeth/core/experiments/orchestrator.py` – `experiment_id` generation
- `tests/test_correlation_ids.py` – Correlation ID propagation tests

---

## Part 4: Log Sink Security Requirements

### Log Security Level Inheritance

**Critical Principle**: Logs are **metadata about classified operations** and inherit the security level of the system/pipeline that generated them.

**Rationale** (ADR-002-A Trusted Container Model):

- A log entry stating "Processed SECRET document X" is itself SECRET metadata
- Even scrubbed logs (no payload content) reveal operational patterns at the system's classification level
- Logs are trusted containers analogous to `SecureDataFrame`

**Inheritance Rules**:

```python
# Audit log inherits pipeline effective security level
pipeline_level = SecurityLevel.SECRET  # Computed from datasource, transforms, sinks

audit_log = AuditLog(
    security_level=pipeline_level,  # Inherits pipeline level
    entries=[...],
)

# Even if individual entries contain no classified content,
# the log as a whole is classified at pipeline_level
```

---

### Logs as Trusted Containers (ADR-002-A Integration)

**Design Principle**: Logs use the **same trusted container pattern** as pipeline data.

**Container Model**:

- **Data**: Wrapped in `SecureDataFrame` (ADR-002-A)
- **Logs**: Wrapped in `SecureAuditLog` (analogous container)

**Implementation**:

```python
from dataclasses import dataclass
from elspeth.core.data import SecureDataFrame  # ADR-002-A

@dataclass
class SecureAuditLog:
    """Trusted container for audit logs (analogous to SecureDataFrame).

    Logs are metadata about classified operations and inherit the security
    level of the pipeline that generated them. This container enforces the
    same security properties as SecureDataFrame:

    - Security level is immutable after creation
    - Cannot be downgraded (unless created with allow_downgrade=True)
    - Factory pattern ensures only authorized sources can create
    - Clearance validation enforced at sink boundary
    """

    security_level: SecurityLevel  # Inherited from pipeline
    allow_downgrade: bool           # From pipeline policy (ADR-005)
    entries: list[dict]             # Scrubbed log entries (Part 2)
    run_id: str                     # Correlation ID (Part 3)
    created_at: datetime
    _frozen: bool = False           # Immutability flag

    def __post_init__(self):
        """Freeze container after creation (immutable security level)."""
        self._frozen = True

    def __setattr__(self, name: str, value):
        """Prevent modification of security level after creation."""
        if hasattr(self, "_frozen") and self._frozen and name == "security_level":
            raise SecurityCriticalError(
                "Cannot modify security_level of SecureAuditLog after creation. "
                "Logs are trusted containers with immutable classification (ADR-002-A)."
            )
        super().__setattr__(name, value)
```

**Factory Pattern** (only suite runner can create):

```python
class ExperimentSuiteRunner:
    """Suite runner creates SecureAuditLog via factory."""

    def _create_audit_log(self) -> SecureAuditLog:
        """Factory: Create audit log with pipeline security level."""
        return SecureAuditLog(
            security_level=self.effective_level,  # Pipeline level
            allow_downgrade=self._pipeline_allow_downgrade,  # Pipeline policy
            entries=[],
            run_id=self.run_id,
            created_at=datetime.utcnow(),
        )

    def run(self):
        """Run suite with classified audit log."""
        # Create trusted container
        audit_log = self._create_audit_log()  # ✅ Factory enforces security level

        # Log events during execution
        audit_log.entries.append({
            "event_type": "suite_start",
            "timestamp": datetime.utcnow().isoformat(),
        })

        # ... suite execution ...

        # Validate sink clearance (same pattern as SecureDataFrame)
        if log_sink.security_level < audit_log.security_level:
            raise SecurityValidationError(
                f"Sink lacks clearance for {audit_log.security_level} logs"
            )

        # Write to cleared sink
        log_sink.write(audit_log)  # ✅ Clearance validated
```

**Direct Creation Prevention** (same as SecureDataFrame):

```python
# ❌ Direct creation bypasses security controls
audit_log = SecureAuditLog(
    security_level=SecurityLevel.UNOFFICIAL,  # Lies about level!
    entries=[{"event": "processed SECRET data"}],  # Actually SECRET metadata
)
# This would leak SECRET metadata to UNOFFICIAL sink

# ✅ Must use factory (only suite runner authorized)
audit_log = suite_runner._create_audit_log()  # Enforces pipeline level
```

**Analogy to Data Containers**:

| Component | Data Container | Log Container | Security Property |
|-----------|---------------|---------------|-------------------|
| **Pipeline Data** | `SecureDataFrame` | `SecureAuditLog` | Immutable security level |
| **Factory** | Datasource only | Suite runner only | Authorized creation |
| **Validation** | At sink boundary | At sink boundary | Clearance enforcement |
| **Downgrade** | Via `allow_downgrade` | Via `allow_downgrade` | Explicit policy (ADR-005) |

**Benefit**: Logs receive the **same security guarantees** as data:

- ✅ Factory creation prevents manual classification tampering
- ✅ Immutable security level after creation
- ✅ Clearance validation at sink boundary
- ✅ Audit trail for log creation (logs about logs)

---

### Log Sink Clearance Requirements

**Requirement**: All log sinks MUST have clearance ≥ log security level (ADR-002 MLS enforcement).

**Validation** (fail-fast):

```python
def validate_log_sink_clearance(log: AuditLog, sink: ResultSink) -> None:
    """Validate sink has clearance for log security level."""
    if sink.security_level < log.security_level:
        raise SecurityValidationError(
            f"Log sink '{sink.name}' has insufficient clearance. "
            f"Required: {log.security_level}, Actual: {sink.security_level}. "
            f"Logs contain metadata about {log.security_level} operations and "
            f"must be routed to appropriately cleared sinks (ADR-002-A)."
        )
```

**Example** (clearance violation):

```python
# Pipeline processes SECRET data
pipeline = Pipeline(effective_security_level=SecurityLevel.SECRET)

# Audit log inherits SECRET level
audit_log = AuditLog(security_level=SecurityLevel.SECRET)

# Local file sink has UNOFFICIAL clearance
local_file_sink = LocalFileSink(security_level=SecurityLevel.UNOFFICIAL)

# Validation FAILS
validate_log_sink_clearance(audit_log, local_file_sink)
# ❌ SecurityValidationError: Log sink lacks clearance for SECRET logs
```

---

### Integration with Artifact Pipeline (ADR-007)

**Design**: Audit logs flow through the **Universal Dual-Output Protocol** as security artifacts.

**Implementation**:

```python
class AuditLogger(BasePlugin):
    """Audit logger producing logs as security artifacts."""

    def __init__(self, *, security_level: SecurityLevel, allow_downgrade: bool):
        super().__init__(
            security_level=security_level,
            allow_downgrade=allow_downgrade,
        )
        self._log_entries: list[dict] = []

    def log_event(self, event_type: str, **kwargs) -> None:
        """Log event to in-memory buffer."""
        entry = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **kwargs,
        }
        self._log_entries.append(entry)

    def produce_artifacts(self) -> list[Artifact]:
        """Produce audit log as security artifact (ADR-007)."""
        # Serialize log entries
        log_content = "\n".join(json.dumps(e) for e in self._log_entries)

        # Create artifact with inherited security level
        audit_artifact = Artifact(
            type="audit_log",
            format="jsonl",
            security_level=self.security_level,  # Inherits from logger
            content=log_content.encode("utf-8"),
            metadata={
                "run_id": self._run_id,
                "entry_count": len(self._log_entries),
                "categories": self._compute_categories(),
            },
            persist=True,  # MUST persist for compliance
        )

        return [audit_artifact]
```

**Pipeline Integration**:

```python
# Suite runner configures audit logger
audit_logger = AuditLogger(
    security_level=pipeline.effective_security_level,  # Inherits from pipeline
    allow_downgrade=False,  # Frozen at pipeline level (ADR-005)
)

# Audit logger produces artifact at end of run
audit_artifact = audit_logger.produce_artifacts()[0]

# Artifact pipeline routes to cleared sink
artifact_pipeline.route_artifact(audit_artifact, sink_registry)

# Sink validation enforces clearance
# ✅ Azure Blob sink (SECRET clearance) accepts SECRET logs
# ❌ Local file sink (UNOFFICIAL clearance) rejects SECRET logs
```

---

### Environment-Specific Sink Configuration

**Sink Selection Matrix**:

| Pipeline Security Level | Approved Log Sinks | Rationale |
|------------------------|-------------------|-----------|
| **UNOFFICIAL** | Local file (`logs/run_*.jsonl`), stdout | No special protection required |
| **OFFICIAL** | Azure Blob Storage (restricted), AWS S3 (encrypted) | Requires access controls, encryption at rest |
| **SECRET** | Azure Blob (gov cloud), AWS GovCloud, on-prem secure storage | Requires gov-certified cloud or air-gapped |
| **TOP SECRET** | Air-gapped on-prem, HSM-backed storage | Cannot use public cloud |

**Example Configuration** (`settings.yaml`):

```yaml
audit_logging:
  # Sink selection based on pipeline security level
  sinks:
    UNOFFICIAL:
      type: local_file
      path: logs/run_{run_id}.jsonl

    OFFICIAL:
      type: azure_blob
      container: elspeth-audit-logs-official
      storage_account: elspethauditofficial
      # Requires Azure AD auth, encryption at rest

    SECRET:
      type: azure_blob
      container: elspeth-audit-logs-secret
      storage_account: elspethauditsecret-govcloud
      region: us-gov-virginia  # Gov cloud region
      # Requires DoD IL5 certified storage

  # Retention policy (Part 5)
  retention_days: 90
```

**Runtime Sink Selection**:

```python
def select_log_sink(pipeline_level: SecurityLevel, config: dict) -> ResultSink:
    """Select appropriate log sink for pipeline security level."""
    sink_config = config["audit_logging"]["sinks"].get(pipeline_level.name)

    if not sink_config:
        raise ConfigurationError(
            f"No audit log sink configured for {pipeline_level}. "
            f"Logs at this level cannot be written to lower-clearance sinks. "
            f"Configure sink in settings.yaml under audit_logging.sinks.{pipeline_level.name}"
        )

    # Instantiate sink from registry
    sink = sink_registry.instantiate(sink_config["type"], sink_config)

    # Validate clearance
    if sink.security_level < pipeline_level:
        raise SecurityValidationError(
            f"Configured sink '{sink.name}' has insufficient clearance "
            f"({sink.security_level} < {pipeline_level})"
        )

    return sink
```

---

### Log Scrubbing vs Sink Clearance

**Important Distinction**:

**Log Scrubbing (Part 2)**: Removes PII, credentials, payload content

- **Purpose**: Data minimization, prevent PII leakage
- **Applies to**: Log content (fields within entries)
- **Does NOT change**: Log security level (metadata is still classified)

**Sink Clearance (Part 4)**: Routes logs to appropriately cleared storage

- **Purpose**: MLS enforcement, ensure logs don't leak to lower-cleared systems
- **Applies to**: Log destination (where logs are written)
- **Validates**: Sink clearance ≥ log security level

**Example**:

```python
# SECRET pipeline processes PII data
log_entry = {
    "event_type": "datasource_load",
    "file_path": "/data/secret_pii.csv",
    "email": "user@example.com",  # PII
}

# Step 1: Scrub PII (Part 2)
scrubbed_entry = scrub_log_entry(log_entry)
# Result: {"event_type": "datasource_load", "file_path": "/data/secret_pii.csv"}
# ✅ PII removed, but entry is still SECRET metadata

# Step 2: Validate sink clearance (Part 4)
audit_log = AuditLog(
    security_level=SecurityLevel.SECRET,
    entries=[scrubbed_entry],
)

# ❌ Cannot write to UNOFFICIAL local file (clearance violation)
# ✅ Must write to SECRET-cleared Azure Blob in gov cloud
```

**Both mechanisms are REQUIRED**:

- Scrubbing prevents PII leakage within a security level
- Sink clearance prevents classification leakage across security levels

---

### Validation at Pipeline Construction

**Fail-Fast Validation** (before data retrieval):

```python
class ExperimentSuiteRunner:
    """Suite runner with log sink validation (ADR-013)."""

    def __init__(self, settings: dict, suite_root: Path):
        # Compute pipeline effective security level (ADR-002)
        self.effective_level = self._compute_effective_level(settings)

        # Configure audit logger at pipeline level
        self.audit_logger = AuditLogger(
            security_level=self.effective_level,
            allow_downgrade=False,
        )

        # Select and validate log sink BEFORE run starts
        self.log_sink = select_log_sink(self.effective_level, settings)

        # Validate sink clearance (FAIL-FAST)
        if self.log_sink.security_level < self.effective_level:
            raise SecurityValidationError(
                f"Log sink misconfigured. Pipeline processes {self.effective_level} "
                f"data but log sink only has {self.log_sink.security_level} clearance. "
                f"Logs would leak classified metadata. Configure appropriate sink in "
                f"settings.yaml under audit_logging.sinks.{self.effective_level.name}"
            )

    def run(self):
        """Run suite with validated log sink."""
        # Audit events logged during execution
        self.audit_logger.log_event("suite_start", run_id=self.run_id)

        # ... suite execution ...

        # Produce audit artifact
        audit_artifact = self.audit_logger.produce_artifacts()[0]

        # Route to validated sink
        self.log_sink.write(audit_artifact)  # ✅ Clearance already validated
```

---

### Attack Scenario Prevention

**Attack**: Exfiltrate SECRET operational metadata via misconfigured log sink

**Without ADR-013 Part 4**:

```python
# Attacker configures SECRET pipeline with UNOFFICIAL log sink
settings = {
    "datasource": {"type": "secret_database", "security_level": "SECRET"},
    "audit_logging": {
        "sinks": {
            "SECRET": {"type": "local_file", "path": "/tmp/logs.jsonl"}  # ❌ Public dir
        }
    }
}

# Pipeline processes SECRET data
suite_runner.run()

# Logs written to /tmp/logs.jsonl (world-readable)
# Attacker reads: "Processed SECRET document X at 14:30"
# ❌ Metadata leak reveals operational patterns
```

**With ADR-013 Part 4** (fail-fast validation):

```python
# Same attacker configuration
settings = {...}  # Local file sink for SECRET logs

# Validation at construction
suite_runner = ExperimentSuiteRunner(settings, suite_root)
# ❌ FAILS IMMEDIATELY:
# SecurityValidationError: Log sink '/tmp/logs.jsonl' has UNOFFICIAL clearance
# but pipeline requires SECRET. Logs contain SECRET operational metadata.

# Pipeline NEVER STARTS
# ✅ No data retrieval, no metadata leak
```

---

### Implementation References

- `src/elspeth/core/security/audit.py` – `AuditLogger` class (artifact production)
- `src/elspeth/core/experiments/suite_runner.py` – Log sink validation at construction
- `src/elspeth/plugins/nodes/sinks/azure_blob_log_sink.py` – Azure Blob log sink (OFFICIAL+)
- `src/elspeth/plugins/nodes/sinks/local_file_log_sink.py` – Local file log sink (UNOFFICIAL only)
- `tests/test_log_sink_clearance.py` – Log sink clearance validation tests

---

## Part 5: Retention Policy

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

## Part 6: Failure Handling

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
