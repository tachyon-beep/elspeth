# Test Audit: tests/property/engine/test_coalesce_properties.py

## Overview
Property-based tests for CoalesceExecutor merge policies, memory bounds, and data merge strategies.

**File:** `tests/property/engine/test_coalesce_properties.py`
**Lines:** 766
**Test Classes:** 8

## Findings

### PASS - Comprehensive Coalesce Testing

This is a large, well-structured test file covering critical fork/join semantics.

**Strengths:**
1. **All merge policies tested** - require_all, first, quorum, best_effort
2. **Memory bounds verified** - _completed_keys bounded, FIFO eviction
3. **Data merge strategies tested** - union, nested, select
4. **Late arrival handling** - Returns consistent failure
5. **Token conservation** - consumed_tokens equals arrived tokens
6. **Metadata correctness** - Policy, strategy, arrival order verified

### Issues

**1. Medium Priority - Heavy mock usage (Lines 94-138)**
```python
def make_mock_executor(clock: MockClock | None = None) -> CoalesceExecutor:
    mock_recorder = MagicMock()
    mock_recorder.begin_node_state.return_value = MagicMock(state_id="state-001")
    ...
```
- Creates CoalesceExecutor with mocked dependencies
- Tests CoalesceExecutor logic in isolation
- **Acceptable** - integration tests should exist elsewhere to verify real interactions

**2. Observation - make_token helper creates minimal TokenInfo (Lines 62-91)**
```python
def make_token(...) -> TokenInfo:
    ...
    contract = SchemaContract(mode="OBSERVED", fields=fields, locked=True)
    pipeline_row = PipelineRow(row_data, contract)
    return TokenInfo(...)
```
- Creates real TokenInfo with OBSERVED schema
- Good pattern for realistic test data

**3. Good Pattern - Policy-specific flush behavior (Lines 192-224, 350-394)**
- `test_require_all_never_partial_merge` - Verifies flush fails, doesn't partial merge
- `test_best_effort_merges_on_timeout` - Verifies timeout triggers merge

**4. Good Pattern - Memory bound verification (Lines 486-553)**
```python
def test_completed_keys_bounded_by_max(self) -> None:
    executor._max_completed_keys = 100
    ...
    for row_num in range(150):
        ...
    assert len(executor._completed_keys) <= 100
```
- Directly tests internal memory management
- Acceptable for verifying critical memory bounds

### Coverage Assessment

| Policy | Property | Tested |
|--------|----------|--------|
| require_all | Holds until all arrive | YES |
| require_all | Never partial merge | YES |
| first | Merges immediately | YES |
| quorum | Merges at exact threshold | YES |
| quorum | Flush fails below threshold | YES |
| best_effort | Merges on timeout | YES |

| Memory | Property | Tested |
|--------|----------|--------|
| Bounded keys | <= max_completed_keys | YES |
| FIFO eviction | Oldest evicted first | YES |

| Merge Strategy | Property | Tested |
|----------------|----------|--------|
| union | All fields present | YES |
| nested | Branch hierarchy | YES |
| select | Only selected branch | YES |

| Other | Property | Tested |
|-------|----------|--------|
| Late arrival | Returns failure | YES |
| Multiple late | All fail consistently | YES |
| Token conservation | Consumed = arrived | YES |
| Metadata | Policy/strategy recorded | YES |
| Metadata | Arrival order chronological | YES |

## Verdict: PASS

Comprehensive coverage of CoalesceExecutor behavior. The mock usage is appropriate for testing the coalesce logic in isolation. The tests verify critical invariants including memory bounds and merge policy correctness.
