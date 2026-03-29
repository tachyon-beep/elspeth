## Summary

`create_schema_from_config()` fails to reject `NaN`/`Infinity` inside NumPy arrays at the source boundary, so rows that should be quarantined are accepted as valid and later crash audit hashing.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/plugins/infrastructure/schema_factory.py
- Line(s): 43-67, 70-85
- Function/Method: `_find_non_finite_value_path`, `_reject_non_finite_observed_values`

## Evidence

`schema_factory.py` is intended to stop non-finite values before they reach the pipeline:

```python
43 def _find_non_finite_value_path(value: Any, path: str = "$") -> str | None:
47     if value_type is float and not math.isfinite(value):
50     if value_type is dict:
57     if value_type in {list, tuple}:
64     if isinstance(value, np.floating) and not math.isfinite(float(value)):
```

But this walker only descends into exact `dict`/`list`/`tuple` containers and only checks NumPy **scalar** floats. It never inspects `np.ndarray`, so a source row like `{"data": np.array([1.0, np.nan])}` passes validation.

Verified directly against the target module:

- `/home/john/elspeth/src/elspeth/plugins/infrastructure/schema_factory.py:78-85` installs the validator for observed/source schemas.
- Runtime check with repo code:
  - `create_schema_from_config(SchemaConfig.from_dict({"mode": "fixed", "fields": ["data: any"]}), ..., allow_coercion=True).model_validate({"data": np.array([1.0, np.nan])})`
  - Result: validation succeeds, returning `{'data': array([1., nan])}`
  - Same for observed mode and flexible-mode extras.

That accepted row then reaches the normal valid-row audit path:

- `/home/john/elspeth/src/elspeth/engine/processor.py:1188-1200` records valid source rows with `begin_node_state(..., input_data=source_input)` and `complete_node_state(..., output_data=source_input)`.
- `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:156-168` hashes non-quarantined input with `stable_hash(input_data)` and has no fallback.

Canonical hashing rejects exactly this payload shape:

- `/home/john/elspeth/src/elspeth/core/canonical.py:76-93` explicitly checks `np.ndarray` for `np.isnan`/`np.isinf` and raises.
- Verified with repo code:
  - `stable_hash({"data": np.array([1.0, np.nan])})`
  - Result: `ValueError: NaN/Infinity found in NumPy array...`

So the target file is letting invalid Tier-3 data through, and the run dies later in Tier-1 audit recording instead of quarantining the row at ingestion.

## Root Cause Hypothesis

The non-finite scan in `schema_factory.py` was written for Python floats, nested built-in containers, and NumPy floating scalars, but not NumPy array containers. That leaves a gap between source validation and canonical JSON enforcement: `schema_factory` treats `np.ndarray` as opaque, while `canonical.py` treats it as a structured value and correctly rejects non-finite members.

## Suggested Fix

Teach `_find_non_finite_value_path()` to inspect NumPy arrays, including nested/object arrays, and report a useful path.

Possible direction:

```python
if isinstance(value, np.ndarray):
    if value.ndim == 0:
        return _find_non_finite_value_path(value.item(), path)
    for idx, nested in enumerate(value.tolist()):
        nested_path = _find_non_finite_value_path(nested, f"{path}[{idx}]")
        if nested_path is not None:
            return nested_path
    return None
```

If performance matters for numeric arrays, a fast-path using `np.isnan`/`np.isinf` before fallback recursion would also work. Add regression tests in `/home/john/elspeth/tests/unit/plugins/test_schema_factory.py` for:

- explicit `any` field with `np.array([1.0, np.nan])`
- observed schema with `np.array([1.0, np.inf])`
- flexible extra field containing a non-finite array

## Impact

Rows from source plugins can be misclassified as valid even though they contain data that cannot be canonically hashed. Instead of being quarantined at the Tier-3 boundary, they crash the pipeline during audit recording. That violates the trust model and turns a row-level validation failure into a run-level failure, with source validation/audit behavior no longer matching the intended “quarantine bad external data, continue processing” contract.
