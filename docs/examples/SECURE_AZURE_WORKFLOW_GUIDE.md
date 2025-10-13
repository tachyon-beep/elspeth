# Secure Azure Workflow Guide

This guide demonstrates how to set up a complete end-to-end secure LLM evaluation pipeline using Elspeth with Azure services.

## Overview

The workflow implements a comprehensive security-first approach:

```
CSV (Azure Blob) → Prompt Assembly → Security Filters → LLM → JSON Validation → Statistics → Azure DevOps
```

## Architecture Diagram

```
┌─────────────────────┐
│  Azure Blob Storage │
│   (CSV Input Data)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Datasource Plugin  │
│    (csv_blob)       │
│  • Loads CSV        │
│  • Adds security    │
│    classification   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Prompt Assembly    │
│  • Template engine  │
│  • Row data inject  │
│  • Jinja2 rendering │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────┐
│     Security Middleware Stack    │
├─────────────────────────────────┤
│ 1. Azure Content Safety         │
│    • Hate, Violence, SelfHarm   │
│    • Sexual content screening   │
├─────────────────────────────────┤
│ 2. PII Shield                   │
│    • US: SSN, phone, etc.       │
│    • UK: NI numbers             │
│    • AU: TFN, ABN, Medicare     │
├─────────────────────────────────┤
│ 3. Classified Material Filter   │
│    • SECRET, TOP SECRET         │
│    • PROTECTED, CONFIDENTIAL    │
│    • TS//SCI, NOFORN, etc.      │
├─────────────────────────────────┤
│ 4. Audit Logger                 │
│    • Request/response logs      │
│    • Security-aware filtering   │
├─────────────────────────────────┤
│ 5. Health Monitor               │
│    • Latency tracking           │
│    • Failure rate monitoring    │
└──────────┬──────────────────────┘
           │
           │ ✅ Passed all filters
           ▼
┌─────────────────────┐
│   Azure OpenAI      │
│   (gpt-4 / gpt-35)  │
│   • Temperature     │
│   • Max tokens      │
│   • Response gen    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  JSON Validation    │
│  • Ensure valid     │
│  • Check structure  │
│  • Extract fields   │
└──────────┬──────────┘
           │
           ├─── ✅ Valid JSON
           │
           ▼
┌─────────────────────┐
│  Row Plugins        │
│  • Score extraction │
│  • Metric compute   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Aggregator Plugins │
│  • Statistics       │
│  • Distribution     │
│  • Cost tracking    │
│  • Latency summary  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────┐
│       Output Sinks               │
├─────────────────────────────────┤
│ 1. CSV Export (local)           │
│    • Results with metrics       │
│    • Formula sanitization       │
├─────────────────────────────────┤
│ 2. Analytics Report             │
│    • JSON + Markdown            │
│    • Statistical summaries      │
├─────────────────────────────────┤
│ 3. Enhanced Visualizations      │
│    • Violin plots               │
│    • Heatmaps                   │
│    • Distribution overlays      │
├─────────────────────────────────┤
│ 4. Azure DevOps Repository      │
│    • Git commit results         │
│    • Timestamped paths          │
│    • Full audit trail           │
└─────────────────────────────────┘
```

## Complete Example Configuration

See: `config/sample_suite/secure_azure_workflow.yaml`

## Step-by-Step Setup

### 1. Prerequisites

**Azure Resources:**
- Azure Storage Account (for CSV input)
- Azure OpenAI Service (GPT-4 or GPT-3.5 deployment)
- Azure Content Safety resource
- Azure DevOps organization and repo

**Environment Variables:**
```bash
export AZURE_CONTENT_SAFETY_KEY="your-content-safety-key"
export AZURE_DEVOPS_PAT="your-personal-access-token"
```

**Azure OpenAI Configuration:**
Create `~/.elspeth/azure_openai.json`:
```json
{
  "azure_endpoint": "https://your-resource.openai.azure.com",
  "api_key": "your-api-key",
  "api_version": "2024-02-15-preview"
}
```

### 2. Prepare Input Data

**CSV Format** (in Azure Blob Storage):
```csv
customer_id,feedback_text,category
CUST001,"Great service, very helpful!",support
CUST002,"Product quality could be better",product
CUST003,"Fast shipping, thanks!",logistics
```

**Upload to Azure Blob:**
```bash
az storage blob upload \
  --account-name mystorageaccount \
  --container-name experiments \
  --name input_data.csv \
  --file local_data.csv
```

### 3. Configure the Workflow

**Datasource Configuration:**
```yaml
datasource:
  type: csv_blob
  security_level: confidential
  path: "https://mystorageaccount.blob.core.windows.net/experiments/input_data.csv"
```

**LLM with Security Middleware:**
```yaml
llm:
  type: azure_openai
  security_level: confidential
  config: azure_openai_config
  deployment: gpt-4

  middleware:
    - type: azure_content_safety
      endpoint: "https://my-content-safety.cognitiveservices.azure.com"
      key_env: AZURE_CONTENT_SAFETY_KEY
      on_violation: abort

    - type: pii_shield
      include_defaults: true
      on_violation: abort

    - type: classified_material
      include_defaults: true
      on_violation: abort
```

**Prompt Template:**
```yaml
prompt_template: |
  Analyze the following customer feedback:

  Customer ID: {{ customer_id }}
  Feedback: {{ feedback_text }}
  Category: {{ category }}

  Respond with JSON:
  {
    "sentiment": "positive|negative|neutral",
    "key_themes": ["theme1", "theme2"],
    "priority": "high|medium|low"
  }
```

**Validation and Sinks:**
```yaml
plugins:
  validation:
    - type: json
      ensure_object: true

  aggregators:
    - type: score_stats
    - type: cost_summary
    - type: latency_summary

sinks:
  - type: csv
    path: "outputs/results.csv"

  - type: azure_devops_repo
    organization: "myorg"
    project: "llm-experiments"
    repo: "experiment-results"
    token_env: AZURE_DEVOPS_PAT
```

### 4. Run the Workflow

```bash
python -m elspeth.cli \
  --settings config/sample_suite/secure_azure_workflow.yaml \
  --suite-root config/sample_suite \
  --reports-dir outputs/secure_workflow_reports \
  --live-outputs
```

### 5. Monitor Progress

**Console Output:**
```
[INFO] Loading datasource: csv_blob
[INFO] Loaded 100 rows from Azure Blob Storage
[INFO] Processing experiment: customer_feedback_analysis
[INFO] Row 1/100: Passed security filters
[INFO] Row 2/100: Passed security filters
[INFO] Row 3/100: BLOCKED by pii_shield (detected: email)
[INFO] Row 4/100: BLOCKED by classified_material (detected: SECRET)
[INFO] Row 5/100: Passed security filters
...
[INFO] Completed: 95 successful, 5 blocked
[INFO] Computing statistics...
[INFO] Generating visualizations...
[INFO] Committing to Azure DevOps...
[INFO] ✓ Workflow complete
```

## Security Features

### 1. Azure Content Safety Integration

Screens for harmful content before sending to LLM:
- **Categories**: Hate, Violence, SelfHarm, Sexual
- **Severity Threshold**: 0-7 (configurable)
- **Actions**: abort (block), mask (sanitize), log (record only)

### 2. PII Detection

Detects and blocks personal information:

**US Patterns:**
- Social Security Numbers (SSN)
- Phone numbers
- Email addresses
- Credit card numbers
- Passport numbers

**UK Patterns:**
- National Insurance (NI) numbers

**Australian Patterns:**
- Tax File Numbers (TFN)
- Australian Business Numbers (ABN)
- Australian Company Numbers (ACN)
- Medicare card numbers
- Phone numbers (landline + mobile)
- Passport numbers
- Driver's licenses (NSW, VIC, QLD)

### 3. Classified Material Detection

Detects government classification markings:
- SECRET, TOP SECRET, CONFIDENTIAL
- PROTECTED, RESTRICTED
- CABINET CODEWORD
- TS//SCI, TS/SCI
- NOFORN (No Foreign Nationals)
- FVEY (Five Eyes)
- ORCON (Originator Controlled)
- FOUO (For Official Use Only)
- CUI (Controlled Unclassified Information)
- OFFICIAL-SENSITIVE

### 4. Security Level Propagation

Security classifications flow through the entire pipeline:
```
Datasource (confidential)
  → LLM (confidential)
    → Artifacts (confidential)
      → Sinks (respects classification)
```

## Data Flow Details

### Successful Row Processing

```
1. Load row from CSV
   ↓
2. Assemble prompt with row data
   ↓
3. Azure Content Safety screening → ✅ PASS
   ↓
4. PII Shield check → ✅ PASS (no PII detected)
   ↓
5. Classified Material check → ✅ PASS (no markings)
   ↓
6. Audit log request
   ↓
7. Send to Azure OpenAI
   ↓
8. Receive JSON response
   ↓
9. Validate JSON structure → ✅ VALID
   ↓
10. Extract scores and metrics
    ↓
11. Add to successful results pool
```

### Blocked Row Processing

```
1. Load row from CSV
   ↓
2. Assemble prompt with row data
   ↓
3. Azure Content Safety screening → ✅ PASS
   ↓
4. PII Shield check → ❌ FAIL (detected: email, phone)
   ↓
5. BLOCK request (never sent to LLM)
   ↓
6. Audit log blocking event
   ↓
7. Add to failures with reason
```

### Statistics and Reporting

Both successful and failed rows are tracked:

**Successful Rows:**
- Score statistics (mean, std, min, max)
- Distribution analysis
- Cost and latency metrics
- Sentiment analysis
- Theme extraction

**Failed Rows:**
- Failure reason (which filter blocked)
- PII types detected
- Classification markings found
- Content safety violations

## Output Artifacts

### 1. CSV Export

**Location**: `outputs/secure_workflow/results.csv`

**Contents**:
```csv
customer_id,feedback_text,sentiment,priority,llm_response,cost_usd,latency_ms
CUST001,"Great service!",positive,low,"{...}",0.0042,1250
CUST002,"Good product",positive,medium,"{...}",0.0039,1180
```

### 2. Analytics Reports

**Location**: `outputs/secure_workflow/analytics/`

**Files**:
- `summary.json` - Machine-readable statistics
- `summary.md` - Human-readable report
- `manifest.json` - Provenance and metadata

**Example JSON**:
```json
{
  "experiment": "customer_feedback_analysis",
  "total_rows": 100,
  "successful": 95,
  "failed": 5,
  "security_level": "confidential",
  "statistics": {
    "sentiment_score": {
      "mean": 0.82,
      "std": 0.15,
      "min": 0.45,
      "max": 0.98
    }
  },
  "cost": {
    "total_usd": 0.38,
    "prompt_tokens": 8500,
    "completion_tokens": 2100
  }
}
```

### 3. Visualizations

**Location**: `outputs/secure_workflow/charts/`

**Generated Charts**:
- `violin.png` / `violin.html` - Score distributions
- `heatmap.png` / `heatmap.html` - Correlation matrix
- `distribution.png` / `distribution.html` - Histogram overlays

### 4. Azure DevOps Repository

**Location**: `https://dev.azure.com/myorg/llm-experiments/_git/experiment-results`

**Commit Structure**:
```
workflows/
└── secure_azure_workflow/
    └── customer_feedback_analysis/
        └── 2025-01-15T14-30-00/
            ├── results.csv
            ├── summary.json
            ├── summary.md
            ├── charts/
            │   ├── violin.png
            │   ├── heatmap.png
            │   └── distribution.png
            └── manifest.json
```

**Commit Message**:
```
Secure workflow results: customer_feedback_analysis

- Total rows: 100
- Successful: 95
- Failed: 5
- Security level: confidential
```

## Handling Failures

### Security Filter Blocks

When a row is blocked by security filters:

1. **Never sent to LLM** - Cost savings + security
2. **Logged with reason** - Audit trail maintained
3. **Added to failures** - Tracked in statistics
4. **Available in reports** - Failure analysis possible

**Example failure record**:
```json
{
  "row_id": "CUST003",
  "blocked_by": "pii_shield",
  "reason": "Prompt contains PII: email, phone_us",
  "detected_patterns": ["john@example.com", "555-123-4567"]
}
```

### JSON Validation Failures

When LLM returns invalid JSON:

1. **Validation plugin detects** - Structure mismatch
2. **Logged as validation failure** - Separate from security
3. **Can retry** - If retry policy configured
4. **Tracked separately** - Different failure category

### Network/API Failures

When Azure services are unavailable:

1. **Content Safety**: `on_error: skip` - Continue without check
2. **LLM calls**: Retry with backoff (configurable)
3. **Sinks**: `on_error: skip` - Continue to other sinks

## Advanced Configurations

### Custom Australian Patterns

Add organization-specific Australian identifiers:

```yaml
llm:
  middleware:
    - type: pii_shield
      patterns:
        # Australian company-specific patterns
        - name: acme_employee_id
          regex: '\bACME-EMP-\d{6}\b'
        - name: acme_customer_id
          regex: '\bCUST\d{9}\b'
        # Extra Medicare validation
        - name: medicare_strict
          regex: '\b[2-6]\d{9}\b'
      include_defaults: true
      on_violation: mask
      mask: "[ACME-PII]"
```

### Multi-Region Classification

Combine US, UK, and Australian classifications:

```yaml
llm:
  middleware:
    - type: classified_material
      classification_markings:
        # Australian classifications
        - "PROTECTED"
        - "PROTECTED: CABINET"
        - "OFFICIAL: Sensitive"
        # US classifications (included in defaults)
        # UK classifications
        - "OFFICIAL-SENSITIVE"
        - "SECRET-STRAP1"
      include_defaults: true
      on_violation: abort
```

### Differential Security Levels

Run experiments with different security postures:

```yaml
experiments:
  # High security for sensitive data
  - name: confidential_feedback
    datasource:
      security_level: confidential
    llm:
      security_level: confidential
      middleware:
        - type: pii_shield
          on_violation: abort  # Strict

  # Lower security for public data
  - name: public_feedback
    datasource:
      security_level: public
    llm:
      security_level: public
      middleware:
        - type: pii_shield
          on_violation: mask  # Permissive
```

## Troubleshooting

### Issue: Rows being blocked unexpectedly

**Check**:
```bash
# Review audit logs
grep "pii_shield" outputs/logs/audit.log
grep "classified_material" outputs/logs/audit.log
```

**Solution**: Adjust middleware `on_violation` from `abort` to `mask` or `log` for testing.

### Issue: Azure Content Safety blocking too much

**Check**: Current severity threshold

**Solution**: Increase threshold (4 → 6) or disable specific categories:
```yaml
middleware:
  - type: azure_content_safety
    severity_threshold: 6  # More permissive
    categories: ["Hate", "Violence"]  # Only check these
```

### Issue: False positive PII detection

**Check**: Which patterns are matching

**Solution**: Disable specific patterns:
```yaml
middleware:
  - type: pii_shield
    patterns: []  # No custom patterns
    include_defaults: false  # Start fresh
    # Then add only patterns you need
```

### Issue: Azure DevOps commits failing

**Check**:
1. PAT has correct permissions (Code: Read, Write)
2. Branch exists
3. Path template resolves correctly

**Solution**:
```yaml
sinks:
  - type: azure_devops_repo
    dry_run: true  # Test without actually committing
```

## Best Practices

1. **Start with `dry_run: true`** - Test Azure DevOps sink before live commits
2. **Use `on_error: skip`** for non-critical middleware - Ensures pipeline continues
3. **Set `include_prompts: true`** in audit logger - Full audit trail for compliance
4. **Use prompt packs** - Reusable security configurations across experiments
5. **Monitor costs** - Enable `cost_summary` aggregator to track spending
6. **Version control configurations** - Track changes to security policies
7. **Test with small datasets first** - Use `--head 10` flag for testing

## Security Checklist

Before running in production:

- [ ] Azure Content Safety configured with appropriate threshold
- [ ] PII Shield enabled with all relevant regional patterns
- [ ] Classified Material filter enabled with organization markings
- [ ] Audit logging enabled with `include_prompts: true`
- [ ] Security levels set correctly on datasource and LLM
- [ ] Azure DevOps PAT secured (not in config file)
- [ ] Content Safety key secured (in environment variable)
- [ ] Azure OpenAI key secured (in separate config file)
- [ ] Formula sanitization enabled on CSV/Excel sinks
- [ ] Test suite run with representative data samples
- [ ] Failure handling tested (blocked rows, validation errors)
- [ ] Output artifacts reviewed for sensitive data leakage

## Performance Tuning

### Concurrency

Process multiple rows in parallel:
```yaml
experiments:
  - name: my_experiment
    concurrency: 5  # Process 5 rows simultaneously
```

### Rate Limiting

Control request rate to avoid throttling:
```yaml
llm:
  rate_limit:
    type: adaptive
    requests_per_minute: 60
    tokens_per_minute: 90000
```

### Caching

Reduce duplicate API calls:
```yaml
llm:
  middleware:
    - type: prompt_hash_cache  # TODO: Not yet implemented
      ttl: 3600
      hit_policy: reuse
```

## Additional Resources

- **Plugin Catalogue**: `docs/architecture/plugin-catalogue.md`
- **Security Controls**: `docs/architecture/security-controls.md`
- **Configuration Merge**: `docs/architecture/configuration-merge.md`
- **Azure Setup Guide**: `docs/deployment/azure-setup.md` (TODO)
- **Middleware Documentation**: `docs/middleware/README.md` (TODO)

## Example Output

### Console Summary

```
=================================================================
Experiment: customer_feedback_analysis
=================================================================
Input: Azure Blob Storage (100 rows)
Security Level: confidential

Processing Pipeline:
  ✓ Azure Content Safety: 98 passed, 2 blocked
  ✓ PII Shield: 95 passed, 3 blocked
  ✓ Classified Material: 100 passed, 0 blocked
  ✓ LLM Calls: 95 successful
  ✓ JSON Validation: 95 valid, 0 invalid

Statistics:
  Total Rows: 100
  Successful: 95 (95%)
  Blocked: 5 (5%)
    - Content Safety: 2
    - PII Shield: 3

  Sentiment Distribution:
    Positive: 72 (75.8%)
    Neutral: 18 (18.9%)
    Negative: 5 (5.3%)

  Performance:
    Total Cost: $0.38 USD
    Avg Latency: 1.25s
    Total Duration: 2m 15s

Outputs Generated:
  ✓ CSV: outputs/secure_workflow/results.csv
  ✓ Analytics: outputs/secure_workflow/analytics/summary.json
  ✓ Visualizations: outputs/secure_workflow/charts/*.png
  ✓ Azure DevOps: Committed to main branch

=================================================================
✓ Workflow Complete
=================================================================
```

---

**This workflow demonstrates Elspeth's capability for production-grade secure LLM evaluation pipelines with comprehensive audit trails, multi-region PII detection, and enterprise-ready output management.**
