## Summary

`ContractBuilder.process_first_row()` freezes inferred fields to `NoneType` when the first valid row contains `None`/`pd.NA`, so later rows with real values for that field are wrongly treated as contract violations and can be quarantined or discarded.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/contract_builder.py`
- Line(s): 91-103
- Function/Method: `ContractBuilder.process_first_row`

## Evidence

`process_first_row()` infers every undeclared field directly from the first row value:

```python
for normalized_name, value in row.items():
    ...
    try:
        updated = updated.with_field(normalized_name, original_name, value)
    except TypeError:
        updated = updated.with_field(normalized_name, original_name, object())
```

`with_field()` delegates to `normalize_type_for_contract(value)`:

- `/home/john/elspeth/src/elspeth/contracts/schema_contract.py:215-221`
- `/home/john/elspeth/src/elspeth/contracts/type_normalization.py:54-55, 67-73`

That normalization explicitly maps missing sentinels to `type(None)`:

- `None -> type(None)` at `/home/john/elspeth/src/elspeth/contracts/type_normalization.py:54-55`
- `pd.NA -> type(None)` at `/home/john/elspeth/src/elspeth/contracts/type_normalization.py:67-69`
- `pd.NaT -> type(None)` at `/home/john/elspeth/src/elspeth/contracts/type_normalization.py:71-73`

So a first row like `{"comment": None}` locks the inferred contract field as `NoneType`.

After locking, source plugins validate subsequent rows against that contract:

- JSON source: `/home/john/elspeth/src/elspeth/plugins/sources/json_source.py:378-406`
- CSV source: `/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py:422-451`
- Azure Blob source: `/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py:784-817`

`SchemaContract.validate()` compares later values against the frozen type and raises a mismatch for non-`None` values:

- type check logic: `/home/john/elspeth/src/elspeth/contracts/schema_contract.py:257-275`

The existing unit test suite codifies the problematic inference but never checks the later-row behavior:

- `test_infer_none_type`: `/home/john/elspeth/tests/unit/contracts/test_contract_builder.py:125-139`
- `test_infer_pandas_na_type`: `/home/john/elspeth/tests/unit/contracts/test_contract_builder.py:140-153`

What the code does:
- Treats first-row absence as a concrete schema type (`NoneType`).

What it should do:
- Treat first-row absence in inferred fields as “type not yet known”, so later non-null values are not falsely rejected.

## Root Cause Hypothesis

The builder conflates “missing/absent value observed on the first row” with “the field’s actual runtime type is `NoneType`”. In ELSPETH’s trust model, absence is evidence about that row, but it is not enough evidence to freeze the field’s type for all later rows. Because the contract is locked after the first valid row, this mistaken inference becomes permanent and turns sparse external data into false validation failures.

## Suggested Fix

Special-case null-like first-row values in `ContractBuilder.process_first_row()` before calling `with_field()`. For inferred fields, if the sampled value normalizes to `type(None)`, record the field as `object` instead of `NoneType` so the contract preserves the field without falsely constraining later rows.

Helpful shape:

```python
inferred_type = normalize_type_for_contract(value)
if inferred_type is type(None):
    updated = updated.with_field(normalized_name, original_name, object())
else:
    updated = updated.with_field(normalized_name, original_name, value)
```

or equivalent logic inside `SchemaContract.with_field()` for inferred additions.

Add an integration test covering:
1. First valid row has `None`/`pd.NA` for an extra field.
2. Second valid row has a real value for that field.
3. The second row is accepted, not quarantined/discarded.

## Impact

Valid source rows can be wrongly quarantined or dropped in `OBSERVED`/`FLEXIBLE` schemas when the first row is sparse. This affects first-row contract locking in at least JSON, CSV, and Azure Blob sources. The audit trail records a validation failure, but it is a false failure caused by the builder, so downstream behavior and row counts become incorrect. In `discard` mode this becomes silent data loss from the operator’s perspective: legitimate rows never reach the pipeline because the contract was frozen from an absence signal rather than real type evidence.
