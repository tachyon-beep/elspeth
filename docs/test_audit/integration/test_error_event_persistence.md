# Test Audit: test_error_event_persistence.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_error_event_persistence.py`
**Lines:** 543
**Batch:** 100-101

## Summary

Tests validation and transform error persistence to the Landscape audit database, including the `explain()` lineage query functionality.

## Audit Findings

### 1. DEFECT: Manual Token Creation Bypasses Production Path

**Severity:** Medium
**Location:** Lines 157-170, 240-254

The tests manually insert tokens directly into the database using raw SQL:

```python
with landscape_db.connection() as conn:
    conn.execute(
        tokens_table.insert().values(
            token_id="token-123",
            row_id=row.row_id,
            step_in_pipeline=0,
            created_at=datetime.now(UTC),
        )
    )
    conn.commit()
```

This bypasses `recorder.create_token()` which is the production path. While the comment says "to match test expectations," this:
- Avoids exercising the actual token creation logic
- Hardcodes token IDs which may mask issues with token ID generation
- Creates tokens with potentially incomplete fields that `create_token()` would populate

**Recommendation:** Use `recorder.create_token()` and capture the returned token's ID instead of hardcoding.

### 2. STRUCTURAL: PluginContext node_id Mismatch

**Severity:** Low
**Location:** Lines 186-189, 268-273

The `PluginContext` is created with `node_id="transform_node"` but the transform is registered as `"price_calculator"` or `"validator"`:

```python
# Registered node
recorder.register_node(
    run_id=run_id,
    plugin_name="price_calculator",
    node_id="price_calculator",  # <-- Registered as this
    ...
)

# Context uses different node_id
ctx = PluginContext(
    run_id=run_id,
    config={},
    landscape=recorder,
    node_id="transform_node",  # <-- Different!
)
```

This discrepancy doesn't cause test failure because `record_transform_error` uses the explicit `transform_id` parameter, but it's misleading and could hide real integration issues.

### 3. COVERAGE: Missing Edge Cases

**Severity:** Low

Missing test coverage for:
- Validation errors with NULL/empty row data
- Transform errors with very large `error_details` (payload store boundary)
- Concurrent error recording from multiple threads
- Error recording after run completion (should it be rejected?)
- Schema mode "observed" vs "fixed" behavior differences in validation errors

### 4. GOOD: Comprehensive Lineage Testing

The `TestErrorEventExplainQuery` class properly tests:
- Single validation errors in lineage
- Single transform errors in lineage
- Empty error lists for clean rows
- Multiple errors for the same token

### 5. STRUCTURAL: Import Inside Test Methods

**Severity:** Minor
**Location:** Lines 157-159, 241-243

```python
from datetime import datetime
from elspeth.core.landscape.schema import tokens_table
```

Imports are placed inside test methods. While functional, this is inconsistent with the module's style (other imports at top level) and can slow down test execution due to repeated import resolution.

### 6. GOOD: Fixture Usage

Tests properly use pytest fixtures (`landscape_db`, `recorder`) provided by conftest, ensuring proper isolation and cleanup.

## Test Path Integrity

**Status:** VIOLATION (Minor)

The manual token insertion bypasses the production `recorder.create_token()` method. While this is done to control token IDs for assertion, it means the token creation path isn't exercised in these specific tests.

## Recommendations

1. **High Priority:** Replace manual token creation with `recorder.create_token()` and use the returned token's ID
2. **Medium Priority:** Fix the node_id mismatch between registered nodes and PluginContext
3. **Low Priority:** Move inline imports to module level
4. **Enhancement:** Add edge case tests for concurrent errors and payload size boundaries
