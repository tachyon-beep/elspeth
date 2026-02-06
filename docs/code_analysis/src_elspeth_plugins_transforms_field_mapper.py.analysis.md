# Analysis: src/elspeth/plugins/transforms/field_mapper.py

**Lines:** 157
**Role:** Core data transformation plugin that renames, reorders, and selects fields from pipeline rows. Used in nearly every pipeline. Supports nested field extraction via dot notation, strict/non-strict modes, and select_only mode for field subsetting.
**Key dependencies:** BaseTransform, TransformDataConfig, SchemaConfig, PipelineRow, TransformResult, create_schema_from_config, contract_propagation.narrow_contract_to_output, get_nested_field, MISSING sentinel
**Analysis depth:** FULL

## Summary

FieldMapper is the cleanest of the five transforms in this batch. The code is well-structured, follows trust model conventions, and handles edge cases thoughtfully. The primary concerns are: (1) a `copy.deepcopy()` call that is correct but expensive for large rows, and (2) the interaction between nested field extraction and the `del output[source]` cleanup logic has a subtle edge case. No critical findings.

## Critical Findings

None.

## Warnings

### [110] deepcopy for non-select_only mode is correct but has O(n) performance implications

**What:** When `select_only=False`, the entire row is deep-copied:
```python
output = copy.deepcopy(row_dict)
```

**Why it matters:** `deepcopy` is expensive, especially for rows with nested structures (JSON objects, lists of dicts). For pipelines processing millions of rows, this becomes a significant CPU bottleneck. However, this is the CORRECT approach (unlike batch_replicate's shallow copy) because the transform mutates the output dict (deleting old keys, adding new keys). Using shallow copy would risk corrupting the original PipelineRow's data through the MappingProxyType.

This is not a bug -- it is a performance characteristic to be aware of. If profiling shows this is a bottleneck, the deepcopy could be replaced with a shallow copy + selective deep copy of only the fields being renamed, since the unmapped fields are passed through unmodified.

### [123-125] Nested field extraction does not remove the top-level nested key

**What:** When a mapping uses dot notation like `{"meta.source": "origin"}`, the code extracts the nested value but only attempts to delete `source` from output (which doesn't exist as a top-level key, so the `if` check prevents the KeyError). The original `meta` dict remains in the output.

**Why it matters:** If a user configures `{"meta.source": "origin"}` expecting the `meta` object to be cleaned up, they'll get both `meta` (with all its fields including `source`) AND `origin` in the output. This is not strictly a bug -- the docstring doesn't promise nested key removal -- but it is surprising behavior. The `not self._select_only and "." not in source` guard explicitly skips nested paths:

```python
if not self._select_only and "." not in source and source in output:
    del output[source]
```

This means dot-notation mappings never remove the source, only flat renames do. This is intentional but worth documenting more explicitly.

### [130-137] Field change tracking re-traverses nested paths

**What:** The tracking loop at lines 130-137 calls `get_nested_field()` again for every mapping entry to determine if the source field existed:

```python
for source, target in self._mapping.items():
    if get_nested_field(row_dict, source) is not MISSING:
        if target in row_dict:
            fields_modified.append(target)
        else:
            fields_added.append(target)
```

**Why it matters:** This is redundant work -- the same traversal was already done in the mapping loop at line 114. For large mappings with deep nesting, this doubles the traversal cost. Additionally, the `fields_modified` vs `fields_added` classification has a subtle issue: it checks `if target in row_dict` (the original input), but the target is a new key name. If the target happens to also exist as a key in the original row (e.g., renaming `a` to `b` when `b` already exists), it classifies it as "modified" which is correct. But if using `select_only=True`, `row_dict` still contains the original keys even though the output dict is empty -- the classification is based on the input shape, not the output shape.

## Observations

### [9] import copy is used correctly

Unlike batch_replicate and json_explode which use shallow copies, field_mapper correctly uses `copy.deepcopy()` for the non-select_only case. This prevents mutation of the original PipelineRow data.

### [103-104] Optional input validation follows trust model

The `validate_input` flag is opt-in and only works with non-observed schemas. When enabled, it uses the Pydantic schema to validate the input row, crashing on type mismatches (correct for Tier 2 data). This is a good diagnostic tool.

### [140-143] Contract propagation via narrow_contract_to_output

The field mapper correctly uses `narrow_contract_to_output` which handles both field removal and field addition in the contract. This preserves original names for fields that survive the mapping and infers types for new fields. This is the correct contract propagation pattern for shape-changing transforms.

### [116-121] MISSING sentinel usage is correct

The MISSING sentinel properly distinguishes "field not present" from "field is None". In non-strict mode, missing source fields are silently skipped. In strict mode, they produce `TransformResult.error()`. This correctly treats missing fields in user data as a row-level error (not a crash) when strict mode is enabled.

### [62] _on_error is stored and IS used (via TransformResult.error in strict mode)

Unlike batch_replicate and batch_stats, field_mapper actually has a code path that returns `TransformResult.error()` (line 118-120, strict mode with missing field). The engine uses `_on_error` to route these error results. This is correct.

## Verdict

**Status:** SOUND
**Recommended action:** No changes required. Minor documentation improvement for nested field behavior would help users. The deepcopy performance characteristic is worth noting in operational documentation but is the correct choice.
**Confidence:** HIGH -- This is a mature, well-tested transform with correct trust model compliance. The edge cases are handled properly or are documented behavior.
