## Summary

Azure batch LLM transform uses `row_mapping: dict[str, dict[str, Any]]` to map custom IDs to row metadata. The inner dict always has exactly two fields — `index: int` and `variables_hash: str` — but this shape is not expressed in the type system.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/plugins/llm/azure_batch.py` — Lines 535, 568-571

## Evidence

```python
# azure_batch.py
row_mapping: dict[str, dict[str, Any]] = {}  # Line 535

# Construction (line 568-571)
row_mapping[custom_id] = {
    "index": idx,
    "variables_hash": rendered.variables_hash,
}
```

The same two-field shape is constructed once and read back at result processing time. A typo in either key would silently produce a malformed mapping.

## Proposed Fix

Create a module-private frozen dataclass in `plugins/llm/azure_batch.py` (NOT in `contracts/` — this type does not cross subsystem boundaries):

```python
@dataclass(frozen=True, slots=True)
class _RowMappingEntry:
    index: int
    variables_hash: str
```

Then use `dict[str, _RowMappingEntry]` instead of `dict[str, dict[str, Any]]`.

## Affected Subsystems

- `plugins/llm/azure_batch.py` — construction and consumption

## Related Bugs

Part of a systemic pattern: 10 open bugs (all 2026-02-19) where `dict[str, Any]` crosses subsystem boundaries without type enforcement. This is the simplest of the 10 — one construction site, one consumption site, no audit trail serialization.

Precedent: `TokenUsage` frozen dataclass (`contracts/token_usage.py`, commit `dffe74a6`).

## Review Board Analysis (2026-02-19)

Four-agent review board assessed the proposed fix. Verdict: **Approve with changes**.

### Design Change: Location

**Move to `plugins/llm/azure_batch.py`, not `contracts/`** — `RowMappingEntry` has no consumer outside this one plugin. The `contracts/` module is a leaf package for types that cross subsystem boundaries; this type does not. Use a module-private name (`_RowMappingEntry`) to signal internal scope.

### Checkpoint Safety Risk

`row_mapping` lives inside checkpoint data (`azure_batch.py:535, 568, 682`). Per CLAUDE.md: "Data we wrote to our own database or checkpoint file is still Tier 1 when we read it back." If `_RowMappingEntry` changes the serialized shape when written to checkpoints, recovery across a code migration boundary would fail. Two approaches:

1. **If row_mapping is NOT serialized to checkpoint**: No risk. Use `_RowMappingEntry` directly — no `to_dict()` needed.
2. **If row_mapping IS serialized to checkpoint**: Add `to_dict()` that emits `{"index": ..., "variables_hash": ...}` and a `from_dict()` for recovery. Verify hash stability.

Investigate `azure_batch.py` checkpoint save/restore paths before implementing.

### Required Tests

- Construction test: verify fields stored and typed
- If checkpoint-serialized: round-trip test through checkpoint save/restore
