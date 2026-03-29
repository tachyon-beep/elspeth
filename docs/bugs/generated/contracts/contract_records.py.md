## Summary

`ContractAuditRecord.from_json()` and `to_schema_contract()` accept non-boolean `locked` / `required` / `nullable` values from Tier-1 audit JSON, so corrupted records can restore into live contracts with silently wrong schema semantics instead of crashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/contract_records.py`
- Line(s): 162-203, 224-258
- Function/Method: `ContractAuditRecord.from_json`, `ContractAuditRecord.to_schema_contract`

## Evidence

`from_json()` validates enum-like strings (`mode`, `source`, `python_type`) but does not validate the JSON types of the boolean fields it restores:

```python
mode = data["mode"]
...
fields.append(
    FieldAuditRecord(
        normalized_name=f["normalized_name"],
        original_name=f["original_name"],
        python_type=python_type,
        required=f["required"],
        source=source,
        nullable=f["nullable"],
    )
)
...
return cls(
    mode=mode,
    locked=data["locked"],
    version_hash=data["version_hash"],
    fields=tuple(fields),
)
```

Source: `/home/john/elspeth/src/elspeth/contracts/contract_records.py:168-203`

`to_schema_contract()` then forwards those values unchanged into `SchemaContract` / `FieldContract`:

```python
FieldContract(
    ...
    required=f.required,
    source=f.source,
    nullable=f.nullable,
)
...
contract = SchemaContract(
    mode=self.mode,
    fields=fields,
    locked=self.locked,
)
```

Source: `/home/john/elspeth/src/elspeth/contracts/contract_records.py:243-259`

Those flags are later consumed with boolean semantics, not strict type checks:

```python
if fc.required and fc.normalized_name not in row:
...
if value is None and (not fc.required or fc.nullable):
```

Source: `/home/john/elspeth/src/elspeth/contracts/schema_contract.py:249-269`

```python
if not output_contract.locked:
    raise OrchestrationInvariantError(...)
```

Source: `/home/john/elspeth/src/elspeth/engine/tokens.py:361-365`

```python
if initial_contract.locked:
    self.set_schema_contract(initial_contract)
```

Source: `/home/john/elspeth/src/elspeth/plugins/sources/json_source.py:154-158`

So a corrupted audit record like `"nullable": "false"` or `"locked": "false"` is accepted, and Python truthiness then changes behavior:
- `"nullable": "false"` is truthy, so `None` is incorrectly accepted as valid.
- `"required": "false"` is truthy, so missing fields are incorrectly treated as required.
- `"locked": "false"` is truthy, so code that expects an unlocked contract treats it as locked.

This restore path is used by run recovery:

```python
audit_record = ContractAuditRecord.from_json(schema_contract_json)
contract = audit_record.to_schema_contract()
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py:444-446`

The current tests cover invalid enum strings and missing keys, but there is no coverage for non-boolean boolean fields in `tests/unit/contracts/test_contract_records.py`.

## Root Cause Hypothesis

The module treats JSON field presence as sufficient integrity checking and assumes the stored JSON came from trusted serializers. That leaves a Tier-1 gap: value-shape corruption is not rejected unless it happens to perturb the hash. Since these flags directly control validation and locking semantics, accepting wrong runtime types violates the “our data must be pristine” rule.

## Suggested Fix

Add explicit runtime type validation in `from_json()` and `to_schema_contract()`:
- `locked` must be `bool`
- each field’s `required` must be `bool`
- each field’s `nullable` must be `bool`
- optionally also validate `normalized_name`, `original_name`, and `version_hash` are `str`

Raise `AuditIntegrityError` with field-specific context on mismatch, e.g. “Field 'score' has non-bool nullable='false' in audit record”.

## Impact

A malformed audit record can be restored into a contract that looks valid enough to pass hash checks yet enforces the wrong schema:
- rows may be accepted or rejected incorrectly during validation
- resume/setup code can treat unlocked contracts as locked
- audit analysis based on restored contracts can report incorrect semantics

That is silent Tier-1 semantic corruption, which is exactly what the audit integrity checks are supposed to prevent.
---
## Summary

`ContractAuditRecord.from_json()` assumes the decoded payload shape is correct and can throw raw `TypeError`/indexing errors on malformed Tier-1 JSON, which bypasses the checkpoint corruption translation path and leaks an unclassified internal exception instead of an audit-integrity failure.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/contract_records.py`
- Line(s): 162-195
- Function/Method: `ContractAuditRecord.from_json`

## Evidence

`from_json()` immediately indexes into decoded JSON as though it were a fully valid object graph:

```python
data = json.loads(json_str)
...
for f in data["fields"]:
    source = f["source"]
    ...
    python_type = f["python_type"]
```

Source: `/home/john/elspeth/src/elspeth/contracts/contract_records.py:162-195`

If `data["fields"]` is not a list of dicts, this code raises raw structural exceptions such as:
- `TypeError: string indices must be integers`
- `TypeError: 'int' object is not subscriptable`

Those are not normalized to `AuditIntegrityError`.

That matters because resume recovery only translates these categories:

```python
except AuditIntegrityError as e:
    ...
except (ValueError, KeyError) as e:
    ...
```

Source: `/home/john/elspeth/src/elspeth/core/checkpoint/recovery.py:516-532`

So malformed contract JSON can escape as an uncaught `TypeError` instead of the intended corruption error path, even though the surrounding code explicitly treats malformed stored contract JSON as Tier-1 corruption.

The restore entrypoint that triggers this is:

```python
audit_record = ContractAuditRecord.from_json(schema_contract_json)
contract = audit_record.to_schema_contract()
```

Source: `/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py:444-446`

## Root Cause Hypothesis

The implementation validates selected field values but not the JSON container shape before indexing into it. That leaves malformed-but-JSON-valid payloads outside the module’s declared error contract, so callers that expect `AuditIntegrityError`/`KeyError`/`ValueError` receive a raw `TypeError` instead.

## Suggested Fix

Harden `from_json()` to validate payload structure before field access:
- top-level decoded value must be `dict`
- `fields` must be a list
- each element of `fields` must be a dict

Convert structural mismatches into `AuditIntegrityError` with clear context, for example:
- “Contract audit record must be an object”
- “Contract audit record 'fields' must be a list”
- “Contract audit record field entry at index 0 must be an object”

## Impact

The system still fails closed, but it fails with the wrong exception class and loses the intended audit-corruption context:
- resume may crash with a raw `TypeError` instead of `CheckpointCorruptionError`
- operators get a less actionable error than the surrounding recovery code was designed to provide
- Tier-1 corruption handling becomes inconsistent across different malformed payload shapes
