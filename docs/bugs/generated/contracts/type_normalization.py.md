## Summary

`normalize_type_for_contract()` is used on live row values during `SchemaContract.validate()`, but it raises `TypeError`/`ValueError` for unsupported or non-finite values instead of returning a comparable runtime type. That turns a quarantinable Tier 3 row problem into a source plugin crash.

## Severity

- Severity: major
- Priority: P1

## Location

- File: `/home/john/elspeth/src/elspeth/contracts/type_normalization.py`
- Line(s): 75-78, 99-103
- Function/Method: `normalize_type_for_contract`

## Evidence

`normalize_type_for_contract()` hard-fails on values that are not in the contract type allowlist:

```python
# /home/john/elspeth/src/elspeth/contracts/type_normalization.py:77-78
if isinstance(value, (float, np.floating)) and (math.isnan(value) or math.isinf(value)):
    raise ValueError(...)
```

```python
# /home/john/elspeth/src/elspeth/contracts/type_normalization.py:101-106
final_type = type(value)
if final_type not in ALLOWED_CONTRACT_TYPES:
    raise TypeError(...)
```

But `SchemaContract.validate()` calls that helper directly while validating row data and does not catch either exception:

```python
# /home/john/elspeth/src/elspeth/contracts/schema_contract.py:271-275
actual_type = normalize_type_for_contract(value)
if actual_type != fc.python_type:
    violations.append(...)
```

The source plugins then assume `contract.validate()` only returns violations; they only catch `pydantic.ValidationError`, not `TypeError`/`ValueError` from contract validation:

```python
# /home/john/elspeth/src/elspeth/plugins/sources/json_source.py:389-409
violations = contract.validate(validated_row)
...
except ValidationError as e:
```

Same pattern exists in:
- `/home/john/elspeth/src/elspeth/plugins/sources/csv_source.py:434-457`
- `/home/john/elspeth/src/elspeth/plugins/sources/azure_blob_source.py:800-820`

I reproduced the crash directly:

```python
contract = SchemaContract(
    mode="FIXED",
    fields=(make_field("duration", int, original_name="Duration", required=True, source="declared"),),
    locked=True,
)
contract.validate({"duration": pd.Timedelta("1 days")})
# => TypeError: Unsupported type 'Timedelta' for schema contract...
```

That behavior violates the source trust-boundary expectation captured in `/home/john/elspeth/tests/integration/plugins/sources/test_trust_boundary.py:295-299`, which states malformed external rows must be quarantined, not crash the run.

## Root Cause Hypothesis

This helper is doing two incompatible jobs with one API:

- Contract inference/checkpoint compatibility wants strict failure on unsupported types.
- Runtime row validation wants a normalized runtime type so it can emit `TypeMismatchViolation` and quarantine the row.

Because `normalize_type_for_contract()` always raises on unsupported/non-finite values, validation inherits inference-time crash semantics.

## Suggested Fix

Split the semantics in this module so validation does not use the strict inference path.

For example:
- Keep a strict helper for inference/build-time checks that may raise.
- Add a validation-oriented helper that normalizes numpy/pandas wrappers but otherwise returns `type(value)` (or another non-throwing classification) so callers can produce `TypeMismatchViolation` instead of crashing.

Then update `SchemaContract.validate()` to use the non-throwing path.

This keeps contract construction strict while letting source validation quarantine bad rows.

## Impact

A single later-row value such as `pandas.Timedelta`, `numpy.complex128`, or a non-finite float can abort source processing instead of being recorded as a validation failure. That means:

- Tier 3 bad data crashes the run instead of being quarantined
- `record_validation_error()` is skipped
- the bad row may never reach a terminal quarantine state
- auditability is weakened because the failure is not captured as a normal validation outcome
