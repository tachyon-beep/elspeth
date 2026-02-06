# Test Audit: test_transform_contract_integration.py

**File:** `/home/john/elspeth-rapid/tests/integration/test_transform_contract_integration.py`
**Lines:** 456
**Batch:** 108

## Overview

Integration tests for schema contract propagation through transforms, verifying source-to-sink contract flow with original header restoration, contract preservation when transforms add fields, and PipelineRow dual-name access.

## Audit Findings

### 1. POSITIVE: Correct Production Code Path Usage

Tests use real plugins (CSVSource, CSVSink) as documented:

```python
source = CSVSource(
    {
        "path": str(input_csv),
        "normalize_fields": True,
        "schema": {"mode": "observed"},
        "on_validation_failure": "discard",
    }
)
```

This follows Test Path Integrity requirements.

---

### 2. STRUCTURAL: TestablePluginContext Duplication

**Severity:** Low
**Location:** Lines 33-66

Identical to `test_source_contract_integration.py`:

```python
class TestablePluginContext(PluginContext):
    """PluginContext subclass with validation error tracking for tests."""
```

**Recommendation:** Extract to shared fixtures module.

---

### 3. POSITIVE: End-to-End Contract Flow Testing

Tests verify the complete source -> transform -> sink contract flow:

```python
def test_original_headers_restored_in_output(self, tmp_path: Path) -> None:
    # Source creates contract
    source = CSVSource({...})
    rows = list(source.load(ctx))
    contract = source_row.contract

    # Sink uses contract for headers
    sink = CSVSink({...})
    sink.set_output_contract(contract)
    sink.write([source_row.row], ctx)

    # Output has original headers
    output_content = output_csv.read_text()
    assert "First Name!" in output_content
```

---

### 4. POSITIVE: Contract Propagation Testing

Thorough testing of `propagate_contract`:

```python
def test_contract_with_added_field(self, tmp_path: Path) -> None:
    output_row = {**source_row.row, "computed": 456}
    output_contract = propagate_contract(input_contract, output_row)

    # Original fields preserved
    assert output_contract.get_field("name") is not None

    # New field added with inferred type
    computed_field = output_contract.get_field("computed")
    assert computed_field.python_type is int
    assert computed_field.source == "inferred"
```

---

### 5. POSITIVE: Contract Merge Testing

Tests contract merge behavior for coalesce points:

```python
def test_contract_merge_compatible_types(self) -> None:
    merged = contract_a.merge(contract_b)
    assert merged.get_field("id") is not None
    assert merged.get_field("name") is not None
    assert merged.get_field("status") is not None

def test_contract_merge_type_conflict_raises(self) -> None:
    with pytest.raises(ContractMergeError) as exc_info:
        contract_a.merge(contract_b)
    assert "amount" in str(exc_info.value)
```

---

### 6. MISSING COVERAGE: Contract Merge With Different Original Names

**Severity:** Medium

Tests verify type conflict detection but not original name conflict:

```python
# What if two contracts have same normalized name but different original names?
contract_a = SchemaContract(fields=(
    FieldContract("amount", "Amount USD", int, True, "declared"),
))
contract_b = SchemaContract(fields=(
    FieldContract("amount", "Order Amount", int, True, "declared"),  # Different original!
))
```

Should test how merge handles this scenario.

---

### 7. MISSING COVERAGE: Sink Header Mode Edge Cases

**Severity:** Low

Tests cover:
- `headers: original`
- `headers: normalized`
- `headers: {custom_mapping}`

Missing:
- Mixed headers (some custom, some original/normalized)
- Empty contract with headers mode
- Fields in data but not in contract

---

### 8. POSITIVE: Passthrough Transform Contract Optimization

Tests verify contract instance reuse for passthrough:

```python
def test_passthrough_transform_preserves_contract(self, tmp_path: Path) -> None:
    output_contract = propagate_contract(input_contract, output_row, transform_adds_fields=False)
    assert output_contract is input_contract  # Same instance
```

This is an important optimization for the audit trail.

---

### 9. MISSING COVERAGE: Transform Chain Contract Propagation

**Severity:** Medium

Tests verify single transform propagation but not a chain:

```python
# Should test: source -> transform1 -> transform2 -> sink
# Verify contract evolves correctly through multiple transforms
```

---

### 10. STRUCTURAL: Test Organization

The tests are well-organized into logical test classes:
- `TestSourceToSinkContractFlow`
- `TestContractPreservationThroughTransforms`
- `TestContractWithSinkHeaderModes`
- `TestContractMergeAtCoalesce`

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Positive Findings | 6 | N/A |
| Missing Coverage | 3 | Medium, Medium, Low |
| Structural Issues | 1 | Low |
| Defects | 0 | N/A |

## Recommendations

1. **MEDIUM:** Add test for contract merge with conflicting original names
2. **MEDIUM:** Add test for transform chain contract propagation (source -> T1 -> T2 -> sink)
3. **LOW:** Add tests for edge cases in sink header modes
4. **LOW:** Extract TestablePluginContext to shared fixtures

## Overall Assessment

This is a comprehensive test file that properly verifies contract propagation through the pipeline. Uses production code paths correctly and makes meaningful assertions about contract behavior. The main gaps are in edge case coverage for merges and transform chains.
