## Summary

`ContractBuilder.process_first_row()` crashes on first-row `dict`/`list` values (common in JSON observed/flexible sources) instead of inferring `object`, causing pipeline aborts at the source boundary.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/contract_builder.py`
- Line(s): `94`
- Function/Method: `ContractBuilder.process_first_row`

## Evidence

`process_first_row()` always calls:

```python
updated = updated.with_field(normalized_name, original_name, value)
```

at `/home/john/elspeth-rapid/src/elspeth/contracts/contract_builder.py:94`.

`with_field()` infers type via `normalize_type_for_contract(value)` (`src/elspeth/contracts/schema_contract.py:218`), and `normalize_type_for_contract()` raises `TypeError` for non-primitive types like `dict`/`list` (`src/elspeth/contracts/type_normalization.py:94`).

Callers do not catch this exception path:
- `src/elspeth/plugins/sources/json_source.py:345-350`, only catches `ValidationError` at `:375`
- `src/elspeth/plugins/sources/csv_source.py:281-287`, only catches `ValidationError` at `:315`
- `src/elspeth/plugins/azure/blob_source.py:731-741`, only catches `ValidationError` at `:766`

So the exception escapes and aborts load.

Direct repro (in-memory) produced:
`TypeError Unsupported type 'dict' for schema contract...`

This is inconsistent with expected observed behavior:
- Observed schema accepts nested objects (`tests/unit/plugins/test_schema_factory.py:23-33`)
- Contract inference elsewhere already maps `dict`/`list` to `object` (`src/elspeth/contracts/contract_propagation.py:53-58`, validated by tests at `tests/unit/contracts/test_contract_propagation.py:457-504`).

## Root Cause Hypothesis

`ContractBuilder` still uses strict primitive-only inference for first-row source contracts, but newer contract propagation logic added explicit `dict`/`list` -> `object` handling. The source-side first-row inference path was not updated accordingly, so it now crashes on valid JSON-shaped fields.

## Suggested Fix

In `process_first_row()`, handle `dict`/`list` values explicitly before/around `with_field()` and infer them as `object` (same policy as `contract_propagation.py`), while preserving current failure behavior for other unsupported types.

Example approach in target file:

```python
value_for_inference = object() if type(value) in (dict, list) else value
updated = updated.with_field(normalized_name, original_name, value_for_inference)
```

Also add unit coverage in `tests/unit/contracts/test_contract_builder.py` for first-row dict/list inference to `object` without crashing.

## Also Affects

`SchemaContract.with_field()` has the same root cause — it calls `normalize_type_for_contract(value)` without handling dict/list fallback. This was previously tracked as a separate bug (`schema-contract-with-field-crashes-on-nested-json-values`) but is the same fix location and same root cause. Merged during triage 2026-02-14.

## Impact

- JSON observed/flexible sources can crash on common payload shapes (`{"payload": {...}}`, arrays, usage blobs).
- External Tier-3 data path violates "quarantine/continue" behavior by aborting instead.
- Affected rows are not emitted as quarantined results, reducing audit completeness and disrupting run continuity.
