# Test Audit: test_source_contract_integration.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_source_contract_integration.py`
**Lines:** 424
**Batch:** 107

## Overview

End-to-end integration tests for source-to-contract-to-pipeline flow, verifying schema validation, contract creation/locking, PipelineRow dual-name access, and checkpoint serialization.

## Audit Findings

### 1. POSITIVE: Excellent Test Path Integrity

The tests correctly use production code paths:

```python
source = CSVSource(
    {
        "path": str(csv_file),
        "schema": {"mode": "observed"},
        "on_validation_failure": "discard",
    }
)
rows = list(source.load(ctx))
```

Uses real `CSVSource`, `SchemaContract`, `PipelineRow` classes as documented in the test header.

---

### 2. POSITIVE: Comprehensive Contract Lifecycle Testing

Tests cover the full contract lifecycle:
- Dynamic schema inference (`test_dynamic_schema_infer_and_lock`)
- Dual-name access (`test_dual_name_access`)
- Strict validation with quarantine (`test_strict_schema_validation`)
- Checkpoint round-trip (`test_contract_survives_checkpoint_round_trip`)
- PipelineRow checkpoint restoration (`test_pipeline_row_checkpoint_round_trip`)
- Quarantine behavior (`test_quarantined_row_cannot_convert_to_pipeline_row`)
- Field containment checks (`test_contract_field_containment_check`)
- FLEXIBLE mode (`test_contract_mode_flexible_with_declared_fields`)
- Empty source locking (`test_empty_source_locks_contract`)

---

### 3. STRUCTURAL: TestablePluginContext Duplication

**Severity:** Low
**Location:** Lines 28-66

The `TestablePluginContext` class is also defined in `test_transform_contract_integration.py`. This duplication could be extracted to a shared fixture.

```python
class TestablePluginContext(PluginContext):
    """PluginContext subclass with validation error tracking for tests."""
```

**Recommendation:** Move to `tests/conftest.py` or a dedicated fixtures module.

---

### 4. POSITIVE: Good Assertion Specificity

Tests make specific assertions about contract state:

```python
# Contract locked after first row
contract = source.get_schema_contract()
assert contract is not None
assert contract.locked is True
assert contract.mode == "OBSERVED"

# All rows have same contract
for row in rows:
    assert row.contract is contract
```

---

### 5. MISSING COVERAGE: Contract Versioning

**Severity:** Low

No tests verify behavior when contract version changes between checkpoint and restore. The `version_hash()` method is used but hash collision or mismatch scenarios aren't tested.

---

### 6. MISSING COVERAGE: STRICT Mode

**Severity:** Low

Tests cover OBSERVED, FIXED, and FLEXIBLE modes but not STRICT mode (if it exists). Verify if STRICT is a valid mode and add coverage if so.

---

### 7. POSITIVE: Checkpoint Round-trip Verification

Thorough verification of serialization/deserialization:

```python
checkpoint_data = contract.to_checkpoint_format()
restored = SchemaContract.from_checkpoint(checkpoint_data)

# Verify integrity
assert restored.mode == contract.mode
assert restored.locked == contract.locked
assert len(restored.fields) == len(contract.fields)
```

Field-by-field comparison ensures complete fidelity.

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Positive Findings | 5 | N/A |
| Missing Coverage | 2 | Low |
| Structural Issues | 1 | Low |
| Defects | 0 | N/A |

## Recommendations

1. **LOW:** Extract `TestablePluginContext` to shared fixtures
2. **LOW:** Add tests for contract version hash mismatch scenarios
3. **LOW:** Verify all schema modes have test coverage

## Overall Assessment

This is a well-structured integration test file with good coverage of the contract system. Uses production code paths correctly and makes specific, meaningful assertions.
