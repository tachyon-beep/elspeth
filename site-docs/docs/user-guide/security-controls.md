# Security Controls

Comprehensive guide to Elspeth's security mechanisms for protecting data and preventing unauthorized access.

!!! info "Data Classification vs Content Filtering"
    - **[Security Model](security-model.md)** = **Data classification** (Bell-LaPadula MLS enforcement)
    - **This page** = **Content filtering & protection** (PII detection, formula sanitization, signing)

---

## Quick Navigation

- [Content Filtering](#content-filtering) - PII detection, classified material blocking, prompt shielding
- [Output Protection](#output-protection) - Formula sanitization, artifact signing
- [Monitoring & Audit](#monitoring-audit) - Audit logging, health monitoring
- [Quick Start](#quick-start-production-configuration) - Complete secure configuration

---

## Content Filtering

### PII Detection (pii_shield Middleware)

**Purpose**: Prevent personally identifiable information from reaching external LLM APIs.

**Detects**:
- Email addresses (RFC 5322 compliant)
- Social Security Numbers (US format: XXX-XX-XXXX)
- Credit card numbers (Visa, Mastercard, Amex, Discover)
- Phone numbers (US format)
- Australian Tax File Numbers (TFN)
- Australian Medicare numbers

**Configuration**:
```yaml
llm:
  type: azure_openai
  middleware:
    - type: pii_shield
      on_violation: abort  # abort | mask | log
      patterns:
        - email
        - ssn
        - credit_card
        - phone
        - au_tfn
        - au_medicare
```

**Behavior**:
- `abort`: Raise `SecurityCriticalError`, stop pipeline immediately
- `mask`: Replace PII with `[REDACTED-{type}]`, continue processing
- `log`: Log warning, continue processing (for testing only)

**Example**:
```python
# Input prompt containing PII
"Send email to john.doe@example.com about account 123-45-6789"

# With on_violation: abort
SecurityCriticalError: PII detected: email, ssn

# With on_violation: mask
"Send email to [REDACTED-EMAIL] about account [REDACTED-SSN]"
```

**Full Documentation**: [PII Shield in Plugin Catalogue](../plugins/overview.md#example-pii-shield)

---

### Classified Material Detection (classified_material Middleware)

**Purpose**: Prevent classified markings from being sent to untrusted systems.

**Detects**:
- SECRET, TOP SECRET, CONFIDENTIAL
- TS//SCI (Top Secret // Sensitive Compartmented Information)
- NOFORN (No Foreign Nationals)
- PROTECTED, OFFICIAL SENSITIVE (Australian PSPF)
- Custom markings (configurable)

**Configuration**:
```yaml
llm:
  middleware:
    - type: classified_material
      on_violation: abort
      markings:
        - SECRET
        - TOP SECRET
        - TS//SCI
        - NOFORN
        - PROTECTED
      case_sensitive: false
```

**Use Cases**:
- Government contractors handling unclassified data
- Organizations with internal classification schemes
- Preventing accidental disclosure of sensitive markings

**Full Documentation**: [Classified Material Filter in Plugin Catalogue](../plugins/overview.md#example-classified-material-filter)

---

### Prompt Shielding (prompt_shield Middleware)

**Purpose**: Block banned terms, profanity, or organization-specific restricted content.

**Configuration**:
```yaml
llm:
  middleware:
    - type: prompt_shield
      on_violation: abort
      banned_terms:
        - "internal-only"
        - "do-not-distribute"
        - "company-confidential"
      case_sensitive: false
```

**Use Cases**:
- Enforcing organizational content policies
- Preventing accidental disclosure of internal jargon
- Custom term filtering

**Full Documentation**: [Prompt Shield in Plugin Catalogue](../plugins/overview.md#security-middleware)

---

### Azure Content Safety Integration

**Purpose**: External content safety validation using Azure Content Safety API.

**Checks**:
- Hate speech detection
- Violence/self-harm content
- Sexual content
- Profanity

**Configuration**:
```yaml
llm:
  middleware:
    - type: azure_content_safety
      endpoint: ${AZURE_CONTENT_SAFETY_ENDPOINT}
      api_key: ${AZURE_CONTENT_SAFETY_KEY}
      severity_threshold: medium  # low | medium | high
      on_violation: abort
```

**Requires**: Azure Content Safety resource (separate Azure service)

**Full Documentation**: [Azure Content Safety in Plugin Catalogue](../plugins/overview.md#security-middleware)

---

## Output Protection

### Formula Sanitization (Automatic)

**Purpose**: Prevent spreadsheet injection attacks (Excel, CSV).

**How It Works**:
- All CSV and Excel sinks **automatically sanitize** output
- Formulas are prefixed with `'` to prevent execution
- No configuration required (always enabled)

**Protected Formulas**:
```
Original: =SUM(A1:A10)
Sanitized: '=SUM(A1:A10)

Original: @SUM(A1:A10)  (Excel 4.0 macro)
Sanitized: '@SUM(A1:A10)

Original: +1+1
Sanitized: '+1+1
```

**Sinks with Automatic Sanitization**:
- `csv` (csv sink)
- `excel_workbook` (Excel XLSX)
- `visual_analytics` (CSV exports)

**Technical Details**: See `src/elspeth/plugins/nodes/sinks/_sanitize.py`

---

### Artifact Signing

**Purpose**: Tamper-evident artifacts with cryptographic integrity verification.

**Supported Algorithms**:
- `HMAC-SHA256` - Symmetric key (fast, recommended for internal use)
- `HMAC-SHA512` - Symmetric key (stronger hash)
- `RSA-PSS-SHA256` - Asymmetric key (public/private keypair)
- `ECDSA-P256-SHA256` - Asymmetric key (elliptic curve, smaller keys)

**Configuration**:
```yaml
sinks:
  - type: signed_artifact
    algorithm: HMAC-SHA256
    key_path: keys/signing.key
    output_path: outputs/signed_bundle.tar.gz
    security_level: OFFICIAL
```

**Output**:
```
outputs/
  signed_bundle.tar.gz          # Compressed archive
  signed_bundle.tar.gz.sig      # Signature file
  signed_bundle.tar.gz.manifest # Metadata (checksums, timestamps)
```

**Verification**:
```bash
python -m elspeth.cli verify-bundle \
  --bundle-path outputs/signed_bundle.tar.gz \
  --key-path keys/signing.key
```

**Use Cases**:
- Compliance requirements (HIPAA, PCI-DSS, government)
- Audit trails for regulatory review
- Tamper detection for experiment results

**Full Documentation**: [Signed Artifact Sink in Plugin Catalogue](../plugins/overview.md#example-signed-artifacts)

---

## Monitoring & Audit

### Audit Logging (audit_logger Middleware)

**Purpose**: Comprehensive logging of all requests and responses.

**Logged Information**:
- Request prompts (sanitized or full, configurable)
- Response content
- Token usage (prompt_tokens, completion_tokens)
- Latency metrics
- Security level
- Retry attempts
- Correlation IDs (for request tracing)

**Configuration**:
```yaml
llm:
  middleware:
    - type: audit_logger
      include_prompts: false  # false = sanitized, true = full prompts
      include_responses: true
      log_level: INFO
```

**Output Location**: `logs/run_*.jsonl` (JSONL format)

**Example Log Entry**:
```json
{
  "timestamp": "2025-10-26T10:30:45.123Z",
  "run_id": "exp-2025-10-26-001",
  "row_id": 42,
  "event": "llm_request",
  "security_level": "OFFICIAL",
  "prompt_tokens": 150,
  "completion_tokens": 80,
  "latency_ms": 1234,
  "cost": 0.0023
}
```

**Use Cases**:
- Compliance audits
- Cost tracking
- Performance monitoring
- Incident investigation

**Full Documentation**: [Audit Logger in Plugin Catalogue](../plugins/overview.md#example-audit-logger)

---

### Health Monitoring (health_monitor Middleware)

**Purpose**: Track LLM API health and performance over time.

**Metrics**:
- Success rate (successful requests / total requests)
- Average latency (milliseconds)
- Token usage trends
- Error rates by type (timeout, rate limit, auth failure)

**Configuration**:
```yaml
llm:
  middleware:
    - type: health_monitor
      heartbeat_interval: 60  # seconds
      log_level: INFO
```

**Use Cases**:
- Detecting LLM API degradation
- Capacity planning
- SLA monitoring

**Full Documentation**: [Health Monitor in Plugin Catalogue](../plugins/overview.md#example-health-monitor)

---

## Quick Start: Production Configuration

Complete security-hardened configuration for production use:

```yaml
# Production-ready configuration with all security controls
experiment:
  name: secure_production_experiment

  datasource:
    type: azure_blob
    container: production-data
    path: experiments/input.csv
    security_level: PROTECTED  # Match your data sensitivity

  llm:
    type: azure_openai
    endpoint: ${AZURE_OPENAI_ENDPOINT}
    api_key: ${AZURE_OPENAI_KEY}
    deployment_name: gpt-4
    security_level: PROTECTED

    middleware:
      # Layer 1: Block PII
      - type: pii_shield
        on_violation: abort
        patterns: [email, ssn, credit_card, phone, au_tfn, au_medicare]

      # Layer 2: Block classified markings
      - type: classified_material
        on_violation: abort
        markings: [SECRET, TOP SECRET, PROTECTED, CONFIDENTIAL]

      # Layer 3: Block banned terms
      - type: prompt_shield
        on_violation: abort
        banned_terms: [internal-only, do-not-distribute]

      # Layer 4: External content safety
      - type: azure_content_safety
        endpoint: ${AZURE_CONTENT_SAFETY_ENDPOINT}
        api_key: ${AZURE_CONTENT_SAFETY_KEY}
        severity_threshold: medium
        on_violation: abort

      # Layer 5: Audit logging
      - type: audit_logger
        include_prompts: false  # Sanitized prompts only
        include_responses: true

      # Layer 6: Health monitoring
      - type: health_monitor
        heartbeat_interval: 60

  sinks:
    # Sanitized CSV output (automatic formula protection)
    - type: csv
      path: outputs/results.csv
      security_level: PROTECTED

    # Signed tamper-evident bundle
    - type: signed_artifact
      algorithm: HMAC-SHA256
      key_path: keys/signing.key
      output_path: outputs/signed_bundle.tar.gz
      security_level: PROTECTED
      consumes: [csv]  # Bundle includes CSV
```

**What This Configuration Provides**:
- ✅ PII detection (6 pattern types)
- ✅ Classified material blocking
- ✅ Custom term filtering
- ✅ External content safety validation
- ✅ Comprehensive audit logging
- ✅ Performance monitoring
- ✅ Formula injection prevention (automatic)
- ✅ Tamper-evident artifacts
- ✅ Bell-LaPadula MLS enforcement (PROTECTED level)

**Next Steps**:
1. Replace `${AZURE_*}` environment variables with actual values
2. Create signing key: `openssl rand -hex 32 > keys/signing.key`
3. Adjust `security_level` to match your data classification
4. Test with `--head 5` before full run

---

## Security Controls Summary

### Defense-in-Depth Layers

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Bell-LaPadula MLS (Data Classification)      │
│  → Prevents unauthorized access to high-classified data │
└───────────────────┬─────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 2: Content Filtering (Middleware)                │
│  → PII detection, classified markings, banned terms     │
└───────────────────┬─────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 3: External Validation (Azure Content Safety)    │
│  → Hate speech, violence, profanity detection          │
└───────────────────┬─────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 4: Output Protection (Sanitization + Signing)    │
│  → Formula injection prevention, tamper evidence        │
└───────────────────┬─────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Layer 5: Audit & Monitoring (Logging + Health)        │
│  → Comprehensive audit trail, performance tracking      │
└─────────────────────────────────────────────────────────┘
```

### When to Use Each Control

| Control | Use When | Skip When |
|---------|----------|-----------|
| **PII Shield** | Handling customer data, healthcare, financial | Public data only (marketing copy) |
| **Classified Material** | Government, defense, regulated industries | No classified markings expected |
| **Prompt Shield** | Organization-specific policies | No custom term restrictions |
| **Azure Content Safety** | User-generated content, public-facing | Internal business workflows |
| **Formula Sanitization** | Any CSV/Excel output | N/A (always enabled) |
| **Artifact Signing** | Compliance requirements (HIPAA, PCI-DSS) | Testing/development |
| **Audit Logging** | Production environments | Local development only |
| **Health Monitoring** | Production environments | Single-run experiments |

---

## Related Documentation

- **[Security Model](security-model.md)** - Bell-LaPadula MLS data classification
- **[Configuration Guide](configuration.md)** - YAML configuration reference
- **[Plugin Catalogue](../plugins/overview.md)** - Complete middleware documentation
- **[Architecture > Security Policy](../architecture/security-policy.md)** - Design principles and ADRs

---

## Troubleshooting

### "PII detected" but I don't see any PII

**Cause**: False positive (e.g., "123-45-6789" could be an order number, not SSN)

**Solutions**:
1. **Temporarily use `on_violation: log`** to identify the pattern:
   ```yaml
   - type: pii_shield
     on_violation: log  # Logs detection but continues
   ```
2. **Exclude specific patterns**:
   ```yaml
   - type: pii_shield
     patterns: [email, credit_card]  # Exclude SSN if causing issues
   ```
3. **Sanitize input data** before running experiment

### "SecurityCriticalError" in middleware

**Cause**: Security middleware detected policy violation

**Debugging**:
1. Check `logs/run_*.jsonl` for detailed error:
   ```bash
   tail -f logs/run_*.jsonl | grep ERROR
   ```
2. Review the failing row's input data
3. Verify middleware configuration matches your data

**Solutions**:
- Adjust `on_violation` policy (abort → log for debugging)
- Adjust detection thresholds (e.g., Azure Content Safety severity)
- Sanitize input data before processing

### "Insufficient clearance" error

**Cause**: This is Bell-LaPadula MLS error (data classification), not middleware

**Solution**: See [Security Model Troubleshooting](security-model.md#troubleshooting)

---

!!! success "Security Controls Summary"
    Elspeth provides **5 layers of defense-in-depth** security:

    1. ✅ **Data Classification** (Bell-LaPadula MLS)
    2. ✅ **Content Filtering** (PII, classified markings, banned terms)
    3. ✅ **External Validation** (Azure Content Safety)
    4. ✅ **Output Protection** (formula sanitization, signing)
    5. ✅ **Audit & Monitoring** (logging, health tracking)

    Start with the [Quick Start configuration](#quick-start-production-configuration) and adjust to your security requirements!
