## Summary

`explain_field()` can return the wrong field when a lookup key matches one field's `original_name` and a different field's `normalized_name`, causing silent provenance misattribution.

## Severity

- Severity: minor
- Priority: P3 (downgraded from P1 — requires a field whose original_name equals another field's normalized_name; extremely niche scenario in practice; plugin name provides disambiguation; read-only diagnostic tool)

## Location

- File: `src/elspeth/mcp/analyzers/contracts.py`
- Line(s): 95-100
- Function/Method: `explain_field`

## Evidence

`explain_field()` does a linear scan with an `or` match:

```python
for f in contract.fields:
    if f.normalized_name == field_name or f.original_name == field_name:
        field_contract = f
        break
```

Because this is first-match-wins, results depend on field order, not identity rules.

In contrast, contract lookup logic already defines deterministic precedence (`normalized_name` first) in `SchemaContract.find_name()`:

- `src/elspeth/contracts/schema_contract.py:136-140`

I reproduced this with an in-memory contract:

- Field 1: `normalized_name='a'`, `original_name='x'`
- Field 2: `normalized_name='x'`, `original_name='y'`

Calling `explain_field(..., field_name='x')` returned Field 1 (`normalized_name='a'`) instead of Field 2 (`normalized_name='x'`), i.e. wrong field provenance.

This overlap is feasible from source mapping behavior (original->final mappings can produce names overlapping other originals), e.g. `{'x': 'a', 'y': 'x'}` is accepted by `resolve_field_names()` (`src/elspeth/plugins/sources/field_normalization.py:256-277`).

## Root Cause Hypothesis

`explain_field()` re-implements contract name resolution ad hoc instead of using the canonical resolver (`find_name`/`get_field`), so it loses deterministic precedence and becomes order-dependent.

## Suggested Fix

Replace manual scan with contract-native resolution:

1. `normalized = contract.find_name(field_name)`
2. If `None`, return not-found payload.
3. Else `field_contract = contract.get_field(normalized)`

This centralizes semantics and removes order-dependent ambiguity.

## Impact

Audit/provenance answers from MCP can be incorrect for valid contracts, violating explainability guarantees by attributing metadata to the wrong field without error.
