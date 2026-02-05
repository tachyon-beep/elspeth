# Audit: tests/plugins/test_results.py

## Summary
Tests for plugin result types (RowOutcome, RoutingAction, TransformResult, GateResult, SourceRow). Well-structured with good coverage of immutability and defensive copy behavior.

## Findings

### 1. Strong Tests - Immutability Verification

**Location:** Lines 60-65

**Issue:** None - this is a positive finding.

**Quality:** `test_immutable` correctly verifies FrozenInstanceError is raised. Good defensive test.

### 2. Strong Tests - Defensive Copy

**Location:** Lines 67-79, 204-239

**Issue:** None - positive finding.

**Quality:** Tests verify that mutating original dicts doesn't affect stored values. Critical for audit integrity.

### 3. Redundant Deletion Tests

**Location:** Lines 152-165, 335-339, 355-359

**Issue:** Multiple tests verify `AcceptResult` and `AggregationProtocol` are deleted. These duplicate tests in other files.

**Severity:** Low - cleanup item.

### 4. Weak Assertion - has_audit_fields

**Location:** Lines 104-113, 139-149

**Issue:** Tests verify audit fields exist via `hasattr()` but don't verify they're used correctly:
```python
assert hasattr(result, "input_hash")
assert result.input_hash is None  # Not set yet
```

This only tests the dataclass has the field - not that the engine populates it.

**Severity:** Medium - provides false confidence about audit trail integration.

### 5. Tests That Do Nothing - Import Verification

**Location:** Lines 287-370

**Issue:** `TestPluginsPublicAPI` class mostly verifies imports work:
```python
from elspeth.plugins import GateResult, RoutingAction, ...
assert GateResult is not None
```

These are trivially true if imports don't fail. The `is not None` assertions add nothing.

**Severity:** Low - these are module contract tests, not behavioral tests.

### 6. Magic String Comparison

**Location:** Lines 35-41, 46-50

**Issue:** Tests compare routing action kinds to string literals:
```python
assert action.kind == "continue"
assert action.kind == "route"
```

But later tests (lines 171-202) correctly compare to enum values. Inconsistent approach.

**Severity:** Medium - could mask enum value changes if kind starts using enum exclusively.

### 7. Missing Test for SourceRow.valid()

**Location:** Lines 242-284

**Issue:** Tests cover `SourceRow.quarantined()` but not `SourceRow.valid()`. The happy path is untested here.

**Severity:** Low - likely tested elsewhere, but asymmetric coverage.

## Missing Coverage

1. **TransformResult.error() with row preservation** - some errors keep the row
2. **GateResult with routing reason details** - metadata verification
3. **SourceRow.valid() factory method**
4. **Result serialization** for audit trail
5. **Result equality semantics** if relevant

## Structural Issues

### Enum Comparison Inconsistency
Lines 35-57 use string comparison (`action.kind == "continue"`) while lines 171-202 use enum comparison (`action.kind == RoutingKind.CONTINUE`). Should be consistent.

## Verdict

**Overall Quality:** Good

Strong tests for immutability and defensive copying - critical for audit integrity. Main issues are:
- Inconsistent enum vs string comparisons
- Some redundant deletion tests
- Import verification tests add little value

## Recommendations

1. **Standardize on enum comparisons** throughout (remove string comparisons)
2. **Remove duplicate deletion tests** - keep in one location
3. **Remove trivial import assertions** (`assert X is not None`)
4. **Add SourceRow.valid() test** for completeness
5. **Add integration test** verifying engine sets audit fields (input_hash, output_hash, duration_ms)
