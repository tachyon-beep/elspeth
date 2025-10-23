# Production Configuration Templates

This directory contains secure configuration templates for production use of Elspeth.

## Templates

### production_suite.yaml
**Use Case:** Multi-experiment suites for production workloads

**Security Mode:** STRICT (set `ELSPETH_SECURE_MODE=strict`)

**Features:**
- Complete security configuration (all required fields)
- Azure Blob Storage datasource with audit retention
- Real LLM (Azure OpenAI) - no mocks
- Comprehensive middleware (audit logger, prompt shield, health monitor)
- Formula sanitization enforced
- Rate limiting and cost tracking
- Checkpoints and retry logic
- Reproducibility bundle for complete audit trail

**When to Use:**
- Production deployments
- Compliance-sensitive workloads
- Multi-experiment evaluation suites
- Long-running batch processing

### production_experiment.yaml
**Use Case:** Single experiment with production-grade security

**Security Mode:** STANDARD (default)

**Features:**
- Required security configurations
- Local CSV datasource with audit retention
- Real LLM (Azure OpenAI)
- Audit logging middleware
- Formula sanitization enabled
- Basic rate limiting
- CSV and analytics report outputs

**When to Use:**
- Individual production experiments
- Quick production runs
- Testing production configurations
- Standard operational work

### retrieval_pgvector_example.yaml
**Use Case:** Demonstrate pgvector retrieval with a bounded connection timeout.

**Notes:**
- Shows `connect_timeout` to avoid long DB connect stalls.
- Reference-only; merge fields into your suite configs as needed.

### retrieval_azure_search_example.yaml
**Use Case:** Demonstrate Azure Cognitive Search retrieval with a per-request timeout.

**Notes:**
- Shows `request_timeout` (alias `timeout`) to bound query latency.
- Reference-only; merge fields into your suite configs as needed.

## Quick Start

### 1. Copy Template
```bash
# For suite
cp config/templates/production_suite.yaml config/my_production_suite.yaml

# For single experiment
cp config/templates/production_experiment.yaml config/my_experiment.yaml
```

### 2. Configure Security Mode
```bash
# For STRICT mode (production)
export ELSPETH_SECURE_MODE=strict

# For STANDARD mode (default)
export ELSPETH_SECURE_MODE=standard

# For DEVELOPMENT mode (testing only)
export ELSPETH_SECURE_MODE=development
```

### 3. Set Environment Variables
```bash
export AZURE_OPENAI_API_KEY="your-api-key"
# Add other required environment variables
```

### 4. Customize Configuration
Edit your copied configuration file:
- Update `security_level` to match your data classification
- Configure datasource path/container
- Set LLM endpoint and deployment
- Adjust rate limits and concurrency
- Configure output paths

### 5. Test Run
```bash
# Test with small dataset first
python -m elspeth.cli \
  --settings config/my_experiment.yaml \
  --head 5 \
  --live-outputs
```

### 6. Production Run
```bash
# Full run after testing
python -m elspeth.cli \
  --settings config/my_experiment.yaml \
  --live-outputs
```

## Security Modes

### STRICT Mode
**Environment:** `ELSPETH_SECURE_MODE=strict`

**Requirements:**
- ✅ `security_level` REQUIRED for all datasources, LLMs, sinks
- ✅ `retain_local=true` REQUIRED for datasources
- ❌ Mock LLMs NOT ALLOWED
- ✅ Formula sanitization REQUIRED (enabled by default)
- ✅ Audit logging STRONGLY RECOMMENDED

**Use When:**
- Production deployments
- Compliance-sensitive data
- Formal testing/validation
- ATO/security audit requirements

### STANDARD Mode (Default)
**Environment:** `ELSPETH_SECURE_MODE=standard` (or unset)

**Requirements:**
- ✅ `security_level` REQUIRED for all datasources, LLMs, sinks
- ⚠️ `retain_local` RECOMMENDED (warns if False)
- ⚠️ Mock LLMs ALLOWED (warns)
- ✅ Formula sanitization ENABLED by default (warns if disabled)

**Use When:**
- Standard operational work
- Development with real data
- Pre-production testing

### DEVELOPMENT Mode
**Environment:** `ELSPETH_SECURE_MODE=development`

**Requirements:**
- ⚠️ `security_level` OPTIONAL (defaults applied)
- ⚠️ `retain_local` OPTIONAL
- ✅ Mock LLMs ALLOWED
- ⚠️ Formula sanitization CAN BE DISABLED

**Use When:**
- Local development
- Testing configurations
- Debugging
- **NOT for production data**

## Configuration Checklist

Before running in production, verify:

### Required Fields
- [ ] `datasource.security_level` set
- [ ] `llm.security_level` set
- [ ] All `sinks[].security_level` set

### Data Retention (STRICT mode)
- [ ] `datasource.retain_local = true`
- [ ] Audit logs enabled (`audit_logger` middleware)
- [ ] Reproducibility bundle configured (for complete audit)

### Security Controls
- [ ] Formula sanitization enabled (default `sanitize_formulas: true`)
- [ ] Prompt shield middleware configured (if needed)
- [ ] Real LLM configured (no mocks in STRICT mode)

### Environment Variables
- [ ] `ELSPETH_SECURE_MODE` set appropriately
- [ ] `AZURE_OPENAI_API_KEY` set
- [ ] Any other API keys/credentials set

### Outputs
- [ ] Output directories exist or will be created
- [ ] Sink error handling configured (`on_error: "raise"`)
- [ ] Audit logs path configured

### Testing
- [ ] Tested with small dataset (`--head 5`)
- [ ] Verified outputs are correct
- [ ] Checked audit logs for completeness

## Common Patterns

### Pattern 1: Multi-Variant Evaluation
```yaml
experiments:
  - name: baseline
    prompts:
      template: "Answer: {question}"

  - name: detailed
    prompts:
      template: "Provide a detailed answer to: {question}"

  - name: concise
    prompts:
      template: "Briefly answer: {question}"
```

### Pattern 2: Staged Processing
```yaml
# First pass: Initial processing
sinks:
  - plugin: csv
    path: "outputs/stage1_results.csv"

# Second pass: Use stage1 as input
datasource:
  plugin: local_csv
  path: "outputs/stage1_results.csv"
```

### Pattern 3: Multiple Output Formats
```yaml
sinks:
  - plugin: csv
    path: "outputs/results.csv"

  - plugin: excel_workbook
    path: "outputs/results.xlsx"

  - plugin: analytics_report
    output_dir: "outputs/reports"
    formats: ["json", "markdown", "html"]

  - plugin: reproducibility_bundle
    output_dir: "outputs/audit"
```

## Troubleshooting

### Error: "missing required 'security_level'"
**Solution:** Add `security_level` to datasource, LLM, or sink configuration.

### Error: "retain_local=False which violates STRICT mode"
**Solution:** Set `retain_local: true` in datasource configuration.

### Error: "Mock LLM not allowed in STRICT mode"
**Solution:** Use real LLM (azure_openai, http_openai) or switch to STANDARD mode.

### Warning: "No 'audit_logger' middleware found"
**Solution:** Add audit_logger to `llm_middlewares` for compliance.

### Error: "sanitize_formulas=False which violates STRICT mode"
**Solution:** Remove `sanitize_formulas: false` (default is true) or switch to STANDARD mode.

## Related Documentation

- [ATO Work Program](../../docs/ATO_REMEDIATION_WORK_PROGRAM.md) - Security requirements
- [Configuration Merge](../../docs/architecture/configuration-security.md#update-2025-10-23-prompt-packs-defaults-and-merge-order) - Config hierarchy
- [Plugin Catalogue](../../docs/architecture/plugin-catalogue.md) - Available plugins
- [Security Controls](../../docs/architecture/security-controls.md) - Security features

## Support

For questions or issues:
1. Check the troubleshooting section above
2. Review [ATO_QUICK_START.md](../../docs/ATO_QUICK_START.md)
3. Run daily verification: `./scripts/daily-verification.sh`
4. Contact the team for assistance
