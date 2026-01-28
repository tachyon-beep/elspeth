# Field Normalization at Source Boundary

**Date:** 2026-01-29
**Status:** Approved
**Author:** Design collaboration (user + Claude)

## Problem Statement

The schema contract feature (commit `be6a6a3`) assumes field names are valid Python identifiers (e.g., `customer_id`, `text`). Real-world CSV headers are often messy:

- `"CaSE Study1 !!!! xx!"` - special characters, mixed case
- `"User ID"` - spaces
- `"123_field"` - leading digits
- Missing headers entirely (headerless files)

This is a Tier 3 boundary problem: external data normalization belongs at the source.

## Design Goals

1. **Normalize messy headers** to valid Python identifiers automatically
2. **Support explicit overrides** when auto-normalization isn't enough
3. **Handle headerless files** with explicit column definitions
4. **Fail fast** on collisions, invalid mappings, or unparseable headers
5. **Full audit trail** of original-to-final field name resolution

## Configuration Schema

New options for source plugins that read tabular external data:

```yaml
source:
  plugin: csv
  options:
    path: data.csv

    # For headerless files - ordered list of column names
    # Mutually exclusive with reading headers from file
    columns: [id, name, amount, category]

    # Auto-normalize messy headers to valid Python identifiers
    # Default: false (backwards compatible)
    normalize_fields: true

    # Override specific normalized names
    # Keys are normalized names, values are final names
    field_mapping:
      case_study1_xx: cs1
      user_id: uid

    # Existing schema config unchanged
    schema:
      mode: free
      fields:
        - "cs1: str"
        - "uid: int"
```

### Option Interactions

| `columns` | `normalize_fields` | `field_mapping` | Behavior |
|-----------|-------------------|-----------------|----------|
| Not set | `false` | Not set | Current behavior - raw headers used as-is |
| Not set | `true` | Not set | Headers auto-normalized |
| Not set | `true` | Set | Headers auto-normalized, then mapping applied |
| Not set | `false` | Set | Error: mapping without normalization is ambiguous |
| Set | N/A | Not set | Headerless mode - columns used directly |
| Set | `true` | N/A | Error: normalize_fields incompatible with columns |
| Set | N/A | Set | Headerless mode with mapping overrides allowed |

## Normalization Algorithm

When `normalize_fields: true`, these rules apply in order:

```python
def normalize_field_name(raw: str) -> str:
    """Normalize messy header to valid Python identifier.

    Rules applied in order:
    1. Strip leading/trailing whitespace
    2. Lowercase
    3. Replace non-identifier chars (not letter/digit/underscore) with underscore
    4. Collapse consecutive underscores to single underscore
    5. Strip leading/trailing underscores
    6. If result starts with digit, prefix with underscore
    7. If result is empty, raise error (header is unparseable)
    """
```

### Examples

| Raw Header | Normalized | Notes |
|------------|------------|-------|
| `"CaSE Study1 !!!! xx!"` | `case_study1_xx` | Spaces and `!` → `_`, collapsed |
| `"User ID"` | `user_id` | Space → `_` |
| `"123_field"` | `_123_field` | Leading digit gets `_` prefix |
| `"data.field"` | `data_field` | Dot → `_` |
| `"  Amount  "` | `amount` | Whitespace stripped |
| `"!!!"` | **ERROR** | Nothing left after normalization |

## Processing Flow

### Init Phase (Fail Fast)

```
1. Parse config options

2. Determine headers:
   IF columns provided:
       headers = config.columns
       (headerless mode - file has no header row)
   ELSE:
       Read first row as raw_headers
       IF file appears headerless (heuristics or error):
           FAIL: "CSV file has no header row. Provide 'columns' config"

       IF normalize_fields:
           headers = [normalize(h) for h in raw_headers]
           Check for collisions → FAIL if any duplicates
       ELSE:
           headers = raw_headers

3. Apply field mapping (if provided):
   FOR each key in field_mapping:
       IF key not in headers:
           FAIL: "field_mapping key '{key}' not in headers"
   headers = [field_mapping.get(h, h) for h in headers]

4. Build resolved_mapping for audit:
   resolved_mapping = {original: final for original, final in zip(raw_headers, headers)}

5. Store resolved_mapping in source metadata

6. Validate final headers satisfy schema (guaranteed_fields must be valid identifiers)
```

### Row Phase

```
1. Read values from file
2. Zip with final headers (pre-computed at init)
3. Validate against schema
4. Yield SourceRow
```

All mapping overhead is at init. Zero per-row cost.

## Error Handling

All failures are loud and early:

| Scenario | When Detected | Error Message |
|----------|---------------|---------------|
| Collision after normalization | Init | `"Field collision: 'Case Study 1' and 'case-study-1' both normalize to 'case_study_1'"` |
| Header normalizes to empty | Init | `"Header '!!!' at column 3 normalizes to empty string"` |
| Mapping key not found | Init | `"field_mapping key 'foo' does not match any normalized header. Available: [...]"` |
| Headerless without `columns` | Init | `"CSV has no header row. Provide 'columns' config for headerless files"` |
| `columns` count mismatch | First row | `"columns config has 4 fields but CSV row has 5 values"` |
| Duplicate in `columns` | Init | `"Duplicate field name 'id' in columns config"` |
| `columns` + `normalize_fields` | Init | `"normalize_fields cannot be used with columns (columns already provides clean names)"` |
| `field_mapping` without `normalize_fields` or `columns` | Init | `"field_mapping requires normalize_fields: true or columns config"` |

## Audit Trail

Recorded once per run in source node metadata:

```python
{
    "source_plugin": "csv",
    "path": "data.csv",
    "normalize_fields": true,
    "field_resolution": {
        # Complete lineage: raw header → final field name
        "CaSE Study1 !!!! xx!": "cs1",
        "User ID": "uid",
        "Amount": "amount",  # auto-norm only, no override
    },
    "field_mapping_applied": {
        # Just the explicit overrides configured
        "case_study1_xx": "cs1",
        "user_id": "uid"
    },
    "schema_config": { ... }
}
```

- `field_resolution`: Complete trace for any field (auditor asks "where did `cs1` come from?")
- `field_mapping_applied`: Shows configured overrides (auditor asks "what manual mappings were set?")

## Implementation Scope

### In Scope

**Shared infrastructure:**
- `src/elspeth/plugins/config_base.py` - `FieldNormalizationMixin` with core logic

**Source plugins:**
- `src/elspeth/plugins/sources/csv_source.py`
- `src/elspeth/plugins/sources/json_source.py`
- `src/elspeth/plugins/azure/blob_source.py`

**Tests:**
- Unit tests for normalization algorithm
- Integration tests for each source plugin
- Error case coverage

### Out of Scope (YAGNI)

| Not Doing | Why |
|-----------|-----|
| Regex-based mapping rules | Complexity explosion; explicit mapping is clearer |
| Per-column type coercion in mapping | Schema already handles type coercion |
| Fuzzy/approximate header matching | Too magic; prefer explicit `columns` for headerless |
| Reverse mapping at sinks | Sinks output clean names; use transform if messy output needed |
| Runtime mapping changes | Config is immutable per run |

## Backwards Compatibility

- Default `normalize_fields: false` preserves current behavior
- Existing pipelines with clean headers continue working unchanged
- New options are purely additive

## Success Criteria

1. Pipeline with `normalize_fields: true` transforms `"CaSE Study1 !!!! xx!"` → `case_study1_xx`
2. Field mapping `{case_study1_xx: cs1}` produces final name `cs1`
3. Headerless file with `columns: [a, b, c]` works correctly
4. Collision between two headers that normalize identically fails at init
5. Invalid mapping key fails at init with helpful error
6. Audit trail shows complete `field_resolution` mapping
7. Schema contract validation works with normalized/mapped field names
