# Test Audit: tests/property/core/test_row_data_properties.py

## Overview
Property-based tests for RowDataResult discriminated union invariants.

**File:** `tests/property/core/test_row_data_properties.py`
**Lines:** 272
**Test Classes:** 5

## Findings

### PASS - Correct Discriminated Union Testing

**Strengths:**
1. **State-data invariants tested** - AVAILABLE requires data, others require None
2. **Immutability verified** - Frozen dataclass cannot be mutated
3. **Enum integrity** - Round-trip, lowercase values, exactly 5 states
4. **Error message quality** - Descriptive error messages tested

### Issues

**1. Low Priority - Test file is small but thorough (272 lines)**
- Good ratio of test coverage to code size
- No issues, just observation

**2. Observation - Comprehensive combination test (Lines 102-121)**
```python
@given(state=all_states, data=st.one_of(st.none(), row_data_dicts))
def test_invariant_holds_for_all_combinations(self, state: RowDataState, data: ...) -> None:
    should_succeed = (state == RowDataState.AVAILABLE and data is not None) or \
                     (state != RowDataState.AVAILABLE and data is None)
    if should_succeed:
        result = RowDataResult(state=state, data=data)
        ...
    else:
        with pytest.raises(ValueError):
            RowDataResult(state=state, data=data)
```
- Tests ALL state x data combinations
- This is the definitive test for the discriminated union invariant

**3. Good Pattern - Canary test for enum (Lines 178-184)**
```python
def test_exactly_five_states_exist(self) -> None:
    """Property: Exactly 5 states are defined.

    Canary test - adding a new state should update this test.
    """
    states = list(RowDataState)
    assert len(states) == 5, ...
```
- Catches accidental enum changes

### Coverage Assessment

| Property | Tested | Notes |
|----------|--------|-------|
| AVAILABLE + data succeeds | YES | |
| AVAILABLE + None fails | YES | |
| Non-AVAILABLE + None succeeds | YES | All 4 states |
| Non-AVAILABLE + data fails | YES | |
| All combinations | YES | Exhaustive |
| Immutability (state) | YES | |
| Immutability (data) | YES | |
| State round-trip | YES | |
| State value lowercase | YES | |
| Exactly 5 states | YES | Canary |
| AVAILABLE is only data-carrying | YES | |
| Equality deterministic | YES | |
| Different states not equal | YES | |
| Error message clarity | YES | |

## Verdict: PASS

Excellent coverage of the discriminated union pattern. The exhaustive combination test (test_invariant_holds_for_all_combinations) is particularly valuable.
