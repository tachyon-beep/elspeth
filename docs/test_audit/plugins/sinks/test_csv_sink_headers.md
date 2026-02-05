# Test Audit: test_csv_sink_headers.py

**File:** `tests/plugins/sinks/test_csv_sink_headers.py`
**Lines:** 434
**Audit Date:** 2026-02-05
**Auditor:** Claude Opus 4.5

## Summary

Tests for CSVSink header mode integration with contracts. Covers the new `headers` configuration option, contract-based header resolution, and legacy `display_headers` compatibility. Well-organized with clear test classes for different scenarios.

## Findings

### 1. Defects

**SEVERITY: LOW**
- **Line 198:** Uses `== None` with a noqa comment to avoid mypy type narrowing. While the comment explains why, this is an unusual pattern that could confuse readers. Consider using `is None` with type narrowing handled differently, or using a helper function.

### 2. Overmocking

None identified. Tests appropriately use real file I/O and actual SchemaContract instances.

### 3. Missing Coverage

**SEVERITY: MEDIUM**
- No test for `headers: original` when contract has fields without `original_name` set
- No test for mixing header modes across multiple sinks in the same run
- Missing test for header mode with flexible schema that has extras

**SEVERITY: LOW**
- No test for `headers: original` with special characters in original names (beyond the single quote in `'Amount USD'`)
- No edge case test for contract with duplicate original names

### 4. Tests That Do Nothing

None identified.

### 5. Inefficiency

**SEVERITY: LOW**
- The `sample_contract` fixture is duplicated identically in three test classes (`TestCSVSinkContractSupport`, `TestCSVSinkHeaderModes`, `TestCSVSinkHeaderModeInteraction`). Should be moved to module-level or conftest.
- Similarly, `output_path` and `ctx` fixtures are duplicated across classes.

### 6. Structural Issues

**SEVERITY: LOW**
- File tests both CSV-specific behavior and some generic header mode behavior. Some tests might be better in a shared header mode test file.
- `TestCSVSinkLegacyDisplayHeadersCompatibility` is a single-test class. Could be a function or merged with another class.

## Positive Observations

1. Comprehensive coverage of header mode enum values (NORMALIZED, ORIGINAL, CUSTOM)
2. Tests clearly document the lazy resolution behavior and why it exists
3. Good test of fallback behavior when no contract is available
4. Tests both explicit `set_output_contract()` and implicit `ctx.contract` resolution paths
5. Legacy compatibility testing ensures existing configs continue working

## Recommendations

1. Extract duplicate fixtures to module-level conftest
2. Add tests for edge cases in original name resolution
3. Consider testing header mode inheritance/precedence more explicitly
4. Add tests for contract fields missing original_name
