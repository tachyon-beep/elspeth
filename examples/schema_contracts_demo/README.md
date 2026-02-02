# Schema Contracts Demo

This example demonstrates ELSPETH's **Unified Schema Contracts** feature with automatic header normalization.

## The Problem

Real-world CSV files often have messy headers:

```csv
Customer ID!!,  Amount (USD)  ,Transaction Date/Time,Status [Active/Inactive],NOTES & Comments
```

These can't be used directly as Python identifiers or dictionary keys without careful handling.

## The Solution: Schema Contracts

ELSPETH's schema contracts automatically:

1. **Normalize headers** to Python-safe identifiers:
   - `Customer ID!!` → `customer_id`
   - `  Amount (USD)  ` → `amount_usd`
   - `Transaction Date/Time` → `transaction_date_time`
   - `Status [Active/Inactive]` → `status_active_inactive`
   - `NOTES & Comments` → `notes_comments`

2. **Preserve original names** in the audit trail for compliance and debugging

3. **Infer types** from the first row of data

4. **Enable dual-name access** via `PipelineRow`:
   ```python
   row["customer_id"]        # Works (normalized)
   row["Customer ID!!"]      # Also works (original)
   ```

## Running the Example

```bash
# Execute the pipeline
uv run elspeth run -s examples/schema_contracts_demo/suite.yaml --execute

# Inspect the audit trail with MCP server
uv run elspeth-mcp --database sqlite:///examples/schema_contracts_demo/runs/audit.db
```

## MCP Analysis

After running, use these MCP tools to explore the contract:

```
> get_run_contract("<run_id>")
{
  "mode": "OBSERVED",
  "locked": true,
  "fields": [
    {"normalized_name": "customer_id", "original_name": "Customer ID!!", "python_type": "str"},
    {"normalized_name": "amount_usd", "original_name": "  Amount (USD)  ", "python_type": "float"},
    {"normalized_name": "status_active_inactive", "original_name": "Status [Active/Inactive]", "python_type": "str"},
    ...
  ]
}

> explain_field("<run_id>", "amount_usd")
{
  "normalized_name": "amount_usd",
  "original_name": "  Amount (USD)  ",
  "python_type": "float",
  "source": "inferred",
  "provenance": {"discovered_at": "source", "schema_mode": "OBSERVED"}
}
```

## Key Files

| File | Purpose |
|------|---------|
| `input.csv` | CSV with intentionally crazy headers |
| `suite.yaml` | Pipeline with `normalize_fields: true` and typed schema |
| `output/processed.csv` | Regular transactions (< $500) |
| `output/high_value.csv` | High-value transactions (>= $500) |
| `runs/audit.db` | Landscape audit trail with contract records |

## What Gets Recorded

The audit trail stores:

1. **Run-level contract**: Source schema with all field mappings
2. **Node contracts**: Input/output contracts per transform
3. **Validation errors**: Contract violation details if any rows fail validation

This enables complete field provenance tracing: "Why did field X have value Y?"
