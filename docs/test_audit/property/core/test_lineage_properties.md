# Test Audit: tests/property/core/test_lineage_properties.py

## Overview
Property-based tests for lineage query validation via `explain()` function.

**File:** `tests/property/core/test_lineage_properties.py`
**Lines:** 354
**Test Classes:** 6

## Findings

### PASS - Proper Input Validation Testing

**Strengths:**
1. **Argument validation thoroughly tested** - Must provide token_id OR row_id
2. **Ambiguity detection tested** - Multiple terminal tokens without sink raises ValueError
3. **Tier 1 trust tested** - Missing parent token crashes (Lines 291-319)
4. **Return value invariants tested** - None returned for not-found cases

### Issues

**1. Medium Priority - Mock-heavy tests may miss integration issues (Lines 54-109)**
```python
recorder = MagicMock()
recorder.get_token.return_value = None
result = explain(recorder, run_id, token_id=token_id)
```
- Tests use MagicMock for recorder extensively
- This verifies the explain() logic but not the recorder interactions
- Need integration tests elsewhere to verify real recorder behavior
- **Acceptable** for property tests focused on explain() contract

**2. Observation - LineageResult field assertions (Lines 236-280)**
```python
def test_required_fields_present(self) -> None:
    required_fields = {
        "token", "source_row", "node_states", ...
    }
    field_names = {f.name for f in fields(LineageResult)}
    assert required_fields.issubset(field_names)
```
- Tests dataclass structure rather than behavior
- Good as a canary test for schema changes

**3. Good Pattern - Tier 1 integrity test (Lines 291-319)**
```python
def test_missing_parent_token_crashes(self, run_id: str, token_id: str) -> None:
    """Property: Missing parent token raises ValueError (Tier 1 integrity)."""
    ...
    with pytest.raises(ValueError, match="Audit integrity violation"):
        explain(recorder, run_id, token_id=token_id)
```
- Correctly verifies that audit database corruption causes crashes

### Coverage Assessment

| Scenario | Tested | Notes |
|----------|--------|-------|
| Neither token nor row provided | YES | Raises ValueError |
| token_id alone | YES | Valid path |
| row_id alone | YES | Valid path |
| Both provided | YES | token_id takes precedence |
| No outcomes for row | YES | Returns None |
| No terminal outcomes | YES | Returns None |
| Sink filter no match | YES | Returns None |
| Multiple terminals no sink | YES | Raises ValueError |
| Multiple tokens same sink | YES | Raises ValueError |
| Token not found | YES | Returns None |
| Source row not found | YES | Returns None |
| Missing parent (Tier 1) | YES | Raises ValueError |

## Verdict: PASS

Mock usage is appropriate for testing explain() logic in isolation. The Tier 1 trust model is correctly verified with crash semantics for audit integrity violations.
