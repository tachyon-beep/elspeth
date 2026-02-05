# Audit: tests/plugins/test_protocol_lifecycle.py

## Summary
Tests verifying that plugin protocols define `close()` lifecycle method. Minimal tests with limited practical value.

## Findings

### 1. Tests That Do Nothing - hasattr Checks

**Location:** Lines 15-17, 73-75

**Issue:** Tests `test_protocol_has_close_method` only verify `hasattr(TransformProtocol, "close")`. This is trivially true for any Protocol that defines the method - it provides no assurance the method works or is called.

**Severity:** Low - these are contract documentation tests, not behavioral tests.

### 2. Excessive Boilerplate in Test Classes

**Location:** Lines 28-67, 83-119

**Issue:** The inline test classes (MyTransform, MyGate) duplicate significant protocol boilerplate. They define many attributes that aren't relevant to the lifecycle test:
- `routes`, `fork_to`, `determinism`, `plugin_version`
- `is_batch_aware`, `creates_tokens`, `_on_error`

**Impact:** Makes tests harder to maintain and understand.

### 3. Type Ignore Annotations

**Location:** Lines 60, 63, 112, 115

**Issue:** Multiple `# type: ignore[unreachable]` comments indicate mypy doesn't believe the isinstance checks should pass. This suggests either:
- The test classes don't fully implement the protocol
- There's a mypy configuration issue

**Severity:** Low - runtime behavior is correct, but type system disagreement warrants investigation.

### 4. Redundant Protocol Conformance Tests

**Location:** Lines 58-67, 110-119

**Issue:** These tests verify that a class implementing all protocol methods satisfies `isinstance(x, Protocol)`. This tests Python's Protocol mechanism, not ELSPETH code.

**Recommendation:** Remove these or consolidate into a single "Protocol basics work" test.

## Missing Coverage

1. **No test for Source close()** - only Transform and Gate are tested
2. **No test for Sink close()** - significant omission
3. **No test for on_start/on_complete hooks** - lifecycle includes more than close()
4. **No integration test** verifying close() is called by engine on shutdown
5. **No test for exception handling** in close()

## Structural Issues

None - test classes are properly named and will be discovered.

## Verdict

**Overall Quality:** Poor

These tests verify Python's Protocol mechanism works but provide almost no value for ELSPETH. They don't test:
- That the engine calls close()
- What happens when close() throws
- Resource cleanup behavior

## Recommendations

1. **Delete these tests** or consolidate into test_protocols.py
2. Add integration tests verifying engine calls lifecycle methods in correct order
3. Add tests for exception handling in lifecycle methods
4. If keeping, simplify test classes by removing irrelevant protocol attributes
