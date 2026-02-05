# Analysis: src/elspeth/contracts/type_normalization.py

**Lines:** 89
**Role:** Converts runtime values (including numpy/pandas types) to canonical Python primitive types for consistent schema contract storage. Enforces audit integrity by rejecting NaN/Infinity and unsupported types. Acts as the bridge between dynamic runtime values and the static type system in schema contracts.
**Key dependencies:**
- Imports: `math`, `datetime` (stdlib); `numpy`, `pandas` (lazy imports inside function)
- Imported by: `schema_contract.py` (for `with_field()` and `validate()` type checking), `contract_propagation.py` (for inferring new field types), `contracts/__init__.py`
**Analysis depth:** FULL

## Summary

This file is well-designed with correct lazy imports, proper NaN/Infinity rejection, and a clear fail-fast approach for unsupported types. The main finding is a divergence between `ALLOWED_CONTRACT_TYPES` in this file and `VALID_FIELD_TYPES` in `schema_contract.py` -- specifically, `object` is in `VALID_FIELD_TYPES` but not in `ALLOWED_CONTRACT_TYPES`. This is intentional (you cannot infer `object` from a runtime value), but the relationship is undocumented and could confuse future maintainers. One warning about the `bool` subclass of `int` ordering safety, which is actually handled correctly but deserves documentation.

## Critical Findings

None.

## Warnings

### [22-31 vs schema_contract.py:31-41] ALLOWED_CONTRACT_TYPES diverges from VALID_FIELD_TYPES -- missing `object`

**What:** This file defines:
```python
ALLOWED_CONTRACT_TYPES: frozenset[type] = frozenset({
    int, str, float, bool, type(None), datetime,
})
```

While `schema_contract.py` defines:
```python
VALID_FIELD_TYPES: frozenset[type] = frozenset({
    int, str, float, bool, type(None), datetime, object,
})
```

The `object` type (representing "any" in the contract system) is present in `VALID_FIELD_TYPES` but absent from `ALLOWED_CONTRACT_TYPES`.

**Why it matters:** This is actually semantically correct: you can declare a field as `object` type (via `_get_python_type` in `transform_contract.py` or directly in `FieldContract`), but you cannot *infer* `object` from a runtime value (what would a runtime "any" value even look like?). However:

1. The two sets have a `Must match` comment (`type_normalization.py` line 21: "Must match type_map in SchemaContract.from_checkpoint()") that suggests they SHOULD be identical, but they are not.
2. There is no cross-reference or documentation explaining why the intentional difference exists.
3. A future maintainer adding a type to one set but not the other could introduce bugs.
4. The comment on line 21 is misleading -- `ALLOWED_CONTRACT_TYPES` does NOT need to match the `type_map` in `from_checkpoint()` because `from_checkpoint()` also includes `object`.

**Evidence:**
```python
# type_normalization.py line 20-21
# Types that can be serialized in checkpoint and restored in from_checkpoint()
# Must match type_map in SchemaContract.from_checkpoint()
ALLOWED_CONTRACT_TYPES: frozenset[type] = frozenset({...})  # No 'object'
```

```python
# schema_contract.py line 357-365 (from_checkpoint type_map)
type_map: dict[str, type] = {
    "int": int, "str": str, "float": float, "bool": bool,
    "NoneType": type(None), "datetime": datetime,
    "object": object,  # present here!
}
```

The "Must match" claim is factually wrong -- `ALLOWED_CONTRACT_TYPES` does NOT match `from_checkpoint()`'s `type_map` because `object` is missing.

### [50-51] Unconditional numpy/pandas import inside function body

**What:** Lines 50-51 always import `numpy` and `pandas` inside `normalize_type_for_contract()`. The comment (line 15-18) explains this is intentional for lazy loading. However, every single call to this function pays the import lookup cost, even for plain Python values like `int` or `str`.

**Why it matters:** Performance concern for hot paths. This function is called per-field during:
- Source row processing (`schema_contract.py:with_field()` for OBSERVED/FLEXIBLE modes)
- Contract validation (`schema_contract.py:validate()` for every field of every row)
- Contract propagation (`contract_propagation.py` for inferring new fields)

While Python caches imports after the first call (so it is just a dict lookup after the first import), the import machinery still has overhead per call. For pipelines processing millions of rows, this adds up. The function could check for Python primitive types FIRST (before the lazy import) and return early, only importing numpy/pandas when the value is not a primitive.

**Evidence:**
```python
def normalize_type_for_contract(value: Any) -> type:
    import numpy as np    # Always imported
    import pandas as pd   # Always imported

    if value is None:     # Could have returned type(None) before importing
        return type(None)
```

The `None` check at line 54 is after the imports. For the common case of Python primitive values, the numpy/pandas imports are unnecessary.

## Observations

### [66-78] Numpy type checking order is correct for the bool/int subclass relationship

**What:** In numpy, `np.bool_` inherits from `np.generic`, NOT from `np.integer`. The code checks `np.integer` before `np.bool_` (lines 67 vs 71), which could be problematic if `np.bool_` were a subclass of `np.integer` -- but it is not. The order is safe.

**Why it matters:** This is a common concern when reviewing numpy type normalization code because in native Python, `bool` IS a subclass of `int`. However, numpy's hierarchy is different: `np.bool_` is NOT a subclass of `np.integer`. The code is correct. A comment explaining this would help future reviewers avoid the same concern.

### [82-83] Final type check uses `type(value)` not `isinstance()`

**What:** The final fallback at line 82 uses `type(value)` for the allowed-type check, not `isinstance()`. This means `bool` values are correctly identified as `bool` (since `type(True)` is `bool`, not `int`), while `isinstance(True, int)` would return `True`.

**Why it matters:** This is correct and important. Using `isinstance` here would misclassify `True` as `int`. Using `type()` gives the exact type. This is a deliberate and correct design choice.

### [63] NaN check uses `math.isnan` and `math.isinf` which work on both float and np.floating

**What:** The NaN/Infinity check at line 63 uses `math.isnan()` and `math.isinf()`, which work correctly on both Python `float` and `numpy.floating` types.

**Why it matters:** Confirms correctness. The `isinstance(value, (float, np.floating))` guard ensures these functions are only called on numeric types where they are valid.

### [80-88] Fail-fast error message includes helpful guidance

**What:** The `TypeError` message on lines 85-87 lists all allowed types and suggests using "any" type for complex fields. This is excellent error UX.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Fix the misleading "Must match type_map" comment on line 20-21 to accurately describe the relationship with `VALID_FIELD_TYPES` and explain why `object` is intentionally excluded. (2) Consider reordering the function to check Python primitive types before the lazy numpy/pandas imports for performance on the common path. (3) Add a comment explaining why `type(value)` is used instead of `isinstance()` at line 82.
**Confidence:** HIGH -- the code is correct in its current form. The findings are about documentation accuracy, performance optimization, and maintainability, not correctness bugs.
