## Summary

`SchemaContract.from_checkpoint()` uses `f.get("nullable", False)` to deserialize the `nullable` field from checkpoint data, treating it as optional. The checkpoint serialization format (`to_checkpoint_format()`) always writes `nullable`, making this a Tier 1 defensive pattern.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/contracts/schema_contract.py`
- Line: 393
- Function: `SchemaContract.from_checkpoint()`

## Evidence

**Write side** (`to_checkpoint_format()`, line 360) always includes `nullable`:
```python
{
    "normalized_name": fc.normalized_name,
    "original_name": fc.original_name,
    "python_type": fc.python_type.__name__,
    "required": fc.required,
    "source": fc.source,
    "nullable": fc.nullable,
}
```

**Read side** (line 393) treated it as optional with comment:
```python
nullable=f.get("nullable", False),  # Backward compat for old checkpoints
```

Per the No Legacy Code Policy, there are no old checkpoints.

## Root Cause

Same as contract_records.py — backward-compat shim for nonexistent legacy data.

## Fix Applied

1. Changed `f.get("nullable", False)` to `f["nullable"]` in `schema_contract.py`
2. Replaced backward-compat test with crash-on-missing test (`test_missing_nullable_crashes`)

## Impact

Missing `nullable` key in checkpoint data now correctly crashes as corruption instead of silently defaulting to `False`.
