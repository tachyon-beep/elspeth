# Plugin Catalogue

Discover Elspeth's built-in plugins organized by **what you want to accomplish**.

!!! tip "Quick Start"
    For your first experiment, use: `csv_local` datasource → `mock` LLM → `csv` sink. Once working, swap `mock` for a real LLM like `azure_openai`.

---

## Overview

Elspeth plugins are modular components that handle specific tasks in your experiment pipeline:

```
Datasources → LLM Transforms → Sinks
     ↓             ↓             ↓
  Load Data    Process Data   Save Results
```

All plugins declare a **security level** (clearance) and work within the Bell-LaPadula MLS framework. See [Security Model](../user-guide/security-model.md) for details.

---

## Loading Data (Datasources)

Choose how to load input data into your experiments.

### Decision Guide

```
Need local CSV file?           → csv_local
Need CSV from Azure Blob?      → csv_blob or azure_blob
Need database/API integration? → Coming soon (SQL, REST APIs)
```

### Available Datasources

| Plugin | When to Use | Key Configuration | Example |
|--------|-------------|-------------------|---------|
| **`csv_local`** | Local filesystem CSV files | `path`, `encoding`, `dtype` | Perfect for development and testing |
| **`csv_blob`** | CSV from Azure Blob Storage (direct URI) | `path` (blob URI), `dtype` | Production pipelines with blob URIs |
| **`azure_blob`** | CSV from Azure Blob with profile-based auth | `config_path`, `profile` | Managed identity or config-based auth |

#### Example: Local CSV Datasource

```yaml
datasource:
  type: csv_local
  path: data/customer_feedback.csv
  security_level: OFFICIAL
  encoding: utf-8
  on_error: abort  # abort | skip | log
```

#### Example: Azure Blob Datasource

```yaml
datasource:
  type: azure_blob
  config_path: config/blob_profiles.yaml
  profile: production
  security_level: PROTECTED
  pandas_kwargs:
    dtype:
      customer_id: str
      rating: int
```

**Common Options:**
- `on_error`: What to do if file can't be read (`abort`, `skip`, `log`)
- `dtype`: Column type hints for Pandas (prevents parsing issues)
- `encoding`: File encoding (default: `utf-8`)

---

## Processing with LLMs

Choose how to send data to language models for processing.

### Decision Guide

```
Need Azure OpenAI?             → azure_openai
Need generic OpenAI API?       → http_openai
Testing without API keys?      → mock
Need deterministic responses?  → static_test
```

### Available LLM Clients

| Plugin | When to Use | Key Configuration | Notes |
|--------|-------------|-------------------|-------|
| **`azure_openai`** | Azure-hosted OpenAI (GPT-4, GPT-3.5) | `endpoint`, `api_key`, `deployment_name` | Production LLM access |
| **`http_openai`** | Generic OpenAI HTTP API | `api_base`, `api_key`, `model` | OpenAI or compatible APIs |
| **`mock`** | Testing without real LLM | `response_template`, `seed` | No API keys needed |
| **`static_test`** | Canned responses for testing | `content`, `score`, `metrics` | Deterministic outputs |

#### Example: Azure OpenAI

```yaml
llm:
  type: azure_openai
  endpoint: https://my-openai.openai.azure.com
  api_key: ${AZURE_OPENAI_KEY}  # From environment
  deployment_name: gpt-4
  security_level: OFFICIAL

  model_params:
    temperature: 0.7
    max_tokens: 500
    top_p: 0.9
```

#### Example: Mock LLM (Testing)

```yaml
llm:
  type: mock
  response_template: "Mock response for: {text}"
  security_level: UNOFFICIAL
  seed: 42  # Deterministic for tests
```

**Common Model Parameters:**
- `temperature`: Randomness (0.0 = deterministic, 1.0 = creative)
- `max_tokens`: Maximum response length
- `top_p`: Nucleus sampling threshold
- `frequency_penalty`: Reduce repetition (-2.0 to 2.0)
- `presence_penalty`: Encourage topic diversity (-2.0 to 2.0)

---

## LLM Middleware (Security & Monitoring)

Add security filters, audit logging, and health monitoring to your LLM pipeline.

### Decision Guide

```
Need to log prompts/responses?         → audit_logger
Need to block banned terms?            → prompt_shield
Need to block PII (emails, SSNs)?      → pii_shield
Need to block classified markings?     → classified_material
Need Azure Content Safety?             → azure_content_safety
Need latency/health monitoring?        → health_monitor
```

### Security Middleware

| Plugin | Purpose | Key Configuration | Default Behavior |
|--------|---------|-------------------|------------------|
| **`pii_shield`** | Detect and block PII (emails, credit cards, SSNs, phone numbers, Australian TFN/Medicare/ABN, etc.) | `on_violation` (abort/mask/log), `patterns` | Blocks by default |
| **`classified_material`** | Detect classified markings (SECRET, TOP SECRET, TS//SCI, NOFORN, etc.) | `on_violation`, `classification_markings` | Blocks by default |
| **`prompt_shield`** | Block prompts containing banned terms | `denied_terms`, `on_violation` (abort/mask/log) | Aborts on match |
| **`azure_content_safety`** | Azure Content Safety API screening | `endpoint`, `api_key`, `severity_threshold` | Blocks harmful content |

#### Example: PII Shield

```yaml
llm:
  type: azure_openai
  # ... LLM config ...

  middleware:
    - type: pii_shield
      on_violation: abort  # abort | mask | log
      include_defaults: true  # Use built-in patterns
      patterns:  # Add custom patterns
        - name: employee_id
          regex: 'EMP-\\d{6}'
```

**Built-in PII Patterns:**
- Email addresses
- Credit card numbers
- US Social Security Numbers (SSN)
- US phone numbers and passports
- Australian TFN, ABN, ACN, Medicare numbers
- Australian phone/mobile, passport, driver's licenses (NSW/VIC/QLD)
- UK National Insurance numbers
- IP addresses

#### Example: Classified Material Filter

```yaml
llm:
  middleware:
    - type: classified_material
      on_violation: abort
      include_defaults: true  # SECRET, TOP SECRET, TS//SCI, etc.
      case_sensitive: false
      classification_markings:
        - CABINET IN CONFIDENCE
        - PROTECTED//LEGAL PRIVILEGE
```

**Built-in Classified Markings:**
- SECRET, TOP SECRET, CONFIDENTIAL
- TS//SCI (Top Secret Sensitive Compartmented Information)
- NOFORN (Not Releasable to Foreign Nationals)
- FVEY (Five Eyes)
- PROTECTED (Australian/UK classifications)

### Monitoring Middleware

| Plugin | Purpose | Key Configuration | Use When |
|--------|---------|-------------------|----------|
| **`audit_logger`** | Structured logging of all LLM calls | `include_prompts`, `channel` | Always use in production |
| **`health_monitor`** | Track latency, errors, heartbeats | `heartbeat_interval`, `stats_window` | Production monitoring |

#### Example: Audit Logger

```yaml
llm:
  middleware:
    - type: audit_logger
      include_prompts: true   # Log full prompts (be mindful of PII)
      channel: llm_requests   # Log channel name
```

#### Example: Health Monitor

```yaml
llm:
  middleware:
    - type: health_monitor
      heartbeat_interval: 60  # Seconds
      stats_window: 300       # 5-minute rolling window
      include_latency: true
```

**Middleware Execution Order:**

Middleware runs in the order declared. Best practice:

```yaml
llm:
  middleware:
    - type: pii_shield           # 1. Block PII first
    - type: classified_material  # 2. Block classified markings
    - type: prompt_shield        # 3. Block banned terms
    - type: audit_logger         # 4. Log sanitized prompts
    - type: health_monitor       # 5. Track performance
    - type: azure_content_safety # 6. Final content check
```

---

## Saving Results (Sinks)

Choose how to save experiment outputs.

### Decision Guide

```
Need simple CSV?                       → csv
Need Excel workbook?                   → excel_workbook
Need JSON?                             → local_bundle (with JSON)
Need charts/visualizations?            → analytics_visual or enhanced_visual
Need structured analytics report?      → analytics_report
Need Azure Blob upload?                → azure_blob
Need Git repository commit?            → github_repo or azure_devops_repo
Need signed artifacts?                 → signed_artifact
Need compressed bundle?                → zip_bundle
```

### Available Sinks

| Plugin | When to Use | Key Configuration | Output |
|--------|-------------|-------------------|--------|
| **`csv`** | Simple CSV export | `path`, `sanitize_formulas` | Single CSV file |
| **`excel_workbook`** | Excel with multiple sheets | `base_path`, `timestamped` | .xlsx file |
| **`local_bundle`** | JSON + CSV bundle | `base_path`, `write_json`, `write_csv` | Directory with files |
| **`analytics_report`** | Structured analytics (JSON/Markdown) | `formats` (json/markdown), `include_manifest` | Report files |
| **`analytics_visual`** | Charts (PNG/HTML) | `formats`, `dpi`, `figure_size` | Visualization files |
| **`enhanced_visual`** | Advanced charts (violin, heatmap, forest plots) | `chart_types`, `color_palette` | Advanced visualizations |
| **`azure_blob`** | Azure Blob Storage upload | `config_path`, `profile`, `path_template` | Blob in Azure |
| **`github_repo`** | Commit to GitHub repo | `owner`, `repo`, `branch`, `token_env` | Git commit |
| **`azure_devops_repo`** | Commit to Azure DevOps | `organization`, `project`, `repository` | Git commit |
| **`signed_artifact`** | Cryptographically signed bundle | `algorithm` (HMAC/RSA/ECDSA), `key` | Signed tarball + signature |
| **`zip_bundle`** | Compressed archive | `bundle_name`, `include_manifest` | .zip file |

#### Example: CSV Sink

```yaml
sinks:
  - type: csv
    path: results/experiment_output.csv
    security_level: OFFICIAL
    sanitize_formulas: true  # Remove Excel formulas for security
    overwrite: true
```

#### Example: Excel Workbook

```yaml
sinks:
  - type: excel_workbook
    base_path: results/experiment
    security_level: OFFICIAL
    timestamped: true  # Adds timestamp to filename
    include_manifest: true  # Adds metadata sheet
    sanitize_formulas: true
```

#### Example: Multiple Sinks

```yaml
sinks:
  # CSV for data analysis
  - type: csv
    path: results/data.csv
    security_level: OFFICIAL

  # Excel for stakeholder reports
  - type: excel_workbook
    base_path: results/report
    security_level: OFFICIAL
    timestamped: true

  # Visualizations for presentations
  - type: analytics_visual
    base_path: results/charts
    security_level: OFFICIAL
    formats: [png, html]
    dpi: 300  # High-res for presentations
```

#### Example: Advanced Visualizations

```yaml
sinks:
  - type: enhanced_visual
    base_path: results/advanced_charts
    security_level: OFFICIAL
    chart_types:
      - violin      # Distribution + box plot
      - heatmap     # Correlation matrices
      - forest      # Effect size visualizations
      - box         # Traditional box plots
      - distribution # Overlaid distributions
    formats: [png, html]
    color_palette: colorblind  # Accessible colors
```

#### Example: Signed Artifacts

```yaml
sinks:
  - type: signed_artifact
    base_path: artifacts
    bundle_name: experiment_results
    security_level: PROTECTED
    algorithm: HMAC-SHA256  # HMAC-SHA256 | HMAC-SHA512 | RSA-PSS-SHA256 | ECDSA-P256-SHA256
    key_env: SIGNING_KEY    # Environment variable with key
```

**Formula Sanitization:**

For security, CSV and Excel sinks automatically sanitize spreadsheet formulas by default:
- `=SUM(A1:A10)` → `'=SUM(A1:A10)` (prefixed with `'`)
- Prevents formula injection attacks
- Disable with `sanitize_formulas: false` (not recommended)

---

## Experiment Helpers

Plugins that enhance experiment behavior.

### Validation Plugins

Ensure LLM responses meet quality criteria.

| Plugin | Purpose | Configuration | Example Use |
|--------|---------|---------------|-------------|
| **`regex_match`** | Validate with regex | `pattern`, `flags` | Ensure specific format |
| **`json`** | Validate JSON structure | `ensure_object` | Check valid JSON |
| **`llm_guard`** | Use secondary LLM for validation | `validator_llm` definition | Complex guardrails |

#### Example: Regex Validation

```yaml
experiment:
  validation:
    - type: regex_match
      pattern: '^[A-Z]{3}-\\d{6}$'  # Format: ABC-123456
      flags: IGNORECASE
```

#### Example: JSON Validation

```yaml
experiment:
  validation:
    - type: json
      ensure_object: true  # Must be object, not array
```

### Row-Level Plugins

Process each row during the experiment.

| Plugin | Purpose | Configuration | Use When |
|--------|---------|---------------|----------|
| **`score_extractor`** | Extract numeric scores from responses | `key`, `threshold` | Pull ratings/scores from LLM output |
| **`retrieval_context`** | Add RAG (Retrieval-Augmented Generation) context | `provider` (pgvector/azure_search), `top_k` | Enrich prompts with knowledge base |

#### Example: Score Extraction

```yaml
experiment:
  row_plugins:
    - type: score_extractor
      key: quality_score
      threshold: 0.7
      threshold_mode: min  # min | max
      criteria:
        - relevance
        - accuracy
        - clarity
```

### Aggregation Plugins

Compute statistics after all rows are processed.

| Plugin | Purpose | Key Metrics | Use When |
|--------|---------|-------------|----------|
| **`score_stats`** | Basic statistics | Mean, median, std dev | Simple score summaries |
| **`cost_summary`** | Cost and token usage | Total cost, tokens | Budget tracking |
| **`latency_summary`** | Latency metrics | p50, p95, p99 | Performance analysis |
| **`rationale_analysis`** | Analyze LLM reasoning | Themes, keywords, confidence | Interpretability research |

#### Example: Cost Summary

```yaml
experiment:
  aggregators:
    - type: cost_summary
      on_error: log  # abort | skip | log
```

#### Example: Latency Summary

```yaml
experiment:
  aggregators:
    - type: latency_summary
      on_error: log
```

### Baseline Comparison Plugins

Compare experiments against baselines.

| Plugin | Purpose | Statistical Method | Use When |
|--------|---------|-------------------|----------|
| **`score_delta`** | Simple score difference | Delta calculation | Quick A/B comparison |
| **`score_significance`** | Statistical significance | t-test, Mann-Whitney | Validate improvements |
| **`score_cliffs_delta`** | Effect size | Cliff's Delta | Measure practical impact |
| **`score_bayes`** | Bayesian comparison | Credible intervals | Probabilistic comparison |
| **`score_distribution`** | Distribution comparison | KS test, histograms | Understand score distributions |
| **`referee_alignment`** | LLM vs. human expert alignment | MAE, RMSE, correlation | Validate LLM against human judges |

#### Example: Statistical Significance

```yaml
experiment:
  baseline:
    experiment_name: previous_run
    comparison_plugins:
      - type: score_significance
        criteria:
          - relevance
          - accuracy
        alpha: 0.05  # 95% confidence
        alternative: greater  # greater | less | two-sided
```

#### Example: Referee Alignment

```yaml
experiment:
  baseline:
    comparison_plugins:
      - type: referee_alignment
        referee_fields:
          - expert_rating
          - human_judgment
        score_field: llm_score
        criteria:
          - relevance
        min_samples: 30
        value_mapping:  # Map text to numbers
          excellent: 5
          good: 4
          fair: 3
          poor: 2
          bad: 1
```

### Early Stop Plugins

Halt experiments based on conditions.

| Plugin | Purpose | Configuration | Example |
|--------|---------|---------------|---------|
| **`threshold`** | Stop when metric crosses threshold | `metric`, `threshold`, `comparison` | Stop when accuracy > 0.95 |

#### Example: Early Stop

```yaml
experiment:
  early_stop:
    - type: threshold
      metric: accuracy
      threshold: 0.95
      comparison: greater  # greater | less | equal
      min_rows: 100  # Require minimum sample
      label: high_accuracy_reached
```

---

## Advanced: Retrieval-Augmented Generation (RAG)

Enrich LLM prompts with context from vector databases.

### Supported Vector Stores

| Provider | When to Use | Configuration |
|----------|-------------|---------------|
| **`pgvector`** | PostgreSQL with pgvector extension | `dsn`, `table`, `top_k` |
| **`azure_search`** | Azure Cognitive Search | `endpoint`, `index`, `api_key` |

#### Example: PostgreSQL Vector Retrieval

```yaml
experiment:
  row_plugins:
    - type: retrieval_context
      provider: pgvector
      dsn: postgresql://user:pass@localhost/db
      table: document_embeddings
      embed_model: text-embedding-ada-002
      query_field: user_question
      top_k: 5
      min_score: 0.7
      inject_mode: metadata  # metadata | prompt
```

#### Example: Azure Search Retrieval

```yaml
experiment:
  row_plugins:
    - type: retrieval_context
      provider: azure_search
      endpoint: https://my-search.search.windows.net
      index: knowledge_base
      api_key_env: AZURE_SEARCH_KEY
      embed_model: text-embedding-ada-002
      query_field: user_question
      top_k: 3
```

**Inject Modes:**
- `metadata`: Add retrieved context to row metadata (access via `metadata.retrieval_context`)
- `prompt`: Inject directly into prompt template (use `{retrieval_context}` placeholder)

---

## Cost & Rate Limiting

Control API costs and request rates.

### Rate Limiters

| Plugin | Strategy | Configuration | Use When |
|--------|----------|---------------|----------|
| **`fixed_window`** | Fixed requests per time window | `requests`, `per_seconds` | Simple rate limits |
| **`adaptive`** | Token-aware adaptive throttling | `requests_per_minute`, `tokens_per_minute` | Token-based pricing |
| **`noop`** | No rate limiting | None | Development/testing |

#### Example: Fixed Window Rate Limit

```yaml
llm:
  rate_limiter:
    type: fixed_window
    requests: 60
    per_seconds: 60  # 60 requests per 60 seconds
```

#### Example: Adaptive Rate Limit

```yaml
llm:
  rate_limiter:
    type: adaptive
    requests_per_minute: 50
    tokens_per_minute: 100000
    interval_seconds: 1  # Check every second
```

### Cost Trackers

| Plugin | Pricing Model | Configuration | Use When |
|--------|---------------|---------------|----------|
| **`fixed_price`** | Fixed per-token pricing | `prompt_token_price`, `completion_token_price` | OpenAI-style pricing |
| **`noop`** | No cost tracking | None | Development/testing |

#### Example: Cost Tracking

```yaml
llm:
  cost_tracker:
    type: fixed_price
    prompt_token_price: 0.0000015    # $0.0015 per 1K tokens
    completion_token_price: 0.000002 # $0.002 per 1K tokens
```

**View costs** with the `cost_summary` aggregator:

```yaml
experiment:
  aggregators:
    - type: cost_summary
```

---

## Common Patterns

### Pattern 1: Simple CSV → LLM → CSV

```yaml
experiment:
  datasource:
    type: csv_local
    path: data/input.csv
    security_level: UNOFFICIAL

  llm:
    type: mock
    response_template: "Processed: {text}"
    security_level: UNOFFICIAL

  sinks:
    - type: csv
      path: output.csv
      security_level: UNOFFICIAL
```

### Pattern 2: Production with Security

```yaml
experiment:
  datasource:
    type: azure_blob
    config_path: config/blob.yaml
    profile: production
    security_level: PROTECTED

  llm:
    type: azure_openai
    endpoint: ${AZURE_OPENAI_ENDPOINT}
    api_key: ${AZURE_OPENAI_KEY}
    deployment_name: gpt-4
    security_level: PROTECTED

    middleware:
      - type: pii_shield
        on_violation: abort
      - type: classified_material
        on_violation: abort
      - type: audit_logger
        include_prompts: true

  sinks:
    - type: signed_artifact
      base_path: artifacts
      algorithm: HMAC-SHA256
      key_env: SIGNING_KEY
      security_level: PROTECTED
```

### Pattern 3: RAG with Baseline Comparison

```yaml
experiment:
  datasource:
    type: csv_local
    path: data/questions.csv
    security_level: OFFICIAL

  llm:
    type: azure_openai
    deployment_name: gpt-4
    security_level: OFFICIAL

  row_plugins:
    - type: retrieval_context
      provider: pgvector
      dsn: ${DATABASE_URL}
      top_k: 5

  baseline:
    experiment_name: without_rag
    comparison_plugins:
      - type: score_significance
        criteria: [accuracy, relevance]

  sinks:
    - type: analytics_report
      formats: [json, markdown]
      security_level: OFFICIAL
```

---

## Security Considerations

### All Plugins Inherit Security Level

Every plugin declares a `security_level` (clearance):

```yaml
datasource:
  type: csv_local
  security_level: OFFICIAL  # ← Clearance declaration

llm:
  security_level: PROTECTED  # ← Can handle PROTECTED data

sinks:
  - type: csv
    security_level: OFFICIAL  # ← Output clearance
```

**Pipeline operating level** = MIN of all component security levels.

See [Security Model](../user-guide/security-model.md) for complete explanation.

### Formula Sanitization (CSV/Excel)

CSV and Excel sinks sanitize formulas by default:
- Prefixes formulas with `'` to prevent execution
- Prevents formula injection attacks
- Disable with `sanitize_formulas: false` (not recommended)

### PII and Classified Material

Use middleware to block sensitive content:

```yaml
llm:
  middleware:
    - type: pii_shield
      on_violation: abort
    - type: classified_material
      on_violation: abort
```

---

## Plugin Development

Want to create custom plugins? See [API Reference](../api-reference/index.md).

**Built-in plugin interfaces:**
- **Datasource**: Implement `load_data()`, declare `security_level`
- **LLM Client**: Implement `transform()`, `consumes()`, `produces()`
- **Sink**: Implement `write()`, `consumes()`, `produces()`
- **Middleware**: Implement `before_request()`, `after_response()`

---

## Further Reading

- **[Security Model](../user-guide/security-model.md)** - Understanding Bell-LaPadula MLS
- **[Configuration Guide](../user-guide/configuration.md)** - Deep dive into YAML configuration
- **[First Experiment](../getting-started/first-experiment.md)** - Build an experiment step-by-step
- **[Plugin Development](../api-reference/index.md)** - Create custom plugins

---

!!! success "Ready to Build?"
    You now know how to choose the right plugins for your experiment! Start with the simple patterns above, then gradually add security middleware, validation, and advanced features as needed.
