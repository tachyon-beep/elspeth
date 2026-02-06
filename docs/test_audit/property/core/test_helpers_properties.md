# Test Audit: tests/property/core/test_helpers_properties.py

## Overview
Property-based tests for landscape helper functions: `generate_id()`, `coerce_enum()`, and `now()`.

**File:** `tests/property/core/test_helpers_properties.py`
**Lines:** 298
**Test Classes:** 4

## Findings

### PASS - Proper Tier 1 Trust Model Testing

**Strengths:**
1. **coerce_enum tests verify crash semantics** - Invalid values raise ValueError, not silently coerce
2. **generate_id tests verify UUID4 format** - 32 lowercase hex chars, parseable as UUID4
3. **Timestamp tests verify UTC** - Timezone-aware, zero offset

### Minor Issues

**1. Low Priority - Redundant data parameter (Lines 65-67, 75-77, 108-110)**
```python
@given(st.data())
@settings(max_examples=100)
def test_generates_32_char_hex_string(self, data: st.DataObject) -> None:
    id_ = generate_id()  # data parameter not used
```
- The `data` parameter from `st.data()` is never used in these tests
- This is unnecessary overhead - the tests don't need Hypothesis data drawing
- Could be simple parameterized tests or use `st.none()` if just running N times

**2. Observation - Enum Test Strategy (Lines 44-54)**
```python
class SampleStatus(str, Enum):
    PENDING = "pending"
    ...
```
- Uses a test-local enum to avoid importing real ELSPETH enums
- This is appropriate for isolated property testing

**3. Good Pattern - Invalid enum value filtering (Lines 38-40)**
```python
invalid_enum_values = st.text(min_size=1, max_size=20).filter(
    lambda s: s not in ("PENDING", "RUNNING", "COMPLETED", "FAILED", "a", "b", "c")
)
```
- Correctly filters out valid values to ensure invalid inputs

### Coverage Assessment

| Function | Property | Tested |
|----------|----------|--------|
| generate_id | 32 char hex | YES |
| generate_id | Lowercase | YES |
| generate_id | Uniqueness | YES |
| generate_id | UUID4 parseable | YES |
| coerce_enum | Passthrough | YES |
| coerce_enum | String coercion | YES |
| coerce_enum | Invalid crashes | YES |
| coerce_enum | Idempotent | YES |
| now | UTC timezone | YES |
| now | Timezone aware | YES |
| now | Zero offset | YES |

## Verdict: PASS

Minor inefficiency with unused `st.data()` parameters, but tests are correct and verify the important properties including Tier 1 crash semantics.
