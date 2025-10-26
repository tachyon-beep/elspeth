# Quickstart

Run your first Elspeth experiment in **5 minutes**.

## Goal

By the end of this guide, you'll:
- ✅ Run a complete experiment suite
- ✅ See LLM processing in action (mock LLM, no API keys needed)
- ✅ Generate output artifacts (CSV, Excel, JSON)
- ✅ Understand the basic workflow

---

## Prerequisites

- Elspeth installed ([Installation Guide](installation.md))
- Virtual environment activated

---

## Step 1: Activate Environment

```bash
cd elspeth
source .venv/bin/activate
```

---

## Step 2: Run Sample Suite

Elspeth includes a pre-configured sample suite with mock LLM (no external dependencies):

```bash
make sample-suite
```

**What happens**:
1. Loads sample data from CSV
2. Processes through mock LLM transform
3. Writes results to multiple output formats
4. Shows preview tables in terminal

**Expected output**:
```
INFO: Loading experiment suite from config/sample_suite
INFO: Running experiment: basic_transform
INFO: Datasource: sample_data.csv (10 rows)
INFO: Transform: MockLLMClient
INFO: Sink: CSV output
✓ Experiment complete: outputs/sample_suite_reports/basic_transform.csv

=== Preview: basic_transform ===
| input_text          | llm_response             | confidence |
|---------------------|--------------------------|------------|
| Hello world         | MOCK: Hello world        | 0.95       |
| Test data           | MOCK: Test data          | 0.92       |
...
```

**How to verify success**:

✅ **Terminal shows** "✓ Experiment complete" with no ERROR lines
✅ **Output files exist**:
```bash
ls outputs/sample_suite_reports/
# Expected: basic_transform.csv, basic_transform.xlsx, basic_transform.json
```

✅ **CSV has 10 data rows**:
```bash
wc -l outputs/sample_suite_reports/basic_transform.csv
# Expected: 11 (10 data + 1 header)
```

---

## Step 3: Explore Outputs

Results are written to `outputs/sample_suite_reports/`:

```bash
ls outputs/sample_suite_reports/

# Expected files:
# basic_transform.csv
# basic_transform.xlsx
# basic_transform.json
# manifest.json
```

**View CSV output**:
```bash
cat outputs/sample_suite_reports/basic_transform.csv
```

**View manifest** (experiment metadata):
```bash
cat outputs/sample_suite_reports/manifest.json | jq
```

---

## Step 4: Understand What Happened

### Pipeline Flow

```
┌──────────────┐      ┌───────────────┐      ┌──────────┐
│  CSV Data    │  →   │  Mock LLM     │  →   │  Sinks   │
│  (10 rows)   │      │  (Transform)  │      │  (3 files)│
└──────────────┘      └───────────────┘      └──────────┘
```

### Configuration

The sample suite is defined in `config/sample_suite/`:

```yaml
# config/sample_suite/experiments/basic_transform.yaml
experiment:
  name: basic_transform

  datasource:
    type: csv_local
    path: data/sample.csv

  llm:
    type: mock
    response_template: "MOCK: {input_text}"

  sinks:
    - type: csv
      path: basic_transform.csv
    - type: excel
      path: basic_transform.xlsx
    - type: json
      path: basic_transform.json
```

---

## Step 5: Run with Signed Artifacts

Generate cryptographically signed bundles:

```bash
make sample-suite-artifacts
```

**Additional outputs**:
- `artifacts/sample_suite_<timestamp>.tar.gz` - Signed bundle
- `artifacts/sample_suite_<timestamp>.tar.gz.sig` - HMAC signature
- SBOM included in bundle

---

## What's Next?

### Learn More

- **[First Experiment](first-experiment.md)** - Create your own experiment from scratch
- **[Security Model](../user-guide/security-model.md)** - Understand Bell-LaPadula MLS
- **[Configuration](../user-guide/configuration.md)** - Deep dive into config files

### Try Different Sinks

Edit `config/sample_suite/experiments/basic_transform.yaml`:

```yaml
sinks:
  - type: markdown
    path: report.md
  - type: visual_analytics
    path: analysis.html
```

### Use Real LLM

Replace mock LLM with Azure OpenAI:

```yaml
llm:
  type: azure_openai
  endpoint: https://your-endpoint.openai.azure.com
  api_key: ${AZURE_OPENAI_KEY}  # From environment variable
  deployment_name: gpt-4
```

---

## Common Issues

### Command Not Found

**Error**: `make: command not found`

**Solution**: Run CLI directly:
```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --head 0
```

### No Module Named 'elspeth'

**Error**: `ModuleNotFoundError: No module named 'elspeth'`

**Solution**: Ensure virtual environment is activated and Elspeth is installed:
```bash
source .venv/bin/activate
python -m pip install -e . --no-deps --no-index
```

### Permission Denied on Outputs

**Error**: Cannot write to `outputs/`

**Solution**: Create output directory:
```bash
mkdir -p outputs/sample_suite_reports
```

---

## Quick Reference

```bash
# Run sample suite (no external deps)
make sample-suite

# Run with signed artifacts
make sample-suite-artifacts

# Run specific experiment
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite

# Validate configuration before running
python -m elspeth.cli validate-schemas \
  --settings config/sample_suite/settings.yaml
```

---

!!! tip "Experiment Templates"
    The sample suite is a great starting point. Copy `config/sample_suite/` to create your own experiment suites with real data and LLMs.

!!! success "You Did It!"
    You've successfully run your first Elspeth experiment! The pipeline processed data through a mock LLM and generated multiple output formats. Ready to build something real? Continue to [First Experiment](first-experiment.md).
