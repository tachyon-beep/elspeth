# Audit: tests/plugins/test_hookspecs.py

## Summary
Very small test file verifying hookspec and hookimpl markers exist and hook methods are defined on spec classes.

## Findings

### 1. Issues

#### Tests Only Check Existence, Not Behavior
- **Location**: All tests
- **Issue**: Tests only use `hasattr()` to verify methods exist
- **Impact**: Medium - doesn't verify signatures, return types, or behavior
- **Recommendation**: Add tests that verify hook signatures:
```python
def test_source_hook_returns_list(self):
    sig = inspect.signature(ElspethSourceSpec.elspeth_get_source)
    # Verify return type annotation
```

#### No Tests for Hook Specification Decorators
- hookspec marker not verified to be pluggy.HookspecMarker
- hookimpl marker not verified to be pluggy.HookimplMarker

### 2. Missing Coverage

#### No Tests for Hook Calling
- No tests verify hooks can be called
- No tests verify hooks return expected types

#### Incomplete Spec Coverage
- Only checks methods exist, not their complete specification

### 3. Tests Provide Minimal Value

These tests would pass even if the methods did nothing:
```python
class ElspethSourceSpec:
    def elspeth_get_source(self): pass  # This would pass!
```

## Verdict
**WEAK PASS** - Tests exist but provide minimal assurance. Hook specifications need better verification.

## Risk Assessment
- **Defects**: None
- **Overmocking**: None
- **Missing Coverage**: High - signatures and behavior not tested
- **Tests That Do Nothing**: Medium - existence checks only
- **Inefficiency**: None
