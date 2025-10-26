# Configuration Guide

Master Elspeth's configuration system to build robust, secure experiment pipelines.

!!! info "Quick Start"
    Start with [First Experiment](../getting-started/first-experiment.md) for a hands-on walkthrough. This guide provides the **complete reference** for configuration options.

---

## Overview

Elspeth experiments are configured using **YAML files** organized in a **suite structure**:

```
config/my_suite/
├── settings.yaml              # Suite-level settings
├── experiments/
│   ├── experiment_1.yaml      # Experiment configuration
│   └── experiment_2.yaml
└── prompt_packs/              # Optional: reusable prompts
    └── common_prompts.yaml
```

**Key principle**: Configuration merges in a **predictable order** to let you define defaults once and override them per-experiment.

---

## Configuration Levels

Elspeth merges configuration from three levels:

```
1. Suite Defaults (settings.yaml)
        ↓
2. Prompt Packs (optional, reusable templates)
        ↓
3. Experiment Overrides (experiments/*.yaml)
```

**Later levels override earlier levels.** This lets you:
- Define security middleware once in settings.yaml
- Share prompts across experiments via prompt packs
- Override specific options per experiment

---

## Settings File (settings.yaml)

The suite-level settings file defines **defaults** inherited by all experiments.

### Basic Structure

```yaml
# config/my_suite/settings.yaml

suite:
  name: my_experiment_suite
  description: Production LLM evaluation suite

# Default security level (inherited by all components)
security:
  default_level: OFFICIAL  # UNOFFICIAL | OFFICIAL | OFFICIAL_SENSITIVE | PROTECTED | SECRET

# Logging configuration
logging:
  level: INFO         # DEBUG | INFO | WARNING | ERROR
  audit: true         # Enable audit trail (logs/run_*.jsonl)
  include_prompts: false  # Log full prompts (be mindful of PII)

# Default LLM configuration (inherited by experiments)
llm:
  type: azure_openai
  endpoint: ${AZURE_OPENAI_ENDPOINT}
  api_key: ${AZURE_OPENAI_KEY}
  deployment_name: gpt-4
  security_level: OFFICIAL

  model_params:
    temperature: 0.7
    max_tokens: 500

  # Default middleware (inherited by all experiments)
  middleware:
    - type: pii_shield
      on_violation: abort
    - type: classified_material
      on_violation: abort
    - type: audit_logger
      include_prompts: false

  # Rate limiting
  rate_limiter:
    type: fixed_window
    requests: 60
    per_seconds: 60

  # Cost tracking
  cost_tracker:
    type: fixed_price
    prompt_token_price: 0.0000015
    completion_token_price: 0.000002

# Default sinks (inherited by all experiments)
sinks:
  - type: csv
    path: "{experiment_name}_results.csv"
    security_level: OFFICIAL
    sanitize_formulas: true

  - type: excel_workbook
    base_path: "reports/{experiment_name}"
    security_level: OFFICIAL
    timestamped: true
    include_manifest: true
```

### Configuration Sections

| Section | Purpose | Required | Common Options |
|---------|---------|----------|----------------|
| `suite` | Suite metadata | ✅ Yes | `name`, `description` |
| `security` | Default security level | ✅ Yes | `default_level` |
| `logging` | Logging behavior | ⚠️ Recommended | `level`, `audit`, `include_prompts` |
| `llm` | Default LLM client | ⚠️ If using LLMs | `type`, `endpoint`, `api_key`, `middleware` |
| `sinks` | Default output sinks | ⚠️ Recommended | `type`, `path`, `security_level` |
| `concurrency` | Parallel execution | ❌ Optional | `max_workers`, `backlog_threshold` |
| `retry` | Retry configuration | ❌ Optional | `max_attempts`, `initial_delay`, `backoff_multiplier` |

---

## Experiment Configuration

Individual experiments inherit from settings.yaml and can override any option.

### Basic Structure

```yaml
# config/my_suite/experiments/sentiment_analysis.yaml

experiment:
  name: sentiment_analysis
  description: Analyze customer sentiment with GPT-4

  # Datasource (required)
  datasource:
    type: csv_local
    path: data/customer_feedback.csv
    security_level: OFFICIAL
    encoding: utf-8

  # LLM configuration (inherits from settings.yaml)
  llm:
    # Override specific model params
    model_params:
      temperature: 0.3  # Lower temperature for consistency

  # Sinks (inherits from settings.yaml)
  sinks:
    # Add experiment-specific sink
    - type: analytics_visual
      base_path: "visualizations/sentiment"
      formats: [png, html]
      security_level: OFFICIAL
```

### Full Example

```yaml
experiment:
  name: product_categorization
  description: Categorize product descriptions with LLM

  # === DATASOURCE ===
  datasource:
    type: csv_local
    path: data/products.csv
    security_level: OFFICIAL
    dtype:
      product_id: str
      description: str
      category: str

  # === LLM ===
  llm:
    # Inherit type/endpoint from settings.yaml
    model_params:
      temperature: 0.2
      max_tokens: 100

    # Add experiment-specific middleware
    middleware:
      - type: regex_match
        pattern: '^(Electronics|Clothing|Food|Other)$'

  # === EXPERIMENT HELPERS ===

  # Row-level processing
  row_plugins:
    - type: score_extractor
      key: confidence
      threshold: 0.8

  # Aggregation
  aggregators:
    - type: cost_summary
    - type: latency_summary

  # Validation
  validation:
    - type: json
      ensure_object: true

  # === BASELINE COMPARISON ===
  baseline:
    experiment_name: product_categorization_v1
    comparison_plugins:
      - type: score_significance
        criteria: [accuracy]
        alpha: 0.05

  # === EARLY STOP ===
  early_stop:
    - type: threshold
      metric: accuracy
      threshold: 0.95
      comparison: greater
      min_rows: 100

  # === SINKS ===
  sinks:
    # Override default sinks (inherit: false)
    inherit: false

    - type: csv
      path: "results/{experiment_name}_categorization.csv"
      security_level: OFFICIAL

    - type: analytics_report
      formats: [json, markdown]
      include_manifest: true
      security_level: OFFICIAL

    - type: signed_artifact
      base_path: artifacts
      algorithm: HMAC-SHA256
      key_env: SIGNING_KEY
      security_level: OFFICIAL
```

---

## Configuration Merge Order

Understanding merge order helps you avoid configuration surprises.

### Merge Rules

```
settings.yaml (suite defaults)
    ↓
+ prompt_pack.yaml (if specified)
    ↓
+ experiment.yaml (experiment-specific)
    ↓
= Final Configuration
```

**Merge behavior:**
- **Simple values** (strings, numbers): Later value **overwrites** earlier value
- **Lists** (middleware, sinks): Later list **appends** to earlier list (unless `inherit: false`)
- **Nested objects** (model_params): Deep merge (only specified keys overwrite)

### Example: Merge Process

**settings.yaml:**
```yaml
llm:
  type: azure_openai
  deployment_name: gpt-4
  model_params:
    temperature: 0.7
    max_tokens: 500
  middleware:
    - type: pii_shield
    - type: audit_logger
```

**experiment.yaml:**
```yaml
llm:
  model_params:
    temperature: 0.3  # Override temperature
  middleware:
    - type: regex_match  # Append to middleware list
```

**Final merged configuration:**
```yaml
llm:
  type: azure_openai           # From settings.yaml
  deployment_name: gpt-4       # From settings.yaml
  model_params:
    temperature: 0.3           # Overridden by experiment.yaml
    max_tokens: 500            # From settings.yaml
  middleware:
    - type: pii_shield         # From settings.yaml
    - type: audit_logger       # From settings.yaml
    - type: regex_match        # Appended from experiment.yaml
```

### Opting Out of Inheritance

Use `inherit: false` to **replace** instead of **append**:

```yaml
llm:
  middleware:
    inherit: false  # Ignore settings.yaml middleware
    - type: audit_logger  # Only middleware for this experiment

sinks:
  inherit: false  # Ignore settings.yaml sinks
  - type: csv
    path: custom_output.csv
```

---

## Environment Variables

Elspeth supports environment variables for **secrets** and **dynamic values**.

### Using Environment Variables

```yaml
llm:
  type: azure_openai
  endpoint: ${AZURE_OPENAI_ENDPOINT}  # Read from env var
  api_key: ${AZURE_OPENAI_KEY}        # Never commit secrets to YAML

datasource:
  type: azure_blob
  connection_string: ${AZURE_STORAGE_CONNECTION_STRING}

sinks:
  - type: signed_artifact
    key_env: SIGNING_KEY  # Plugin reads from env var
```

### Setting Environment Variables

**Development (.env file):**
```bash
# .env (DO NOT COMMIT TO GIT)
AZURE_OPENAI_ENDPOINT=https://my-openai.openai.azure.com
AZURE_OPENAI_KEY=sk-...
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
SIGNING_KEY=my-secret-key
```

**Production (CI/CD):**
```bash
# GitHub Actions / Azure DevOps secrets
export AZURE_OPENAI_ENDPOINT="${{ secrets.AZURE_OPENAI_ENDPOINT }}"
export AZURE_OPENAI_KEY="${{ secrets.AZURE_OPENAI_KEY }}"
```

**Local Development:**
```bash
# Load .env file
source .env

# Or inline
AZURE_OPENAI_KEY=sk-... python -m elspeth.cli --settings config/my_suite/settings.yaml
```

!!! danger "Never Commit Secrets"
    - ❌ Never put API keys, passwords, or connection strings directly in YAML files
    - ✅ Always use environment variables (`${VAR_NAME}`)
    - ✅ Add `.env` to `.gitignore`
    - ✅ Rotate secrets regularly
    - ✅ Use managed identities (Azure, AWS IAM) when possible

---

## Prompt Packs (Advanced)

Reusable prompt templates shared across experiments.

### Creating a Prompt Pack

```yaml
# config/my_suite/prompt_packs/sentiment_pack.yaml

prompt_pack:
  name: sentiment_analysis
  description: Sentiment analysis prompts

  prompts:
    classify_sentiment: |
      Analyze the sentiment of the following text.
      Respond with: "positive", "negative", or "neutral"

      Text: {text}

      Sentiment:

    extract_themes: |
      Identify key themes in the following feedback.

      Feedback: {feedback}

      Themes (JSON array):

  # Middleware shared across experiments
  middleware:
    - type: pii_shield
      on_violation: mask
    - type: audit_logger

  # Default sinks for this pack
  sinks:
    - type: csv
      path: "{experiment_name}_sentiment.csv"
```

### Using a Prompt Pack

```yaml
# experiment.yaml
experiment:
  name: customer_sentiment
  prompt_pack: sentiment_pack  # Reference by name

  datasource:
    type: csv_local
    path: data/feedback.csv

  # Prompts from pack are available in templates
  llm:
    prompt_template: "{prompts.classify_sentiment}"
```

**Benefits:**
- Reuse prompts across experiments
- Centralize middleware configuration
- Standardize output formats

---

## Concurrency & Performance

Configure parallel execution and retry behavior.

### Concurrency Configuration

```yaml
# settings.yaml
concurrency:
  max_workers: 4              # Parallel threads
  backlog_threshold: 100      # Queue size before blocking
  timeout_seconds: 300        # Per-row timeout
```

### Retry Configuration

```yaml
retry:
  max_attempts: 3             # Retry failed rows 3 times
  initial_delay: 1.0          # Start with 1-second delay
  backoff_multiplier: 2.0     # Double delay each retry (1s → 2s → 4s)
  retry_on_errors:
    - RateLimitError
    - TimeoutError
```

**Example: Production Configuration**

```yaml
llm:
  type: azure_openai
  # ... LLM config ...

  rate_limiter:
    type: adaptive
    requests_per_minute: 50
    tokens_per_minute: 100000

concurrency:
  max_workers: 8
  backlog_threshold: 200
  timeout_seconds: 120

retry:
  max_attempts: 5
  initial_delay: 2.0
  backoff_multiplier: 2.0
```

---

## Validation & Schema Checking

Validate configuration before running experiments.

### Validate Configuration

```bash
python -m elspeth.cli validate-schemas \
  --settings config/my_suite/settings.yaml \
  --suite-root config/my_suite
```

**Expected output:**
```
✓ Settings schema valid
✓ Experiment 'sentiment_analysis' schema valid
✓ Experiment 'product_categorization' schema valid
✓ All datasource schemas valid
✓ All LLM schemas valid
✓ All sink schemas valid
✓ All middleware schemas valid
```

### Common Validation Errors

#### Missing Required Field

**Error:**
```
Schema validation failed: 'path' is required
Sink: csv (line 45)
```

**Solution:** Add required field to sink configuration:
```yaml
sinks:
  - type: csv
    path: results.csv  # ← Add missing field
```

#### Invalid Plugin Type

**Error:**
```
Unknown datasource type: 'csv_file'
Did you mean: 'csv_local'?
```

**Solution:** Use correct plugin type from [Plugin Catalogue](../plugins/overview.md).

#### Security Level Mismatch

**Error:**
```
SecurityValidationError: Datasource has insufficient clearance
Component: UNOFFICIAL
Required: OFFICIAL
```

**Solution:** Raise datasource security level to match pipeline:
```yaml
datasource:
  security_level: OFFICIAL  # ← Match pipeline level
```

See [Security Model](security-model.md) for complete explanation.

---

## Configuration Patterns

### Pattern 1: Development Suite

Simple configuration for testing and development.

```yaml
# settings.yaml
suite:
  name: dev_suite
  description: Development experiments

security:
  default_level: UNOFFICIAL  # Lowest level for testing

logging:
  level: DEBUG
  audit: true

llm:
  type: mock
  response_template: "Mock: {text}"
  security_level: UNOFFICIAL

sinks:
  - type: csv
    path: "{experiment_name}.csv"
    security_level: UNOFFICIAL
```

### Pattern 2: Production Suite

Secure configuration with middleware and auditing.

```yaml
# settings.yaml
suite:
  name: production_suite
  description: Production LLM evaluation

security:
  default_level: OFFICIAL

logging:
  level: INFO
  audit: true
  include_prompts: false  # Don't log prompts (PII risk)

llm:
  type: azure_openai
  endpoint: ${AZURE_OPENAI_ENDPOINT}
  api_key: ${AZURE_OPENAI_KEY}
  deployment_name: gpt-4
  security_level: OFFICIAL

  middleware:
    - type: pii_shield
      on_violation: abort
    - type: classified_material
      on_violation: abort
    - type: azure_content_safety
      endpoint: ${AZURE_CONTENT_SAFETY_ENDPOINT}
      api_key: ${AZURE_CONTENT_SAFETY_KEY}
      severity_threshold: medium
    - type: audit_logger
      include_prompts: false
    - type: health_monitor

  rate_limiter:
    type: adaptive
    requests_per_minute: 50
    tokens_per_minute: 100000

  cost_tracker:
    type: fixed_price
    prompt_token_price: 0.0000015
    completion_token_price: 0.000002

concurrency:
  max_workers: 8
  timeout_seconds: 120

retry:
  max_attempts: 5
  initial_delay: 2.0
  backoff_multiplier: 2.0

sinks:
  - type: signed_artifact
    base_path: artifacts
    algorithm: HMAC-SHA256
    key_env: SIGNING_KEY
    security_level: OFFICIAL

  - type: azure_blob
    config_path: config/blob_profiles.yaml
    profile: production
    security_level: OFFICIAL

  - type: excel_workbook
    base_path: "reports/{experiment_name}"
    timestamped: true
    include_manifest: true
    security_level: OFFICIAL
```

### Pattern 3: RAG-Enabled Suite

Retrieval-Augmented Generation with vector store.

```yaml
# settings.yaml
llm:
  type: azure_openai
  # ... standard config ...

# experiment.yaml
experiment:
  name: rag_qa
  description: Question answering with RAG

  datasource:
    type: csv_local
    path: data/questions.csv
    security_level: OFFICIAL

  row_plugins:
    - type: retrieval_context
      provider: pgvector
      dsn: ${DATABASE_URL}
      table: document_embeddings
      embed_model: text-embedding-ada-002
      query_field: question
      top_k: 5
      min_score: 0.7
      inject_mode: prompt  # Inject into prompt template

  llm:
    prompt_template: |
      Context: {retrieval_context}

      Question: {question}

      Answer:
```

---

## Troubleshooting

### Configuration Not Loading

**Problem:** Configuration changes not reflected in experiments.

**Solutions:**
1. **Validate syntax:** Run `validate-schemas` to catch YAML errors
2. **Check merge order:** Experiment overrides may be overriding your changes
3. **Clear cache:** Some plugins cache configuration (restart helps)

### Middleware Not Running

**Problem:** Middleware defined but not executing.

**Solutions:**
1. **Check middleware list:** Ensure middleware is in `llm.middleware` list
2. **Verify plugin type:** Use exact plugin name from [Plugin Catalogue](../plugins/overview.md)
3. **Check execution order:** Middleware runs in declaration order
4. **Look for `inherit: false`:** Experiment may be disabling inherited middleware

### Environment Variables Not Resolving

**Problem:** `${VARIABLE}` appearing literally in configuration.

**Solutions:**
1. **Check variable is set:**
   ```bash
   echo $AZURE_OPENAI_KEY
   ```
2. **Source .env file:**
   ```bash
   source .env
   python -m elspeth.cli ...
   ```
3. **Use explicit export:**
   ```bash
   export AZURE_OPENAI_KEY=sk-...
   ```

### Security Validation Fails

**Problem:** Pipeline aborts with security level error.

**Solution:** See [Security Model Troubleshooting](security-model.md#troubleshooting) for complete guide.

---

## Best Practices

### 1. Use Settings Defaults

Define common configuration once in settings.yaml:

```yaml
# settings.yaml - Define once
llm:
  middleware:
    - type: pii_shield
    - type: audit_logger

# experiments/*.yaml - Inherit automatically
experiment:
  name: experiment_1
  # Middleware inherited from settings.yaml
```

### 2. Validate Before Running

Always validate configuration:

```bash
# Catch errors before running
python -m elspeth.cli validate-schemas \
  --settings config/my_suite/settings.yaml \
  --suite-root config/my_suite

# Then run experiment
python -m elspeth.cli \
  --settings config/my_suite/settings.yaml \
  --suite-root config/my_suite
```

### 3. Use Environment Variables for Secrets

```yaml
# ❌ DON'T: Hardcode secrets
llm:
  api_key: sk-1234567890abcdef

# ✅ DO: Use environment variables
llm:
  api_key: ${AZURE_OPENAI_KEY}
```

### 4. Start Simple, Add Complexity

```yaml
# Phase 1: Minimal configuration
experiment:
  datasource:
    type: csv_local
    path: data/input.csv

  llm:
    type: mock

  sinks:
    - type: csv
      path: output.csv

# Phase 2: Add security
llm:
  middleware:
    - type: pii_shield

# Phase 3: Add monitoring
llm:
  middleware:
    - type: health_monitor

# Phase 4: Add baseline comparison
baseline:
  experiment_name: previous_run
```

### 5. Document Configuration Decisions

Add comments explaining choices:

```yaml
llm:
  model_params:
    temperature: 0.2  # Low temperature for consistency (classification task)
    max_tokens: 50    # Short responses expected (category names)

  middleware:
    - type: pii_shield
      # JUSTIFICATION: Customer data contains emails and phone numbers
      # POLICY: Security team requirement (ticket #1234)
```

---

## Further Reading

- **[First Experiment](../getting-started/first-experiment.md)** - Hands-on configuration walkthrough
- **[Plugin Catalogue](../plugins/overview.md)** - Complete plugin reference
- **[Security Model](security-model.md)** - Understanding security levels
- **[Quickstart](../getting-started/quickstart.md)** - Run sample configuration

---

!!! success "Configuration Mastery"
    You now understand Elspeth's configuration system! Start with simple configurations and gradually add middleware, validation, and baseline comparisons as your experiments mature.
