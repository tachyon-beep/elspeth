## Summary

`JSONExplode` infers `output_field` type from only the first exploded row, so heterogeneous arrays can produce rows whose values violate the emitted contract.

## Severity

- Severity: minor
- Priority: P2
- Triaged: downgraded from P1 — contract metadata inaccuracy for uncommon heterogeneous arrays, not data loss

## Location

- File: /home/john/elspeth-rapid/src/elspeth/plugins/transforms/json_explode.py
- Line(s): 186-202, 203-217
- Function/Method: `JSONExplode.process`

## Evidence

The transform validates only key-shape homogeneity:

```python
first_keys = set(output_rows[0].keys())
...
if row_keys != first_keys: raise ValueError(...)
```

Then it builds contract from `output_rows[0]` only:

```python
output_contract = narrow_contract_to_output(
    input_contract=row.contract,
    output_row=output_rows[0],
)
```

So for `items=["a", {"k": 1}]`, contract for `item` becomes `str` (from first row), but second row has `dict`. Runtime repro confirmed: second row `item` was dict while contract still reported `str`.

## Root Cause Hypothesis

Contract inference for multi-row deaggregation is single-sample-based (first row), and key-only validation does not detect value-type heterogeneity across rows.

## Suggested Fix

Set exploded `output_field` contract to `object` (or compute a union across all items and downgrade to `object` when mixed). For example, after contract creation, replace `output_field` with `python_type=object` regardless of first-row inferred type.

Add a test with mixed-type arrays (e.g., `["a", {"k": 1}]`) and assert the resulting contract type for `output_field` is `object`.

## Impact

- Schema contract can be wrong even when transform returns success.
- Downstream behavior becomes nondeterministic: components relying on contract type can fail unexpectedly.
- Audit/schema lineage becomes inaccurate for deaggregated child tokens.
