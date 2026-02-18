## Summary

Aggregation checkpoint state is `dict[str, Any]` throughout its entire lifecycle — construction in `AggregationExecutor.get_checkpoint_state()`, serialization through `CheckpointManager`, storage in Landscape, and deserialization in `restore_from_checkpoint()`. The dict has a well-defined, documented shape (`_version`, per-node token lists, batch IDs, elapsed timers, contracts), but this shape is enforced only by manual validation at restore time rather than by the type system.

## Severity

- Severity: moderate
- Priority: P2

## Location

- File: `src/elspeth/engine/executors/aggregation.py` — Lines 592, 624, 708
- File: `src/elspeth/core/checkpoint/manager.py` — Line 61
- File: `src/elspeth/engine/processor.py` — Line 184

## Evidence

The checkpoint state flows across 3 module boundaries:

```python
# aggregation.py — construction
def get_checkpoint_state(self) -> dict[str, Any]:  # untyped
    state: dict[str, Any] = {"_version": AGGREGATION_CHECKPOINT_VERSION}
    for node_id, tokens in self._token_buffers.items():
        state[node_id] = {
            "tokens": [...],  # list of token dicts
            "batch_id": ...,
            "elapsed_age_seconds": ...,
            "contract": ...,
        }
    return state

# manager.py — pass-through
def create_checkpoint(self, ..., aggregation_state: dict[str, Any] | None): ...

# processor.py — consumption
def __init__(self, ..., restored_agg_state: dict[NodeID, dict[str, Any]]): ...

# aggregation.py — manual shape validation at restore
def restore_from_checkpoint(self, state: dict[str, Any]) -> None:
    version = state["_version"]
    if not isinstance(tokens_data, list):
        raise ValueError(...)
```

## Proposed Fix

Create typed structures in `contracts/`:
- `AggregationCheckpoint` — outer container with `_version` and per-node entries
- `AggregationNodeState` — per-node state (tokens, batch_id, elapsed_age, contract)
- `AggregationTokenData` — per-token entry in buffer

This would replace manual shape validation at restore time with construction-time guarantees. The `restore_from_checkpoint` validation becomes a `from_dict()` Tier 1 boundary (crash on any anomaly).

## Affected Subsystems

- `engine/executors/aggregation.py` — construction and consumption
- `core/checkpoint/manager.py` — pass-through parameter
- `engine/processor.py` — pass-through parameter
- `contracts/checkpoint.py` — `aggregation_state: dict[str, Any] | None` field
