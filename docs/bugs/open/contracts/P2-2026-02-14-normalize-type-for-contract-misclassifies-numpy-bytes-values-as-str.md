## Summary

`normalize_type_for_contract()` misclassifies `numpy.bytes_` values as `str`, which can silently pass schema validation for string fields even when runtime values are actually bytes.

## Severity

- Severity: minor
- Priority: P2 (downgraded from P1 — narrow practical impact, uncommon for sources to produce np.bytes_ values)

## Location

- File: `/home/john/elspeth-rapid/src/elspeth/contracts/type_normalization.py`
- Line(s): `88-89`
- Function/Method: `normalize_type_for_contract`

## Evidence

`type_normalization.py` currently maps both `np.str_` and `np.bytes_` to `str`:

```python
if isinstance(value, (np.str_, np.bytes_)):
    return str
```

Source: `/home/john/elspeth-rapid/src/elspeth/contracts/type_normalization.py:88`

Schema validation trusts this normalized type comparison:

```python
actual_type = normalize_type_for_contract(value)
if actual_type != fc.python_type:
    violations.append(TypeMismatchViolation(...))
```

Source: `/home/john/elspeth-rapid/src/elspeth/contracts/schema_contract.py:271`

So a field declared as `str` can wrongly pass with `np.bytes_` payloads because `actual_type` is forced to `str`.

Local reproduction (executed in repo environment) showed:
- `type(np.bytes_(b"abc"))` is `numpy.bytes_`
- `isinstance(np.bytes_(b"abc"), str)` is `False`
- `SchemaContract(... python_type=str ...).validate({"name": np.bytes_(b"abc")})` returns `[]` (no violation)

There is also a test that currently locks this incorrect behavior in place:
- `/home/john/elspeth-rapid/tests/unit/contracts/test_type_normalization.py:241-245` (`test_numpy_bytes_returns_str`)

## Root Cause Hypothesis

`np.bytes_` was grouped with `np.str_` as "string-like" during normalization, but only `np.str_` is text-compatible with `str` semantics. This introduces type coercion at contract-validation time and hides real type mismatches.

## Suggested Fix

In `/home/john/elspeth-rapid/src/elspeth/contracts/type_normalization.py`, split handling:
- Keep `np.str_ -> str`
- Stop mapping `np.bytes_ -> str` (treat as non-`str`, e.g., unsupported or explicit non-text type path)

Example direction:

```python
if isinstance(value, np.str_):
    return str
# do not coerce np.bytes_ to str
```

Also update tests:
- Replace `/home/john/elspeth-rapid/tests/unit/contracts/test_type_normalization.py:241-245`
- Add a validation test ensuring `str` contract does not accept `np.bytes_` silently.

## Impact

- Contract/type guarantees are weakened for text fields.
- Bad data can bypass quarantine/violation pathways in source validation flows that depend on contract checks (`csv_source`, `json_source`, `blob_source`), because "bytes presented as string" is treated as valid.
- Violates the project's no-coercion contract semantics for Tier 2+ internal flows and can create misleading audit records about actual runtime value types.
