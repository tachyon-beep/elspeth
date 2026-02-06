# Test Audit: tests/property/engine/test_token_properties.py

## Overview
Property-based tests for token management fork operations - critical for audit trail integrity.

**File:** `tests/property/engine/test_token_properties.py`
**Lines:** 351
**Test Classes:** 3

## Findings

### PASS - Critical Deepcopy Isolation Testing

This test file verifies the fix for a known bug where shallow copy caused mutation leakage between forked siblings.

**Strengths:**
1. **Object identity verified** - Each child has different PipelineRow instance
2. **Deep nesting tested** - Recursively verifies nested mutable objects are independent
3. **Parent preservation tested** - Parent unchanged after fork
4. **Metadata correctness** - row_id, token_id, branch_name, fork_group_id verified
5. **Override behavior tested** - row_data override uses override, not parent data

### Issues

**1. Good Pattern - Isolation verification (Lines 95-106)**
```python
for i in range(len(children)):
    for j in range(i + 1, len(children)):
        assert children[i].row_data is not children[j].row_data, (
            f"Children {i} and {j} share the same PipelineRow instance! "
            "Fork must create independent copies via deepcopy."
        )
```
- Verifies ALL pairs have different object identities
- Critical for audit integrity

**2. Good Pattern - Deep independence check (Lines 166-179)**
```python
def check_independent_nested(obj1: Any, obj2: Any, path: str = "") -> None:
    """Recursively verify nested mutable objects are independent."""
    if isinstance(obj1, dict) and isinstance(obj2, dict):
        for key in obj1:
            if key in obj2:
                check_independent_nested(obj1[key], obj2[key], f"{path}.{key}")
    elif isinstance(obj1, list) and isinstance(obj2, list):
        for idx in range(min(len(obj1), len(obj2))):
            check_independent_nested(obj1[idx], obj2[idx], f"{path}[{idx}]")
    elif isinstance(obj1, (dict, list)):
        assert obj1 is not obj2, f"Mutable objects at {path} are shared!"
```
- Recursively checks nested mutable structures
- Catches shallow copy bugs at any nesting level

**3. Observation - Mock recorder returns preset children (Lines 47-55)**
```python
def _create_mock_recorder(branches: list[str]) -> MagicMock:
    mock_recorder = MagicMock()
    children = [MagicMock(token_id=f"child_{i}", ...) for i, branch in enumerate(branches)]
    mock_recorder.fork_token.return_value = (children, "fork_1")
    return mock_recorder
```
- Mocks the recorder to return known children
- Tests TokenManager logic in isolation
- **Acceptable** - integration tests verify full flow

**4. Good Pattern - Parent data preservation (Lines 196-227)**
```python
def test_fork_preserves_parent_data(self, row_data: dict[str, Any], branches: list[str]):
    ...
    original_parent_data = parent.row_data.to_dict()
    children, _ = manager.fork_token(...)

    for i, child in enumerate(children):
        assert child.row_data is not parent.row_data, ...

    assert parent.row_data.to_dict() == original_parent_data, "Parent data was changed after fork!"
```
- Verifies parent is not mutated by fork operation

### Coverage Assessment

| Fork Isolation | Property | Tested |
|----------------|----------|--------|
| Children have different PipelineRow | YES | |
| Nested mutable objects independent | YES | |
| Deep nesting isolation | YES | |
| Data content equivalent | YES | |

| Parent Preservation | Property | Tested |
|--------------------|----------|--------|
| Parent PipelineRow not shared | YES | |
| Parent data unchanged | YES | |
| Children have same data as parent | YES | |

| Metadata Correctness | Property | Tested |
|---------------------|----------|--------|
| Same row_id as parent | YES | |
| Unique token_ids | YES | |
| Correct branch_name | YES | |
| Non-None fork_group_id | YES | |

| Override Behavior | Property | Tested |
|-------------------|----------|--------|
| With override uses override | YES | |
| Without override uses parent | YES | |

## Verdict: PASS

Excellent test file that verifies the critical deepcopy fix for fork operations. The recursive independence check is particularly valuable for catching shallow copy bugs at any nesting depth.

The comment at the top referencing tokens.py:151-153 documents that this test was written in response to a known bug, making it a regression test as well as a property test.
