# First Experiment

Create an Elspeth experiment from scratch in **15-20 minutes**.

## Goal

Build a complete experiment that:
- Loads data from a CSV file
- Processes through a mock LLM
- Writes results to multiple formats
- Runs successfully with proper security levels

---

## Overview

An Elspeth experiment consists of:

1. **Datasource** - Where data comes from (CSV, database, etc.)
2. **Transforms** - How data is processed (LLM, middleware, etc.)
3. **Sinks** - Where results go (CSV, Excel, JSON, etc.)
4. **Configuration** - YAML files tying it all together

---

## Step 1: Create Experiment Directory

```bash
# Create new experiment suite
mkdir -p config/my_first_suite/experiments
mkdir -p data
```

---

## Step 2: Create Sample Data

Create `data/my_data.csv`:

```csv
id,text,category
1,"Analyze customer feedback","support"
2,"Generate product description","marketing"
3,"Summarize meeting notes","operations"
```

**Explanation**:
- `id`: Unique identifier
- `text`: Input for LLM processing
- `category`: Metadata for grouping

---

## Step 3: Create Settings File

Create `config/my_first_suite/settings.yaml`:

```yaml
# Suite-level settings
suite:
  name: my_first_suite
  description: My first Elspeth experiment suite

# Default security level (inherited by all components)
security:
  default_level: UNOFFICIAL  # Lowest level for testing

# Logging configuration
logging:
  level: INFO
  audit: true
```

**Key settings**:
- `security.default_level`: Start with `UNOFFICIAL` for testing (no sensitive data)
- `logging.audit`: Enables audit trail in `logs/run_*.jsonl`

---

## Step 4: Create Experiment Configuration

Create `config/my_first_suite/experiments/text_processing.yaml`:

```yaml
experiment:
  name: text_processing
  description: Process text through LLM

  # Data source configuration
  datasource:
    type: csv_local
    path: data/my_data.csv
    security_level: UNOFFICIAL  # Match data sensitivity

  # LLM transformation
  llm:
    type: mock  # Use mock for testing (no API keys needed)
    response_template: "Processed: {text}"
    security_level: UNOFFICIAL

  # Output sinks
  sinks:
    - type: csv
      path: text_processing_results.csv
      security_level: UNOFFICIAL

    - type: excel
      path: text_processing_results.xlsx
      security_level: UNOFFICIAL
      include_timestamp: true

    - type: json
      path: text_processing_results.json
      security_level: UNOFFICIAL
      pretty: true
```

**Breakdown**:

- **Datasource**: `csv_local` reads from local CSV file
- **LLM**: `mock` simulates LLM responses (good for testing)
- **Sinks**: Multiple output formats (CSV, Excel, JSON)
- **Security levels**: All set to `UNOFFICIAL` (lowest sensitivity)

---

## Step 5: Validate Configuration

Before running, validate the configuration:

```bash
python -m elspeth.cli validate-schemas \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite
```

**Expected output**:
```
✓ Settings schema valid
✓ Experiment 'text_processing' schema valid
✓ All datasource schemas valid
✓ All LLM schemas valid
✓ All sink schemas valid
```

**If validation fails**:
- Check YAML syntax (indentation, quotes)
- Verify file paths exist
- Ensure security levels are consistent

---

## Step 6: Run Experiment

```bash
python -m elspeth.cli \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite \
  --reports-dir outputs/my_first_suite \
  --head 0
```

**Flags**:
- `--settings`: Path to settings file
- `--suite-root`: Directory containing experiments
- `--reports-dir`: Where to write outputs
- `--head 0`: Skip data preview (show all rows in output)

**Expected output**:
```
INFO: Loading experiment suite from config/my_first_suite
INFO: Running experiment: text_processing
INFO: Datasource: my_data.csv (3 rows, UNOFFICIAL)
INFO: Transform: MockLLMClient (UNOFFICIAL)
INFO: Pipeline operating level: UNOFFICIAL
INFO: Writing to CSV sink: text_processing_results.csv
INFO: Writing to Excel sink: text_processing_results.xlsx
INFO: Writing to JSON sink: text_processing_results.json
✓ Experiment complete: 3 rows processed

=== Results ===
| id | text                          | category   | llm_response                     |
|----|-------------------------------|------------|----------------------------------|
| 1  | Analyze customer feedback     | support    | Processed: Analyze customer...   |
| 2  | Generate product description  | marketing  | Processed: Generate product...   |
| 3  | Summarize meeting notes       | operations | Processed: Summarize meeting...  |
```

---

## Step 7: Inspect Outputs

Check the generated files:

```bash
ls outputs/my_first_suite/

# Expected:
# text_processing_results.csv
# text_processing_results.xlsx
# text_processing_results.json
# manifest.json
```

**View CSV**:
```bash
cat outputs/my_first_suite/text_processing_results.csv
```

**View JSON** (pretty-printed):
```bash
cat outputs/my_first_suite/text_processing_results.json | jq
```

**View manifest** (experiment metadata):
```bash
cat outputs/my_first_suite/manifest.json | jq
```

---

## Step 8: Customize the Experiment

### Add More Sinks

Edit `text_processing.yaml` and add:

```yaml
sinks:
  # ... existing sinks ...

  - type: markdown
    path: report.md
    template: |
      # Text Processing Results

      **Processed {{ total_rows }} rows**

      {% for row in rows %}
      - **{{ row.category }}**: {{ row.llm_response }}
      {% endfor %}
```

### Add Middleware

Insert between datasource and LLM:

```yaml
llm:
  type: mock
  response_template: "Processed: {text}"

  middleware:
    - type: audit
      log_inputs: true
      log_outputs: true

    - type: health_monitor
      max_retries: 3
```

### Use Multiple Datasources

Create suite with multiple experiments:

```yaml
# experiments/experiment_1.yaml
experiment:
  name: experiment_1
  datasource:
    type: csv_local
    path: data/dataset_1.csv

# experiments/experiment_2.yaml
experiment:
  name: experiment_2
  datasource:
    type: csv_local
    path: data/dataset_2.csv
```

---

## Understanding Security Levels

Elspeth enforces **Bell-LaPadula Multi-Level Security (MLS)**:

```
UNOFFICIAL → OFFICIAL → OFFICIAL_SENSITIVE → PROTECTED → SECRET
(lowest)                                                  (highest)
```

**Key rule**: Components can only access data at their level or below.

### Example: Mismatched Levels

**This will FAIL**:
```yaml
datasource:
  security_level: UNOFFICIAL  # Low clearance

llm:
  security_level: UNOFFICIAL

sinks:
  - type: csv
    security_level: SECRET  # High clearance - FAILS!
```

**Error**: `SecurityValidationError: Datasource has insufficient clearance (UNOFFICIAL) for pipeline level (SECRET)`

**Why**: Datasource can't "uplift" data from UNOFFICIAL to SECRET.

**This will SUCCEED**:
```yaml
datasource:
  security_level: SECRET  # High clearance

sinks:
  - type: csv
    security_level: UNOFFICIAL  # Low clearance - OK!
```

**Why**: SECRET datasource can "downgrade" data to UNOFFICIAL (trusted to filter sensitive info).

See [Security Model](../user-guide/security-model.md) for full details.

---

## Common Issues

### Schema Validation Errors

**Error**: `Schema validation failed: 'path' is required`

**Solution**: Check required fields in experiment config. All sinks need `type` and `path`.

### File Not Found

**Error**: `FileNotFoundError: data/my_data.csv`

**Solution**: Verify file path is correct and file exists:
```bash
ls data/my_data.csv
```

### Security Validation Error

**Error**: `SecurityValidationError: Insufficient clearance`

**Solution**: Ensure all components have same (or compatible) security levels. Start with `UNOFFICIAL` for everything.

### Empty Output

**Problem**: Experiment runs but output files are empty

**Solution**: Check for:
1. Empty input CSV
2. LLM response template issues
3. Sink filters excluding all rows

---

## Next Steps

### Add Real LLM

Replace mock with Azure OpenAI:

```yaml
llm:
  type: azure_openai
  endpoint: ${AZURE_OPENAI_ENDPOINT}
  api_key: ${AZURE_OPENAI_KEY}
  deployment_name: gpt-4
  model_params:
    temperature: 0.7
    max_tokens: 500
```

### Add Baseline Comparison

Compare experiment results against a baseline:

```yaml
experiment:
  baseline:
    experiment_name: previous_run
    metrics:
      - accuracy
      - f1_score
```

### Add Signed Artifacts

Generate cryptographically signed bundles:

```bash
python -m elspeth.cli \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite \
  --artifacts-dir artifacts \
  --signed-bundle
```

---

## Experiment Structure Reference

```
config/my_first_suite/
├── settings.yaml              # Suite-level settings
├── experiments/
│   ├── text_processing.yaml   # Experiment configuration
│   └── another_experiment.yaml
└── prompt_packs/              # Optional: reusable prompts
    └── common_prompts.yaml

data/
└── my_data.csv                # Input data

outputs/my_first_suite/        # Generated outputs
├── text_processing_results.csv
├── text_processing_results.xlsx
├── text_processing_results.json
└── manifest.json

logs/
└── run_<timestamp>.jsonl      # Audit logs
```

---

## Quick Reference

```bash
# Validate configuration
python -m elspeth.cli validate-schemas \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite

# Run experiment
python -m elspeth.cli \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite \
  --reports-dir outputs/my_first_suite

# Run with head preview (first 10 rows)
python -m elspeth.cli \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite \
  --head 10

# Run with signed artifacts
python -m elspeth.cli \
  --settings config/my_first_suite/settings.yaml \
  --suite-root config/my_first_suite \
  --artifacts-dir artifacts \
  --signed-bundle
```

---

!!! success "Congratulations!"
    You've created and run a complete Elspeth experiment from scratch! You now understand:

    - ✅ Experiment structure (datasource → LLM → sinks)
    - ✅ Configuration files (YAML)
    - ✅ Security levels (MLS enforcement)
    - ✅ Output formats (CSV, Excel, JSON)
    - ✅ Validation and debugging

    Ready to dive deeper? Learn about [Security Model](../user-guide/security-model.md) or explore the [Plugin Catalogue](../plugins/overview.md).
