# Australian Government Security Controls

## Overview

Elspeth was designed to support **secure LLM experimentation within Australian government contexts**, with specific controls for Australian PII, government classifications, and compliance requirements.

## Australian PII Protection

### Supported Australian PII Types

The `pii_shield` middleware detects and protects all critical Australian personally identifiable information:

#### Tax & Business Identifiers
- **Tax File Number (TFN)** - 9 digits (123 456 789)
- **Australian Business Number (ABN)** - 11 digits (51 824 753 556)
- **Australian Company Number (ACN)** - 9 digits (123 456 789)

#### Healthcare
- **Medicare Number** - 10 digits (1234 56789 1)

#### Contact Information
- **Australian Landline** - Local/international formats
  - `(02) 1234 5678`
  - `02 1234 5678`
  - `+61 2 1234 5678`
- **Australian Mobile** - 04xx series
  - `0412 345 678`
  - `+61 412 345 678`

#### Identity Documents
- **Australian Passport** - 1 letter + 7 digits (N1234567)
- **Driver's Licenses**:
  - NSW: 8 digits
  - VIC: 10 digits
  - QLD: 9 digits

### Configuration Example

```yaml
llm:
  security_level: "PROTECTED"
  middleware:
    # Block Australian PII before sending to LLM
    - type: pii_shield
      on_violation: abort
      mask: "[AUSTRALIAN PII REDACTED]"
      include_defaults: true
```

## Government Classification Protection

### Supported Classification Markings

The `classified_material` middleware detects Australian government and international classification markings:

#### Australian Government (PSPF)
- `OFFICIAL: Sensitive` (Correct format with colon and space)
- `OFFICIAL-SENSITIVE` (Legacy format - hyphenated)
- `PROTECTED`
- `SECRET`
- `TOP SECRET`
- `CABINET`
- `CABINET CODEWORD`
- `PROTECTED: CABINET`
- `PROTECTED: CABINET CODEWORD`

#### Australian Caveats
- `AUSTEO` (Australian Eyes Only)
- `AGAO` (Australian Government Access Only)
- `REL TO` (Release To - with countries)
- `REL AUS` (Release to Australia)
- `REL FVEY` (Release to Five Eyes)

#### US Classifications
- `TS//SCI` (Top Secret / Sensitive Compartmented Information)
- `TS/SCI`
- `NOFORN` (No Foreign Nationals)
- `ORCON` (Originator Controlled)
- `RELIDO` (Release to...)
- `FOUO` (For Official Use Only)
- `CUI` (Controlled Unclassified Information)

#### UK/Five Eyes
- `FVEY` (Five Eyes)
- `UK EYES ONLY`
- `CANADIAN EYES ONLY`

#### Legacy/Other
- `CONFIDENTIAL`
- `RESTRICTED`

### Configuration Example

```yaml
llm:
  security_level: "PROTECTED"
  middleware:
    # Prevent classified material in prompts
    - type: classified_material
      on_violation: abort
      case_sensitive: false
      include_defaults: true
      classification_markings:
        - "PROTECTED: LEGAL"
        - "IN CONFIDENCE"
```

## Azure Government Cloud Integration

### Azure ML Telemetry

The `azure_environment` middleware integrates with Azure ML for government compliance tracking:

```yaml
llm:
  middleware:
    - type: azure_environment
      enable_run_logging: true
      log_prompts: false  # Never log prompts with PROTECTED data
      log_metrics: true
      severity_threshold: "WARNING"
      on_error: skip
```

**Features**:
- Run context detection for Azure Government Cloud
- Classification-aware logging (never logs sensitive content)
- Metric aggregation for cost tracking
- Experiment lineage tracking

### Azure Content Safety

The `azure_content_safety` middleware uses Azure AI Services for content screening:

```yaml
llm:
  middleware:
    - type: azure_content_safety
      endpoint: "https://your-content-safety.australiaeast.cognitiveservices.azure.com/"
      key_env: "AZURE_CONTENT_SAFETY_KEY"
      severity_threshold: 4
      on_violation: abort
      on_error: skip
```

## Complete Security Stack for Australian Government

### Recommended Configuration

```yaml
suite:
  defaults:
    # Classification-aware configuration
    security_level: "PROTECTED"

    datasource:
      type: "csv_blob"
      path: "abfs://experiments@storageaccount.blob.core.windows.net/data.csv"
      security_level: "PROTECTED"

    llm:
      type: "azure_openai"
      config: "azure_gov_au"
      deployment: "gpt-4-gov"
      temperature: 0.0
      max_tokens: 2000
      security_level: "PROTECTED"

      # Comprehensive middleware stack
      middleware:
        # 1. Block Australian PII
        - type: pii_shield
          on_violation: abort
          include_defaults: true

        # 2. Block classification markings
        - type: classified_material
          on_violation: abort
          include_defaults: true

        # 3. Azure Content Safety screening
        - type: azure_content_safety
          endpoint: "${AZURE_CONTENT_SAFETY_ENDPOINT}"
          key_env: "AZURE_CONTENT_SAFETY_KEY"
          severity_threshold: 2
          on_violation: abort

        # 4. Audit logging (classification-aware)
        - type: audit_logger
          include_prompts: false  # Never log prompts at PROTECTED level
          channel: "elspeth.gov.audit"

        # 5. Health monitoring
        - type: health_monitor
          heartbeat_interval: 60.0
          include_latency: true

        # 6. Azure ML telemetry
        - type: azure_environment
          log_prompts: false
          log_metrics: true
          on_error: skip

experiments:
  - name: "baseline_experiment"
    is_baseline: true
    description: "PROTECTED: Baseline evaluation"
```

## Security Guarantees

### 1. PII Never Reaches LLM

The `pii_shield` middleware operates in the `before_request` hook, ensuring:
- Australian PII is detected **before** prompts are sent to Azure OpenAI
- Three modes: `abort` (block request), `mask` (redact PII), `log` (warn only)
- All 19 PII patterns checked on every request

### 2. Classification Markings Blocked

The `classified_material` middleware prevents accidental inclusion of classified markings:
- Detects 17 government classification markings
- Case-insensitive matching by default
- Custom markings supported for agency-specific classifications

### 3. Artifact Security Levels

All outputs respect classification inheritance:
- Sinks cannot consume artifacts from higher security levels
- Security level flows: datasource + LLM → experiment → artifacts
- Artifact pipeline enforces "read-up" restrictions

### 4. Audit Trail

Comprehensive audit logging for compliance:
- Request/response logging via `audit_logger` middleware
- Classification-aware logging (respects `include_prompts: false`)
- Azure ML telemetry integration
- Signed artifacts with HMAC for integrity

### 5. Formula Injection Protection

CSV/Excel sinks sanitize formulas to prevent code execution:
- Configurable via `sanitize_formulas` and `sanitize_guard`
- Guards against `=`, `+`, `-`, `@` formula prefixes
- Protects downstream analysts from malicious content

## Compliance Features

### 1. Determinism Levels

Experiments can declare reproducibility guarantees:
- `guaranteed` - Fully deterministic (temperature=0, seed set)
- `expected` - Should be reproducible but may vary slightly
- `nondeterministic` - Sampling/stochastic processes

### 2. Provenance Tracking

Every plugin receives `PluginContext` with:
- `security_level` - Classification of data being processed
- `provenance` - Chain of data origins
- `plugin_kind` - Type of plugin (datasource, llm, sink, etc.)
- `plugin_name` - Specific plugin instance

### 3. Cost Tracking

Government-mandated cost visibility:
- Token-level cost tracking via `CostSummaryAggregator`
- Fixed-price and usage-based cost trackers
- Per-experiment cost breakdowns in reports

### 4. Rate Limiting

Protect against runaway costs and abuse:
- `fixed_window` - Simple request quotas
- `adaptive` - Token-aware throttling
- Configurable per-experiment and per-LLM

## Testing & Validation

### Security Filter Test Coverage

- **42 middleware security tests**
  - 14 general/US PII tests
  - 11 Australian PII tests
  - 17 classification marking tests
- **18 total PII patterns** (General: 3, US: 4, UK: 1, Australian: 10)
- **26 classification markings** (Australian PSPF: 9, Australian Caveats: 5, US: 7, Five Eyes: 3, Legacy: 2)
- **429 total passing tests**
- **88% test coverage**

### Validation Before Deployment

```bash
# Run security-focused tests
python -m pytest tests/test_middleware_security_filters.py -v

# Verify PII patterns
python -m pytest -k "australian" -v

# Check classification filtering
python -m pytest -k "classified" -v
```

## References

- **Plugin Catalogue**: `docs/architecture/plugin-catalogue.md`
- **Security Controls**: `docs/architecture/security-controls.md`
- **Threat Model**: `docs/architecture/threat-surfaces.md`
- **Control Inventory**: `docs/architecture/CONTROL_INVENTORY.md`
- **Configuration Guide**: `docs/architecture/configuration-merge.md`

## Contact & Support

For Australian government-specific deployment guidance:
- Review `docs/reporting-and-suite-management.md` for operational procedures
- See `docs/end_to_end_scenarios.md` for common workflow patterns
- Check `CLAUDE.md` for development guidelines
