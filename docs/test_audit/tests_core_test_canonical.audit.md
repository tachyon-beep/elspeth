# Test Audit: tests/core/test_canonical.py

**Lines:** 451
**Test count:** 38
**Audit status:** PASS

## Summary

This is a thorough, well-organized test suite for canonical JSON serialization and hashing, which is critical for audit trail integrity. The tests cover type normalization (NumPy, Pandas, Decimal), NaN/Infinity rejection, RFC 8785 compliance, hash stability, and public API exports. The golden hash test is particularly important for detecting accidental changes to canonicalization behavior.

## Findings

### 🔵 Info

1. **Lines 14-22: Cross-reference note** - Good documentation practice noting that basic float NaN/Infinity tests are in `test_canonical_mutation_gaps.py`, avoiding duplication while ensuring comprehensive coverage across files.

2. **Lines 209-264: Unsupported type rejection tests** - Excellent defensive testing that documents expected behavior when unsupported types (UUID, custom classes, sets) reach the serialization boundary. These tests verify the defense-in-depth boundary at `rfc8785.dumps()`.

3. **Lines 381-415: Golden hash stability test** - Critical test that verifies hash consistency across time. The `test_golden_hash_stability` test with a hardcoded expected hash value is essential for catching accidental changes that would compromise audit trail integrity. The failure message appropriately warns about audit trail implications.

4. **Lines 71-103: Decimal non-finite rejection** - Comprehensive coverage of Decimal NaN and Infinity variants (including signaling NaN), ensuring the non-finite rejection extends beyond just Python floats.

5. **Lines 267-314: Recursive normalization tests** - Good coverage of nested structures with mixed types, including the important case of NaN buried in nested lists (`test_nan_in_nested_raises`).

6. **Lines 418-450: Public API and integration tests** - Validates that the expected symbols are importable from `elspeth.core`, which documents the public interface and catches accidental API breakage.

7. **Lines 145-173: Pandas type conversion** - Good coverage of pandas-specific types including `NaT` and `NA` sentinel values, and timezone-aware vs naive timestamp handling.

## Verdict

**KEEP** - This is a high-quality test suite for audit-critical functionality. The golden hash test, comprehensive type coverage, and proper documentation of test organization make this exemplary. No changes needed.
