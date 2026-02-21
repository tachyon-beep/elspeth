## Summary

`ContractAuditRecord.from_json()` uses `f.get("nullable", False)` to deserialize the `nullable` field, treating it as optional with a backward-compat default. The serialization format (`FieldAuditRecord.to_json_dict()`) always writes `nullable`, making this a Tier 1 defensive pattern that masks corruption.

## Severity

- Severity: minor
- Priority: P3

## Location

- File: `src/elspeth/contracts/contract_records.py`
- Line: 194
- Function: `ContractAuditRecord.from_json()`

## Evidence

**Write side** (`FieldAuditRecord.to_json_dict()`, line 88) always includes `nullable`:
```python
def to_json_dict(self) -> dict[str, Any]:
    return {
        "normalized_name": self.normalized_name,
        "original_name": self.original_name,
        "python_type": self.python_type,
        "required": self.required,
        "source": self.source,
        "nullable": self.nullable,
    }
```

**Read side** treated it as optional:
```python
nullable=f.get("nullable", False),
```

Per the No Legacy Code Policy, there are no pre-nullable audit records to be backward-compatible with.

## Root Cause

Backward-compat shim left in place for hypothetical old data format that doesn't exist (no users yet).

## Fix Applied

1. Changed `f.get("nullable", False)` to `f["nullable"]` in `contract_records.py`
2. Replaced backward-compat test with crash-on-missing test (`test_missing_nullable_key_crashes`)

## Impact

Missing `nullable` key in audit JSON now correctly crashes as corruption instead of silently defaulting to `False`.
