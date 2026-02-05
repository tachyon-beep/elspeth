# Test Audit: tests/property/engine/test_token_lifecycle_state_machine.py

## Overview
Property-based stateful tests for token lifecycle state machine using RuleBasedStateMachine.

**File:** `tests/property/engine/test_token_lifecycle_state_machine.py`
**Lines:** 736
**Test Classes:** 2

## Findings

### PASS - Comprehensive Token Lifecycle State Machine

This is an excellent state machine test that verifies critical audit trail invariants.

**Strengths:**
1. **Uses real database** - `LandscapeDB.in_memory()` for realistic testing
2. **Model-based verification** - Tracks expected token states
3. **Multiple invariants** - Token ID immutability, row linkage, fork children, outcomes
4. **Fork creates parent links** - Verified via database query
5. **Terminal states verified** - FORKED, COMPLETED, QUARANTINED have outcomes

### Issues

**1. Low Priority - Bundle management for active tokens (Lines 165-166)**
```python
active_tokens = Bundle("active_tokens")  # Tokens that can still transition
```
- Tokens are added to bundle but may become terminal
- Rules check state before processing, which is correct

**2. Good Pattern - multiple() return for fork (Lines 293-332)**
```python
@rule(target=active_tokens, token_id=active_tokens, branches=multiple_branches)
def fork_token(self, token_id: str, branches: list[str]) -> Any:
    ...
    return multiple(*child_ids)  # Return each child ID as separate bundle entry
```
- Correctly uses `multiple()` to add forked children to bundle individually

**3. Good Pattern - Invariant for fork children have parents (Lines 415-419)**
```python
@invariant()
def fork_children_have_parent_links(self) -> None:
    """Invariant: Fork children have parent_token_id recorded."""
    missing = verify_fork_children_have_parents(self.db, self.run.run_id)
    assert missing == 0, ...
```
- Verifies via database query that all forked children have parent links

**4. Good Pattern - Terminal state finality test (Lines 576-630)**
```python
def test_terminal_state_is_final(self, data: dict[str, Any]) -> None:
    """Property: Once a token reaches terminal state, no new outcomes can be recorded."""
    ...
    recorder.record_token_outcome(..., outcome=RowOutcome.COMPLETED, ...)

    with pytest.raises(IntegrityError):
        recorder.record_token_outcome(..., outcome=RowOutcome.QUARANTINED, ...)
```
- Verifies database constraint prevents multiple terminal outcomes

### Coverage Assessment

| State Machine Invariants | Tested |
|-------------------------|--------|
| Token ID immutable | YES |
| Token links to valid row | YES |
| Fork children have parent links | YES |
| Fork creates correct # children | YES |
| Terminal states have outcomes | YES |
| Model count matches database | YES |

| Additional Properties | Tested |
|----------------------|--------|
| Token ID uniqueness | YES |
| Fork atomic parent outcome | YES |
| Terminal state is final | YES |
| row_id preserved through lifecycle | YES |
| Coalesce creates merged token | YES |

| State Transitions | Tested |
|-------------------|--------|
| CREATED from source | YES (rule) |
| PROCESSING after transform | YES (rule) |
| FORKED after fork | YES (rule) |
| COMPLETED after sink | YES (rule) |
| QUARANTINED after failure | YES (rule) |

## Verdict: PASS

Excellent state machine test that uses real database operations and verifies critical audit trail invariants. The use of `multiple()` for fork returns and comprehensive invariants make this a robust test.
