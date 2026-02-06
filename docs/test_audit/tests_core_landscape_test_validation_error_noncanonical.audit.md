# Test Audit: tests/core/landscape/test_validation_error_noncanonical.py

**Lines:** 379
**Test count:** 14
**Audit status:** PASS

## Summary

This test file verifies that validation errors can be recorded for non-canonical data (primitives, lists, NaN, Infinity) without crashing the system. This directly tests the Three-Tier Trust Model from CLAUDE.md - Tier 3 (external data) must be quarantined and recorded even when malformed. The tests verify both basic functionality and the repr() fallback mechanism for non-serializable data.

## Findings

### 🔵 Info

1. **Clear module docstring explaining purpose** - Lines 1-9 clearly explain the Three-Tier Trust Model connection and what non-canonical scenarios are being tested.

2. **Good fixture usage** - The `recorder` fixture (lines 20-45) creates a properly initialized test environment with run and source node registration, reducing boilerplate in individual tests.

3. **Thorough audit record verification** - `test_primitive_int_audit_record_verified` (lines 71-117) and `test_nan_audit_record_uses_repr_fallback` (lines 174-218) verify actual persisted database fields, not just return values. This follows the P1 pattern of verifying audit trail completeness.

4. **Testing the repr fallback mechanism** - Lines 256-293 verify that non-canonical data (NaN) triggers the repr() fallback and stores proper metadata structure (`__repr__`, `__type__`, `__canonical_error__`).

5. **Standalone utility tests** - `test_repr_hash_helper` (lines 330-346) and `test_noncanonical_metadata_structure` (lines 349-379) test the underlying utilities directly, providing defense in depth.

6. **Multiple non-canonical row types tested** - Lines 295-327 test primitive int, string, list, dict with NaN, and dict with Infinity all in one test, verifying the system handles various malformed data types.

7. **Frozen dataclass verification** - Line 378 verifies `NonCanonicalMetadata` is immutable by checking that assignment raises `AttributeError`.

### 🟡 Warning

1. **Minor duplication between tests** - `test_audit_trail_contains_repr_fallback` (lines 256-293) and `test_nan_audit_record_uses_repr_fallback` (lines 174-218) test similar behavior with some overlap. However, each has a distinct focus (one tests via direct table query, one tests via `get_validation_errors_for_run`), so this is acceptable.

## Verdict

**KEEP** - This is a well-structured test file that verifies critical Tier 3 data handling. The tests properly verify that malformed external data can be quarantined and recorded without crashing, which is essential for the audit trail to capture what actually happened with problematic data.
