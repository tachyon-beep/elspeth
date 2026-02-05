# Test Audit: tests/property/core/test_reproducibility_properties.py

## Overview
Property-based tests for reproducibility grade computation and degradation logic.

**File:** `tests/property/core/test_reproducibility_properties.py`
**Lines:** 376
**Test Classes:** 5

## Findings

### PASS - Thorough Grade Classification Testing

**Strengths:**
1. **Determinism classification tested** - DETERMINISTIC/SEEDED -> FULL, others -> REPLAY
2. **Grade hierarchy verified** - FULL > REPLAY > ATTRIBUTABLE_ONLY
3. **Degradation logic tested** - REPLAY -> ATTRIBUTABLE after purge
4. **Idempotence verified** - degrade(degrade(x)) == degrade(x)
5. **Uses real database** - `LandscapeDB.in_memory()` for realistic testing

### Issues

**1. Low Priority - Composite strategy could simplify (Lines 76-81)**
```python
@st.composite
def lists_with_non_reproducible(draw: st.DrawFn) -> list[Determinism]:
    non_repro = draw(non_reproducible_determinism)
    others = draw(st.lists(all_determinism, min_size=0, max_size=5))
    return [non_repro, *others]
```
- Works correctly, ensures at least one non-reproducible determinism
- Could alternatively use `st.lists(...).filter(lambda l: any(...))` but composite is cleaner

**2. Observation - Database helper functions (Lines 89-132)**
```python
def _create_run(db: LandscapeDB) -> str:
    ...
def _insert_nodes(db: LandscapeDB, run_id: str, determinisms: list[Determinism]) -> None:
    ...
```
- Good encapsulation of database setup
- Direct SQL usage is appropriate for test setup

**3. Good Pattern - Enum canary test (Lines 143-150)**
```python
def test_exactly_three_grades_exist(self) -> None:
    """Property: Exactly 3 reproducibility grades are defined.

    Canary test - adding a new grade requires updating this test
    and the degradation logic.
    """
    grades = list(ReproducibilityGrade)
    assert len(grades) == 3, ...
```
- Catches unintentional enum changes

### Coverage Assessment

| Property | Tested | Notes |
|----------|--------|-------|
| Exactly 3 grades | YES | Canary test |
| Grade values lowercase | YES | |
| Grade round-trip through value | YES | |
| Grade is string subclass | YES | |
| No duplicate values | YES | |
| DETERMINISTIC/SEEDED -> FULL | YES | |
| IO_*/EXTERNAL_CALL/NON_DET -> REPLAY | YES | |
| Empty pipeline -> FULL | YES | |
| Grade hierarchy ordering | YES | |
| REPLAY degrades to ATTRIBUTABLE | YES | |
| FULL unchanged after purge | YES | |
| ATTRIBUTABLE unchanged after purge | YES | |
| Degradation idempotent | YES | |
| Degradation never increases grade | YES | |

## Verdict: PASS

Comprehensive testing of reproducibility classification and degradation. The use of real database operations ensures the tests verify actual behavior.
