## Summary

Coalesce merge metadata is constructed as `dict[str, Any]` and recorded to the Landscape audit trail as `context_after`. It has a clear, consistent shape — `policy`, `merge_strategy`, `expected_branches`, `branches_arrived`, `field_collisions`, `timeout_seconds` — but this shape is not expressed in the type system. Multiple construction sites build the same structure independently.

## Severity

- Severity: moderate
- Priority: P2

## Location

- File: `src/elspeth/engine/coalesce_executor.py` — Lines 49, 397, 595
- File: `src/elspeth/core/landscape/_node_state_recording.py` — Lines 129, 142 (consumer)

## Evidence

The metadata is built at multiple construction sites with the same shape:

```python
# coalesce_executor.py — CoalesceOutcome dataclass
@dataclass
class CoalesceOutcome:
    metadata: dict[str, Any] | None = None  # untyped

# coalesce_executor.py — construction (paraphrased)
metadata = {
    "policy": policy_name,
    "merge_strategy": strategy_name,
    "expected_branches": list(expected),
    "branches_arrived": list(arrived.keys()),
    "field_collisions": {field: [b1, b2] for ...},
    "timeout_seconds": timeout,
}
```

This dict is then passed to `complete_node_state(context_after=metadata)` and serialized to the Landscape — becoming permanent Tier 1 audit data.

## Proposed Fix

Create `CoalesceMetadata` as a frozen dataclass or TypedDict in `contracts/`:

```python
@dataclass(frozen=True, slots=True)
class CoalesceMetadata:
    policy: str
    merge_strategy: str
    expected_branches: tuple[str, ...]
    branches_arrived: tuple[str, ...]
    field_collisions: Mapping[str, tuple[str, ...]]
    timeout_seconds: float | None
```

## Affected Subsystems

- `engine/coalesce_executor.py` — construction
- `core/landscape/_node_state_recording.py` — consumption (context_after parameter)
