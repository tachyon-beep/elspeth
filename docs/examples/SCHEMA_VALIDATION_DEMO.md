# DataFrame Schema Validation Demo (WP002)

## Status: Production Ready ✅

**Key Value Proposition**: **Fail fast at config-time, not at row 501.**

DataFrame schema validation ensures experiments fail immediately with clear error messages when datasource columns don't match plugin requirements, instead of crashing mysteriously during processing.

---

## Quick Start

### 1. Add Schema Declaration to Your Datasource

```yaml
datasource:
  plugin: local_csv
  security_level: OFFICIAL
  options:
    path: config/sample_suite/data/sample_input.csv
    # Declare expected columns with types
    schema:
      APPID: str
      title: str
      summary: str
      industry: str
```

### 2. Validate Schemas Before Running

```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --validate-schemas

# Output:
# ✅ Schema validation successful!
#    Datasource: CSVDataSource
#    Schema: sample_input_ConfigSchema
#    Columns: APPID, title, summary, industry
```

### 3. Run With Confidence

Schema validation happens automatically at config-time:
```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --head 0 \
  --live-outputs
```

---

## Feature Overview

### 1. Automatic Schema Inference

**Without explicit schema** (automatic inference from CSV):
```yaml
datasource:
  plugin: local_csv
  options:
    path: data/questions.csv
    infer_schema: true  # default
```

The system automatically:
- Reads first 100 rows of CSV
- Infers column types from pandas dtypes
- Attaches schema to DataFrame
- Validates at config-time

**DataFrame dtype mapping**:
- `int64` → `int`
- `float64` → `float`
- `object` → `str`
- `bool` → `bool`
- `datetime64` → `pd.Timestamp`

### 2. Explicit Schema Declaration

**With explicit schema** (recommended for production):
```yaml
datasource:
  plugin: local_csv
  options:
    path: data/questions.csv
    schema:
      APPID: str
      question: str
      score: int
      timestamp: datetime
```

**Benefits**:
- ✅ Clear contract between datasource and plugins
- ✅ Early detection of schema mismatches
- ✅ Self-documenting configuration
- ✅ Type safety throughout pipeline

### 3. Advanced Schema Constraints

**Extended format with validation rules**:
```yaml
datasource:
  plugin: local_csv
  options:
    path: data/ratings.csv
    schema:
      user_id:
        type: str
        required: true
      rating:
        type: int
        min: 1
        max: 5
      comment:
        type: str
        required: false
        max_length: 500
      confidence:
        type: float
        min: 0.0
        max: 1.0
```

**Supported constraints**:
- **Numeric**: `min`, `max` (maps to `>=` and `<=`)
- **String**: `min_length`, `max_length`, `pattern` (regex)
- **Optional**: `required: false` (allows `None` values)

---

## Schema Validation Flow

### Config-Time Validation (Fail Fast)

```
┌──────────────────────────┐
│ 1. Load Datasource       │
│    - Read CSV/DataFrame  │
│    - Attach schema       │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│ 2. Validate Plugins      │
│    - Check row plugins   │
│    - Check aggregators   │
│    - Check validators    │
└────────────┬─────────────┘
             │
             ▼
     Schema Compatible?
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
   ✅ PASS       ❌ FAIL
   Continue      Abort with
   to rows       clear error
```

**Error Example**:
```
SchemaCompatibilityError: Plugin 'row_plugin:data_quality_check' requires columns not provided by datasource: ['validation_status']
Datasource provides: ['APPID', 'title', 'summary', 'industry']
Plugin requires: ['APPID', 'title', 'validation_status']
```

### Runtime Validation (Optional Malformed Data Routing)

For cases where you want to process rows despite schema violations:

```yaml
experiments:
  - name: tolerant_processing
    validation:
      on_schema_violation: route  # "abort" | "route" | "skip"
      malformed_data_sink:
        type: csv
        path: outputs/malformed_rows.csv
        security_level: OFFICIAL
```

**Modes**:
- **`abort`** (default): Stop on first schema violation
- **`route`**: Send malformed rows to dedicated sink, continue processing valid rows
- **`skip`**: Skip malformed rows with logging, continue processing

**Malformed data output** (`malformed_rows.csv`):
```json
{
  "malformed_data": [
    {
      "row_index": 42,
      "schema_name": "sample_input_ConfigSchema",
      "timestamp": "2025-10-14T10:30:15.123456",
      "validation_errors": [
        {
          "field": "score",
          "type": "int_parsing",
          "message": "value is not a valid integer",
          "input_value": "invalid"
        }
      ],
      "malformed_data": {
        "APPID": "APP-043",
        "title": "Test App",
        "score": "invalid"
      }
    }
  ],
  "count": 1,
  "schema_name": "sample_input_ConfigSchema"
}
```

---

## CLI Commands

### Validate Schemas Without Running

Pre-flight check before expensive LLM calls:
```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --validate-schemas
```

**Output on success**:
```
INFO:elspeth.cli:Validating datasource schema compatibility...
INFO:elspeth.cli:✓ Datasource loaded successfully: 3 rows, 4 columns
INFO:elspeth.cli:✓ Schema found: sample_input_ConfigSchema
INFO:elspeth.cli:  Columns: ['APPID', 'title', 'summary', 'industry']
INFO:elspeth.cli:✓ Schema validation passed

✅ Schema validation successful!
   Datasource: CSVDataSource
   Schema: sample_input_ConfigSchema
   Columns: APPID, title, summary, industry
```

**Output on failure**:
```
ERROR:elspeth.cli:✗ Schema validation failed: Plugin 'row_plugin:score_extractor' requires column 'score' not provided by datasource

❌ Schema validation failed: SchemaCompatibilityError: ...
```

### Run Suite With Schema Validation

Schema validation happens automatically:
```bash
python -m elspeth.cli \
  --settings config/sample_suite/settings.yaml \
  --suite-root config/sample_suite \
  --live-outputs
```

---

## Real-World Examples

### Example 1: Question Answering Dataset

**Datasource CSV** (`qa_dataset.csv`):
```csv
question_id,question_text,context,expected_answer
Q001,What is the capital of France?,Geography questions,Paris
Q002,Who wrote Hamlet?,Literature questions,Shakespeare
```

**Configuration**:
```yaml
datasource:
  plugin: local_csv
  security_level: OFFICIAL
  options:
    path: data/qa_dataset.csv
    schema:
      question_id: str
      question_text: str
      context: str
      expected_answer: str

experiments:
  - name: qa_evaluation
    prompt_pack: qa_pack
    row_plugins:
      - name: score_extractor
        # No schema needed - processes LLM responses only
```

### Example 2: Customer Feedback Analysis

**Datasource CSV** (`feedback.csv`):
```csv
feedback_id,customer_id,rating,comment,category
FB001,CUST-123,4,Great service!,Support
FB002,CUST-456,5,Excellent product,Product
```

**Configuration with constraints**:
```yaml
datasource:
  plugin: local_csv
  security_level: PROTECTED
  options:
    path: data/feedback.csv
    schema:
      feedback_id: str
      customer_id: str
      rating:
        type: int
        min: 1
        max: 5
      comment:
        type: str
        max_length: 1000
      category:
        type: str
```

### Example 3: Malformed Data Handling

**Use case**: Process all valid rows, quarantine malformed rows for manual review.

**Configuration**:
```yaml
suite:
  defaults:
    datasource:
      plugin: local_csv
      options:
        path: data/mixed_quality.csv
        schema:
          record_id: str
          value: int  # Expecting integer
          status: str

experiments:
  - name: robust_processing
    validation:
      on_schema_violation: route
      malformed_data_sink:
        type: csv
        path: outputs/quarantine.csv
        security_level: OFFICIAL
```

**Result**: Valid rows processed normally, malformed rows (e.g., `value="abc"`) written to quarantine CSV for analysis.

---

## Integration with Existing Features

### Security Levels

Schemas respect security classification:
```yaml
datasource:
  plugin: local_csv
  security_level: PROTECTED  # Schema inherits classification
  options:
    schema:
      customer_name: str  # PROTECTED data
      purchase_amount: float
```

### Determinism Levels

Schema validation is deterministic:
```yaml
datasource:
  plugin: local_csv
  determinism_level: guaranteed  # Schema validation is reproducible
  options:
    schema:
      test_id: str
      score: int
```

### Artifact Pipeline

Schemas flow through artifact pipeline:
```yaml
sinks:
  - plugin: csv
    path: outputs/validated_results.csv
    # Schema from datasource propagates to sink outputs
```

---

## Best Practices

### 1. Always Declare Schemas in Production

❌ **Bad** (implicit, error-prone):
```yaml
datasource:
  plugin: local_csv
  options:
    path: data/input.csv
```

✅ **Good** (explicit, safe):
```yaml
datasource:
  plugin: local_csv
  options:
    path: data/input.csv
    schema:
      id: str
      text: str
      score: int
```

### 2. Use Pre-Flight Validation

Before expensive suite runs:
```bash
# Step 1: Validate schemas (fast)
python -m elspeth.cli --settings config.yaml --validate-schemas

# Step 2: Run suite (expensive)
python -m elspeth.cli --settings config.yaml --suite-root suites/prod --live-outputs
```

### 3. Handle Malformed Data Gracefully

For real-world messy data:
```yaml
validation:
  on_schema_violation: route  # Don't fail entire suite
  malformed_data_sink:
    type: csv
    path: outputs/quarantine_{experiment_name}.csv
```

### 4. Document Schema Requirements

Add comments to config:
```yaml
datasource:
  plugin: local_csv
  options:
    path: data/survey_responses.csv
    # Schema matches survey v3 format (2024-10-01)
    # Required columns: respondent_id, question_code, answer_text
    schema:
      respondent_id: str
      question_code: str
      answer_text: str
      timestamp: datetime
```

---

## Testing

### Unit Tests for Schema Validation

Located in `tests/test_schema_validation.py`:
```python
def test_schema_from_config():
    """Test schema construction from YAML config."""
    config = {"name": "str", "age": "int"}
    schema = schema_from_config(config)
    assert "name" in schema.__annotations__
    assert "age" in schema.__annotations__

def test_validate_schema_compatibility():
    """Test datasource-plugin schema compatibility."""
    datasource_schema = schema_from_config({"a": "str", "b": "int", "c": "float"})
    plugin_schema = schema_from_config({"a": "str", "b": "int"})
    validate_schema_compatibility(datasource_schema, plugin_schema)  # Should pass

def test_validate_schema_incompatibility():
    """Test detection of missing columns."""
    datasource_schema = schema_from_config({"a": "str"})
    plugin_schema = schema_from_config({"a": "str", "b": "int"})
    with pytest.raises(SchemaCompatibilityError):
        validate_schema_compatibility(datasource_schema, plugin_schema)
```

### Integration Test

Run sample suite with schema validation:
```bash
python -m pytest tests/test_schema_validation_integration.py -v
```

---

## Troubleshooting

### Error: "Column 'X' not found in datasource"

**Problem**: Plugin requires a column that datasource doesn't provide.

**Solution**: Either add the column to your CSV or remove the plugin dependency.

```yaml
# Option 1: Add column to CSV
APPID,title,summary,score
...

# Option 2: Remove plugin that requires 'score' column
row_plugins: []  # Remove score_extractor if it needs 'score'
```

### Error: "Type mismatch for column 'X'"

**Problem**: Datasource provides wrong type (e.g., `str` when `int` expected).

**Solution**: Fix CSV data types or adjust schema:
```yaml
schema:
  score: str  # Change from int to str if CSV has string scores
```

### Warning: "No schema defined - validation skipped"

**Problem**: Datasource has no schema declaration.

**Solution**: Add explicit schema:
```yaml
datasource:
  options:
    schema:
      col1: str
      col2: int
```

---

## Files Delivered

### Implementation
1. `/home/john/elspeth/src/elspeth/core/schema.py` - Core Pydantic schema system (537 lines)
2. `/home/john/elspeth/src/elspeth/core/interfaces.py` - DataSource protocol with `output_schema()` method
3. `/home/john/elspeth/src/elspeth/plugins/datasources/csv_local.py` - CSV datasource with schema support
4. `/home/john/elspeth/src/elspeth/plugins/datasources/csv_blob.py` - Blob CSV datasource with schema support
5. `/home/john/elspeth/src/elspeth/core/experiments/plugins.py` - Plugin protocols with `input_schema()` method
6. `/home/john/elspeth/src/elspeth/core/experiments/runner.py` - ExperimentRunner with schema validation

### Configuration
7. `/home/john/elspeth/config/sample_suite/settings.yaml` - Updated with schema declarations

### CLI
8. `/home/john/elspeth/src/elspeth/cli.py` - Added `--validate-schemas` command

### Documentation
9. `/home/john/elspeth/docs/examples/SCHEMA_VALIDATION_DEMO.md` - This file

---

## Ready for Demo ✅

DataFrame schema validation is:
- ✅ **Production-ready** - Comprehensive Pydantic-based validation
- ✅ **Config-time validation** - Fail fast before expensive LLM calls
- ✅ **Flexible** - Automatic inference or explicit declaration
- ✅ **Safe** - Type safety throughout pipeline
- ✅ **CLI support** - Pre-flight validation command
- ✅ **Well-tested** - Integration with existing test suite
- ✅ **Documented** - Complete demo guide and examples

**Next Steps**:
1. Review this demo guide
2. Test with sample suite: `python -m elspeth.cli --settings config/sample_suite/settings.yaml --validate-schemas`
3. Run full suite: `make sample-suite`
4. Present to stakeholders with live examples

**Demo Script** (2 minutes):
1. Show config with schema declaration (10 seconds)
2. Run `--validate-schemas` (10 seconds)
3. Show successful validation output (10 seconds)
4. Demonstrate schema error by removing a column (30 seconds)
5. Show error message clearly identifying the problem (30 seconds)
6. Fix and show green ✅ validation (30 seconds)

**Key Message**: "Fail fast at config-time, not at row 501" ✅
