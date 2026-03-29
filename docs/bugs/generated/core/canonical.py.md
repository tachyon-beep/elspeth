## Summary

Finite `np.longdouble` values are mishandled in `_normalize_value()`: the code uses `math.isnan()/math.isinf()` and `float()` on `np.floating`, which can falsely treat valid high-range values as non-finite and can collapse distinct high-precision values onto the same canonical hash.

## Severity

- Severity: major
- Priority: P1

## Location

- File: /home/john/elspeth/src/elspeth/core/canonical.py
- Line(s): 59-65
- Function/Method: `_normalize_value`

## Evidence

`_normalize_value()` handles all NumPy floating scalars in one branch:

```python
if isinstance(obj, float | np.floating):
    if math.isnan(obj) or math.isinf(obj):
        raise ValueError(...)
    if isinstance(obj, np.floating):
        return float(obj)
```

Source: `/home/john/elspeth/src/elspeth/core/canonical.py:59-65`

That is unsafe for `np.longdouble`:

1. False rejection of finite values.
   Local verification:

```python
v = np.longdouble('1e4900')
np.isfinite(v) == True
math.isinf(v) == True
```

and:

```python
canonical_json({'x': np.longdouble('1e4900')})
# ValueError: Cannot canonicalize non-finite float: inf...
```

So a finite value is rejected as if it were Infinity.

2. Hash collisions for distinct finite values.
   Local verification:

```python
v1 = np.longdouble(1) + np.finfo(np.longdouble).eps
v2 = np.longdouble(1) + np.finfo(np.longdouble).eps * 2
v1 != v2                           # True
float(v1) == float(v2)             # True
stable_hash({'x': v1}) == stable_hash({'x': v2})  # True
```

Because both values are coerced to Python `float`, canonicalization loses the extra precision before hashing.

This matters in real integration paths, not just unit calls. `stable_hash()` / `canonical_json()` are used on audit and payload paths, for example:

- `/home/john/elspeth/src/elspeth/core/landscape/execution_repository.py:167`
- `/home/john/elspeth/src/elspeth/core/landscape/run_lifecycle_repository.py:87-88`
- `/home/john/elspeth/src/elspeth/plugins/transforms/llm/templates.py:203-211`
- `/home/john/elspeth/src/elspeth/plugins/sinks/dataverse.py:343-346`
- `/home/john/elspeth/src/elspeth/plugins/sinks/database_sink.py:464-471`

Existing tests only cover small finite `np.longdouble` values, not high-range or precision-sensitive cases:
- `/home/john/elspeth/tests/unit/core/test_canonical.py:536-541`

## Root Cause Hypothesis

The implementation assumes all `np.floating` values are safely representable as Python `float`. That is false for `np.longdouble` on this platform: both the non-finite check and the normalization step implicitly downcast through Python `float`, which changes value semantics before canonicalization.

## Suggested Fix

Handle NumPy floating scalars without lossy Python-float coercion during validation.

Suggested direction:
- Use NumPy-native finiteness checks for `np.floating` values, not `math.isnan()/math.isinf()`.
- Either reject precision/range that cannot be represented canonically without loss, or serialize via an exact representation strategy. Do not silently cast distinct `np.longdouble` values to the same Python `float`.

Example shape:

```python
if isinstance(obj, np.floating):
    if not np.isfinite(obj):
        raise ValueError(...)
    py = float(obj)
    if np.longdouble(py) != obj:
        raise ValueError("Cannot canonicalize np.longdouble without precision loss")
    return py
```

Also add regression tests for:
- finite `np.longdouble('1e4900')`
- two distinct `np.longdouble` values that round to the same Python `float`

## Impact

Canonical hashing is no longer faithful for all supported NumPy floating inputs:
- valid data can be rejected as “non-finite”
- distinct values can produce identical hashes

That weakens audit integrity and any downstream content-hash logic that relies on `canonical.py` for exact value identity.
---
## Summary

`sanitize_for_canonical()` silently rewrites finite large `np.longdouble` values to `None`, so quarantined rows can lose real source data before source node-state recording.

## Severity

- Severity: minor
- Priority: P2

## Location

- File: /home/john/elspeth/src/elspeth/core/canonical.py
- Line(s): 280-282
- Function/Method: `sanitize_for_canonical`

## Evidence

The sanitizer treats NumPy floating scalars as non-finite based on `float(obj)`:

```python
if isinstance(obj, np.floating) and not math.isfinite(float(obj)):
    return None
```

Source: `/home/john/elspeth/src/elspeth/core/canonical.py:280-282`

For a finite high-range `np.longdouble`:

```python
v = np.longdouble('1e4900')
np.isfinite(v) == True
sanitize_for_canonical({'x': v}) == {'x': None}
```

So the function erases a valid value.

This is a live audit path. Quarantined rows are sanitized here:

- `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1805-1810`

and then recorded as source node-state input data here:

- `/home/john/elspeth/src/elspeth/engine/orchestrator/core.py:1823-1833`

That means the token’s source-state record can contain `None` instead of the actual quarantined field value.

## Root Cause Hypothesis

The sanitizer reuses Python-float finiteness as a proxy for NumPy scalar finiteness. For `np.longdouble`, converting to Python `float` can overflow even when the original value is finite, so the sanitizer mistakes “not representable as float” for “non-finite”.

## Suggested Fix

Use NumPy-native finiteness checks on `np.floating` values and only sanitize truly non-finite values.

Example shape:

```python
if isinstance(obj, np.floating):
    if not np.isfinite(obj):
        return None
    return obj
```

Add a regression test showing that `sanitize_for_canonical({"x": np.longdouble("1e4900")})` preserves the value instead of replacing it.

## Impact

A quarantined row can lose truthful source payload data in the node-state record even though the original value was valid. That degrades audit fidelity for quarantine lineage and can make later explanation show a synthetic `None` that the source never provided.
