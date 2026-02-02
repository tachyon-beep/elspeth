# Schema Contracts LLM Assessment Example

This example demonstrates ELSPETH's **Unified Schema Contracts** with LLM-powered medical case study assessment. It combines automatic header normalization with multi-query LLM evaluation.

## The Challenge

Medical data often comes with inconsistent, messy headers from various EMR systems:

```csv
'User ID #',  "Case Study 1 - Background Info"  ,'CS1: Symptoms & Signs',"CS1 >> Medical History"
```

These headers need to be:
1. Normalized for code access
2. Preserved for audit compliance (original names matter for traceability)
3. Type-tracked through the entire pipeline

## How Schema Contracts Solve This

The pipeline automatically:

| Original Header | Normalized Name | Tracked In |
|-----------------|-----------------|------------|
| `User ID #` | `user_id` | Contract |
| `Case Study 1 - Background Info` | `case_study_1_background_info` | Contract |
| `CS1: Symptoms & Signs` | `cs1_symptoms_signs` | Contract |
| `CS1 >> Medical History` | `cs1_medical_history` | Contract |
| `Case Study 2 - Background Info` | `case_study_2_background_info` | Contract |
| `CS2: Symptoms & Signs!!` | `cs2_symptoms_signs` | Contract |
| `CS2 >> Medical History` | `cs2_medical_history` | Contract |

## Prerequisites

```bash
export OPENROUTER_API_KEY="your-openrouter-api-key"
```

## Running the Example

```bash
# Execute the pipeline
uv run elspeth run -s examples/schema_contracts_llm_assessment/suite.yaml --execute

# Inspect the audit trail
uv run elspeth-mcp --database sqlite:///examples/schema_contracts_llm_assessment/runs/audit.db
```

## MCP Analysis: Tracing Field Provenance

After running, explore the schema contract:

```
> get_run_contract("<run_id>")
{
  "mode": "OBSERVED",
  "locked": true,
  "fields": [
    {
      "normalized_name": "user_id",
      "original_name": "'User ID #'",
      "python_type": "str",
      "required": true,
      "source": "inferred"
    },
    {
      "normalized_name": "case_study_1_background_info",
      "original_name": "Case Study 1 - Background Info",
      "python_type": "str",
      ...
    },
    ...
  ]
}
```

Trace a specific field's journey:

```
> explain_field("<run_id>", "cs1_symptoms_signs")
{
  "normalized_name": "cs1_symptoms_signs",
  "original_name": "'CS1: Symptoms & Signs'",
  "python_type": "str",
  "source": "inferred",
  "provenance": {
    "discovered_at": "source",
    "schema_mode": "OBSERVED"
  }
}
```

## Pipeline Flow

```
Input CSV (crazy headers)
    │
    ▼
┌─────────────────────────────┐
│ CSVSource                   │
│ - normalize_fields: true    │
│ - Creates SchemaContract    │  ──► Audit: runs.schema_contract_json
│   with field resolution     │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ OpenRouter Multi-Query LLM  │
│ - Uses NORMALIZED names     │
│ - input_contract from       │  ──► Audit: nodes.input_contract_json
│   upstream SchemaContract   │
│ - Adds score/rationale      │  ──► Audit: nodes.output_contract_json
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ CSVSink                     │
│ - Output with all fields    │
└─────────────────────────────┘
```

## Audit Trail Contents

The Landscape database stores:

1. **Run Contract** (`runs.schema_contract_json`)
   - Complete field mapping table
   - Version hash for integrity verification

2. **Node Contracts** (`nodes.input_contract_json`, `nodes.output_contract_json`)
   - What each node expected as input
   - What each node produced as output

3. **Validation Errors** (if any)
   - Contract violation type
   - Expected vs actual types
   - Original field name for debugging

## Why This Matters for Medical AI

In healthcare AI systems:

- **Compliance**: Auditors can trace "Which field in the original EMR export became `cs1_symptoms_signs`?"
- **Debugging**: When LLM assessment fails, you can see exact field provenance
- **Reproducibility**: Contract hashes verify data didn't change between runs
- **Multi-system integration**: Different EMR systems have different header conventions - contracts normalize them

## Key Files

| File | Purpose |
|------|---------|
| `input.csv` | Medical case studies with crazy headers |
| `suite.yaml` | Pipeline with `normalize_fields: true` |
| `criteria_lookup.yaml` | Assessment criteria definitions |
| `output/results.csv` | LLM assessment results |
| `runs/audit.db` | Full audit trail with contracts |
