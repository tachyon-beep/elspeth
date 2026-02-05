# Test Audit: tests/core/landscape/test_row_data.py

**Lines:** 64
**Test count:** 9 test functions
**Audit status:** PASS

## Summary

This test file validates the `RowDataState` enum and `RowDataResult` type, which provide explicit state discrimination for row data retrieval (replacing ambiguous `dict | None` returns). The tests are focused, comprehensive, and verify important invariants around data availability states.

## Findings

### 🔵 Info

1. **Complete state coverage (lines 16-21)**: Tests verify all five `RowDataState` values exist with correct string representations: AVAILABLE, PURGED, NEVER_STORED, STORE_NOT_CONFIGURED, ROW_NOT_FOUND.

2. **Invariant validation (lines 31-37)**: Tests verify the critical invariants that AVAILABLE state requires non-None data, and non-AVAILABLE states require None data. This enforces the discriminated union pattern.

3. **Individual state tests (lines 39-57)**: Each non-AVAILABLE state has its own test verifying correct construction with `data=None`.

4. **Immutability test (lines 59-64)**: Verifies the frozen dataclass behavior using `FrozenInstanceError`.

5. **Good design validation**: The tests confirm that the `RowDataResult` type prevents the ambiguity problem described in the docstring - you cannot accidentally return data in a PURGED state or None data in an AVAILABLE state.

## Verdict

**KEEP** - Clean, focused tests that validate important type invariants. The tests ensure the discriminated union pattern is enforced, which prevents bugs where callers misinterpret row data state.
