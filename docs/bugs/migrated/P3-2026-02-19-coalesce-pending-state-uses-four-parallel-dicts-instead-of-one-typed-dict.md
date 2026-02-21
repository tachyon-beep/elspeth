## Summary

`_PendingCoalesce` dataclass in `coalesce_executor.py` tracks branch arrival state using four separate `dict[str, X]` fields all keyed by branch name: `arrived`, `arrival_times`, `pending_state_ids`, and `lost_branches`. This is a classic "parallel arrays" pattern — four separate data structures tracking aspects of the same entity (a branch's arrival state).

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/engine/coalesce_executor.py` — Lines 59-63

## Evidence

```python
@dataclass
class _PendingCoalesce:
    arrived: dict[str, TokenInfo]      # branch_name → token
    arrival_times: dict[str, float]    # branch_name → monotonic time
    pending_state_ids: dict[str, str]  # branch_name → state_id
    lost_branches: dict[str, str]      # branch_name → loss reason
```

All four dicts share the same key space (branch names). Adding, removing, or querying a branch requires touching multiple dicts in sync. A missed update to one dict would silently desynchronize the state.

## Proposed Fix

Create `BranchArrivalState` dataclass and use a single dict:

```python
@dataclass(frozen=True, slots=True)
class BranchArrivalState:
    token: TokenInfo
    arrival_time: float
    state_id: str

@dataclass
class _PendingCoalesce:
    arrived: dict[str, BranchArrivalState]
    lost_branches: dict[str, str]  # separate — lost branches don't have tokens
```

## Affected Subsystems

- `engine/coalesce_executor.py` — internal state management
