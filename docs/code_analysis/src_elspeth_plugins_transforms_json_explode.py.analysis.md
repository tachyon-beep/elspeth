# Analysis: src/elspeth/plugins/transforms/json_explode.py

**Lines:** 220
**Role:** Deaggregation transform that explodes a single row containing a JSON array field into multiple rows, one per array element. Sets `creates_tokens=True` to signal the engine to create new token IDs for each output row with parent linkage. This is the inverse of aggregation (1-to-N expansion).
**Key dependencies:** BaseTransform, DataPluginConfig (NOT TransformDataConfig), SchemaConfig, PipelineRow, TransformResult, create_schema_from_config, contract_propagation.narrow_contract_to_output
**Analysis depth:** FULL

## Summary

JSONExplode is well-designed with explicit trust model documentation. It correctly inherits from `DataPluginConfig` (not `TransformDataConfig`) since it has no error routing. The schema homogeneity validation (line 188-197) is a strong defense-in-depth measure. The main concern is a shallow copy issue identical to the one in batch_replicate, plus a subtle data integrity issue where array elements that are mutable dicts share references across exploded rows.

## Critical Findings

### [146-177] Shallow copy of base dict + shared array element references create cross-row mutation risk

**What:** The base dict is created via dict comprehension (shallow copy) at line 146, then each output row is created via `base.copy()` (also shallow) at line 177. Array elements are assigned by reference at line 178.

**Why it matters:** Two separate mutation vectors exist:

1. **Shared nested values in base fields:** If the original row has `{"id": 1, "metadata": {"src": "csv"}, "items": [...]}`, the `metadata` dict is shared across all output rows. A downstream transform modifying `output_rows[0]["metadata"]["processed"] = True` will affect all other output rows.

2. **Array elements are references, not copies:** If the array contains dicts (the common case per the docstring example `[{"name": "a"}, {"name": "b"}]`), each output row's `item` field points to the SAME dict object that is in the original array. The array value was extracted from the PipelineRow via `row[self._array_field]`, which returns the value from a `MappingProxyType` -- but `MappingProxyType` only prevents top-level mutation, the nested list and its dict elements are still mutable references.

**Evidence:**
```python
base = {k: v for k, v in row_dict.items() if k != self._array_field}
# ...
output = base.copy()              # Shallow copy of base
output[self._output_field] = item  # Reference to original array element
```

For the intended use case (JSON arrays of dicts), a downstream transform that does `row["item"]["category"] = "processed"` on the first exploded row would corrupt the audit trail representation of subsequent rows.

## Warnings

### [148-172] Empty array returns single row with None values -- breaks deaggregation contract

**What:** When the array field is empty (`[]`), the transform returns a single row with `output_field=None` and `item_index=None` via `TransformResult.success()` (single-row, not multi).

**Why it matters:** This is a semantic edge case with several implications:

1. The single-row return means the engine does NOT create new tokens (success vs success_multi). The original token continues with a row that has `item=None`. Downstream transforms expecting a real item will get None.

2. The `creates_tokens=True` flag is only relevant for multi-row returns. For the empty array case, the original token survives but with a modified row shape (array_field removed, output_field/item_index added with None). This is a valid design choice but worth documenting.

3. A downstream gate checking `row["item"]["name"]` will crash with `TypeError: 'NoneType' object is not subscriptable`. This is technically correct per trust model (the gate should handle this), but it is a common footgun.

### [200-206] Import of `cast` inside process() method

**What:** `from typing import cast` is imported inside the process method at line 201.

**Why it matters:** This is a minor style issue. The import is only needed for the `cast()` call at line 205. While Python caches imports, placing it inside a hot path adds a small overhead on every call. More importantly, it signals that the type annotation `list[dict[str, Any] | PipelineRow]` for `output_rows` is slightly too broad -- the list only ever contains dicts, not PipelineRows. The cast is needed because `narrow_contract_to_output` expects `dict[str, Any]` but `output_rows[0]` has the union type.

### [36] Inherits from DataPluginConfig, not TransformDataConfig -- no on_error available

**What:** JSONExplode uses `DataPluginConfig` as documented in the module docstring, meaning there is no `on_error` configuration.

**Why it matters:** This is an intentional design decision: the transform has no value-level operations that can fail (the only failures are type/key violations which are upstream bugs). However, this means there is literally no error recovery path for this transform. If the array_field contains a list but with unexpected element types, the crash will propagate. This is correct per the trust model but worth noting for operators configuring pipelines.

## Observations

### [188-197] Schema homogeneity validation is excellent defense-in-depth

The explicit check that all output rows have the same key set before building the contract is a strong practice. This catches cases where array elements have heterogeneous structures (e.g., `[{"a": 1}, {"a": 1, "b": 2}]`) which would cause the contract to lie about the output shape. The `ValueError` raised here is correct -- heterogeneous output is a data quality issue that should crash the transform.

### [85] creates_tokens = True is correctly set

This is the critical flag that tells the engine to create new `token_id` values for each output row, with `parent_token_id` linking back to the original. This enables audit lineage tracking through deaggregation. JSONExplode is the canonical example of a token-creating transform.

### [134-142] Correct Tier 2 type enforcement

The `isinstance(array_value, list)` check explicitly rejects strings and dicts which are iterable but would produce garbage output. The TypeError is correct -- wrong types in Tier 2 data are upstream bugs.

### [138-142] TypeError message is informative

The error message includes the actual type name and directs the developer to check upstream validation. This follows good practice for system-owned code errors.

### [146] Dict comprehension creates correct base

The `{k: v for k, v in row_dict.items() if k != self._array_field}` correctly removes the array field from the base output. Each output row will NOT contain the original array, only the exploded element.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Use `copy.deepcopy(base)` for each output row instead of `base.copy()` to prevent cross-row mutation of nested fields. (2) Deep-copy array elements if they are mutable (dicts/lists) to prevent downstream mutation from corrupting other rows. (3) Document the empty-array behavior explicitly since it changes the output cardinality from multi to single.
**Confidence:** HIGH -- The shallow copy issue is a clear data integrity risk that will manifest whenever array elements are dicts (the primary use case per the docstring example).
