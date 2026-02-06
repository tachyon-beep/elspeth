# Test Audit: tests/property/core/test_rate_limiter_state_machine.py

## Overview
Stateful property tests for rate limiter state machine using Hypothesis RuleBasedStateMachine.

**File:** `tests/property/core/test_rate_limiter_state_machine.py`
**Lines:** 403
**Test Classes:** 3

## Findings

### PASS - Well-Designed State Machine Tests

**Strengths:**
1. **RuleBasedStateMachine usage** - Explores state space systematically
2. **Model-based verification** - Tracks expected state for invariant checking
3. **Time-based testing** - Uses real sleep with short windows (2s)
4. **Invariant checking** - `never_exceed_limit_in_window` verified after each rule

### Issues

**1. Medium Priority - Timing tolerance in invariant (Lines 186-198)**
```python
@invariant()
def never_exceed_limit_in_window(self) -> None:
    ...
    # Allow small timing tolerance (tokens may have just leaked)
    assert tokens_in_window <= self.limit + 1, ...
```
- Allows limit + 1 due to timing races
- This is pragmatic but could theoretically mask bugs
- **Acceptable** for property tests with real time

**2. Observation - Comment about moved invariant (Lines 180-184)**
```python
# NOTE: The "rejections don't consume quota" property is tested in the
# non-stateful test_rejected_acquire_doesnt_consume_quota() below...
```
- Good documentation explaining why this property is tested elsewhere
- Shows thoughtful test design

**3. Good Pattern - Settings override for state machine (Lines 202-207)**
```python
TestRateLimiterStateMachine.settings = settings(
    max_examples=30,
    stateful_step_count=20,
    deadline=None,  # Disable deadline due to real time.sleep() calls
)
```
- Correctly disables deadline for time-based tests
- Reasonable step count for thorough exploration

**4. Good Pattern - Non-stateful complement tests (Lines 215-403)**
- Additional `@given` tests complement the state machine
- `test_rejected_acquire_doesnt_consume_quota` directly verifies important property
- `test_replenishment_after_wait` with `@pytest.mark.slow` for time-dependent tests

### Coverage Assessment

| Property | Tested By |
|----------|-----------|
| Accepts up to limit | State machine + direct test |
| Rejects over limit | State machine + direct test |
| Rejection doesn't consume quota | Direct test (correctly separated) |
| Token replenishment | State machine + direct test |
| Weight affects consumption | Direct test |
| Multiple rejections don't accumulate | Direct test |
| Resource cleanup | Direct tests |

## Verdict: PASS

Excellent use of state machine testing with appropriate handling of timing-sensitive tests. The separation of time-independent invariants (in state machine) from time-dependent properties (in direct tests) is good design.
