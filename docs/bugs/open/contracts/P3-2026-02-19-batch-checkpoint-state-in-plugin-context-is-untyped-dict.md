## Summary

`PluginContext` manages batch checkpoint state as `dict[str, Any]` throughout — `_checkpoint`, `_batch_checkpoints`, `get_checkpoint()`, and `update_checkpoint()`. The checkpoint data has a known structure (batch_id, row_mapping, etc.) documented in `BatchPendingError`, but this structure is not enforced by the type system.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/contracts/plugin_context.py` — Lines 148, 152, 154-173, 175-188

## Evidence

```python
# plugin_context.py
_checkpoint: dict[str, Any]                     # Line 148
_batch_checkpoints: dict[str, dict[str, Any]]   # Line 152

def get_checkpoint(self) -> dict[str, Any] | None:   # Line 154
def update_checkpoint(self, data: dict[str, Any]):    # Line 175
```

The inner dict has fields like `batch_id`, `row_mapping`, `submitted_at` — all documented in usage but not in the type.

## Proposed Fix

Create `BatchCheckpointState` frozen dataclass or TypedDict in `contracts/` with the known fields. The `get_checkpoint()` / `update_checkpoint()` methods would use the typed structure.

## Affected Subsystems

- `contracts/plugin_context.py` — definition and access
- `plugins/llm/azure_batch.py` — checkpoint creation
- `plugins/llm/openrouter_batch.py` — checkpoint creation
