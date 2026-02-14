## Summary

`ContractAuditRecord` accepts and restores invalid enum-like contract values (`mode`, `source`) without runtime validation, allowing corrupted/tampered audit records to pass integrity checks and silently change schema enforcement behavior.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `src/elspeth/contracts/contract_records.py`
- Line(s): 155, 164, 197, 191, 204
- Function/Method: `ContractAuditRecord.from_json`, `ContractAuditRecord.to_schema_contract`

## Evidence

`from_json` and `to_schema_contract` trust serialized string values directly:

```python
# src/elspeth/contracts/contract_records.py
mode=data["mode"]                  # line 155
source=f["source"]                 # line 164
...
contract = SchemaContract(
    mode=self.mode,                # line 197
    ...
)
...
source=f.source,                   # line 191
```

No runtime check enforces `mode in {"FIXED","FLEXIBLE","OBSERVED"}` or `source in {"declared","inferred"}` before returning a live `SchemaContract`.

Downstream logic depends on exact mode/source strings:
- `src/elspeth/contracts/schema_contract.py:285` only rejects extras when `self.mode == "FIXED"`.
- `src/elspeth/contracts/schema_contract.py:472` treats `source` with exact `"declared"` comparison.

Repro in this repo shows silent behavior drift (no crash):

- Constructed a record with `mode="BROKEN"` and matching `version_hash`.
- `to_schema_contract()` succeeded and returned `restored.mode == "BROKEN"`.
- `restored.validate({"a":1,"extra":2})` returned `0` violations (extras no longer rejected like FIXED mode would).
- Also restored `source="mystery"` without error.

## Root Cause Hypothesis

The module relies on `Literal[...]` type hints as if they were runtime validation. They are static-only. Hash verification checks consistency, not semantic validity, so invalid-but-self-consistent records are accepted.

## Suggested Fix

Add explicit runtime validation in `contract_records.py` before constructing/restoring contracts:

- Validate `ContractAuditRecord.mode` is one of `FIXED/FLEXIBLE/OBSERVED`.
- Validate each `FieldAuditRecord.source` is `declared/inferred`.
- Validate `python_type` key exists in `CONTRACT_TYPE_MAP` with a clear corruption error.
- Fail fast with `ValueError` that includes the invalid value and field name.
- Add unit tests for invalid `mode` and invalid `source` in `from_json` and `to_schema_contract`.

## Impact

This is a Tier-1 audit integrity gap: corrupted/tampered contract JSON can be accepted without immediate failure and alter schema enforcement semantics (especially FIXED-mode extra-field rejection), producing silently incorrect validation/audit outcomes.
