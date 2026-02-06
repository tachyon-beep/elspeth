# Analysis: src/elspeth/plugins/transforms/batch_replicate.py

**Lines:** 194
**Role:** Batch-aware deaggregation transform that replicates rows based on a per-row "copies" field. Takes N input rows and produces M output rows (M >= N). Uses `is_batch_aware=True` to receive rows in batches and `success_multi()` to return expanded output.
**Key dependencies:** BaseTransform, TransformDataConfig, SchemaConfig, SchemaContract, FieldContract, PipelineRow, TransformResult, create_schema_from_config
**Analysis depth:** FULL

## Summary

The file is well-structured and follows ELSPETH's three-tier trust model correctly. The main concerns are: (1) a trust model inconsistency where `raw_copies < 1` raises ValueError (treating it as a system bug) when it should arguably be a Tier 2 row-value error routed via TransformResult.error, (2) the contract builds `python_type=object` for all fields which loses type fidelity in the audit trail, and (3) the `to_dict()` shallow copy means nested mutable structures in the original row could be mutated by later copies. Overall the code is sound for its intended purpose.

## Critical Findings

### [148-152] ValueError for negative copies treats row data as a system bug

**What:** When `raw_copies < 1`, the transform raises `ValueError`. This is a hard crash that kills the entire batch, not just the one bad row.

**Why it matters:** The copies value is Tier 2 pipeline data -- it has been type-validated (int) but the VALUE `0` or `-1` is a legitimate operational failure case, like division-by-zero. Per CLAUDE.md's "Operation Wrapping Rules", operations on row field values that can fail should be wrapped and produce `TransformResult.error()`. A single row with `copies=0` in a batch of 1000 rows will crash the entire batch, losing all 999 valid rows.

**Evidence:**
```python
if raw_copies < 1:
    raise ValueError(
        f"Field '{self._copies_field}' must be >= 1, got {raw_copies}. "
        f"This indicates invalid data - check source validation."
    )
```
The error message itself says "invalid data" -- this is a data quality issue, not a code bug. Yet it raises an exception instead of routing the row to an error sink. The `BatchReplicateConfig` inherits from `TransformDataConfig` which provides `on_error`, and `self._on_error` is stored at line 90, but never used.

Contrast with the isinstance check on line 141, which correctly raises TypeError because wrong types = upstream bug. But wrong VALUES = row-level error that should be quarantined.

### [159] Shallow copy via to_dict() creates shared mutable references across copies

**What:** `row.to_dict()` produces a shallow copy. When the row contains nested mutable objects (dicts, lists), all copies of that row share references to the same nested objects.

**Why it matters:** If a downstream transform mutates a nested field in copy 0, copies 1 through N-1 will see the mutation. This creates phantom data corruption that is extremely difficult to debug. For example:

```python
# Row has {"metadata": {"source": "csv"}, "copies": 3}
# After replication, all 3 output rows share the SAME metadata dict
# If downstream modifies output_rows[0]["metadata"]["processed"] = True
# output_rows[1]["metadata"]["processed"] is ALSO True
```

**Evidence:**
```python
output = row.to_dict()  # Shallow copy preserves original data
```
The comment says "preserves original data" but `to_dict()` returns `dict(self._data)` which is a shallow copy of `MappingProxyType`. For rows with nested structures (common in real pipelines), all copies share nested references.

## Warnings

### [121-127] Empty batch returns single row with fabricated schema

**What:** An empty batch returns `TransformResult.success({"batch_empty": True}, ...)` -- a single row with a completely fabricated field. No contract is provided (contract defaults to None).

**Why it matters:** The comment says "should not happen in normal operation" but if it does, the output row has no relationship to the expected output schema. The downstream transform or sink will receive a row with only `batch_empty: True` and no data fields. This will likely cause failures downstream, but the failure will be attributed to the wrong transform. Additionally, missing `contract=` means `to_pipeline_row()` would fail if the engine tries to convert it.

### [164-180] Contract built from first row only -- heterogeneous batches not detected

**What:** The output contract is built from `output_rows[0]`'s keys. If different input rows have different field sets (FLEXIBLE/OBSERVED schema), later output rows may have different fields than the first, but the contract won't reflect this.

**Why it matters:** Unlike JSONExplode (which validates homogeneity at line 188-197), BatchReplicate does not check that all output rows have the same keys. If input rows have varying fields (valid in OBSERVED mode), the contract built from row 0 will not match rows from different input rows. This creates a contract that lies about the output shape.

### [171] python_type=object loses type information

**What:** All fields in the output contract are typed as `object` (the "any" type).

**Why it matters:** This means the contract carries zero type information to downstream transforms and the audit trail. While OBSERVED mode is inherently dynamic, the actual values in the output rows DO have concrete types that could be inferred (like `propagate_contract` and `narrow_contract_to_output` do in other transforms). The batch_stats transform has the same issue. This is not incorrect, but it degrades audit trail quality.

## Observations

### [109] type: ignore[override] comment for batch signature

The `process()` method takes `list[PipelineRow]` instead of the base class `PipelineRow`. This is documented with a type ignore comment and is the expected pattern for `is_batch_aware=True` transforms. The engine dispatches correctly based on the `is_batch_aware` flag.

### [90] _on_error is stored but never used

`self._on_error = cfg.on_error` is stored from config but never referenced in `process()`. If this transform returned `TransformResult.error()` for value-level issues (as recommended in the critical finding above), this field would be needed by the engine to route errored rows. Currently it is dead code.

### [82] is_batch_aware = True is correctly set

This is critical for the engine to know it should buffer rows and pass a list. Correctly implemented.

### [85] creates_tokens is not set (defaults to False)

For a deaggregation transform, `creates_tokens` should arguably be True (like JSONExplode). However, the YAML example shows `output_mode: transform` which the engine uses to determine token creation. This appears to be handled at the aggregation/engine level rather than via the `creates_tokens` flag, so it may be correct but worth verifying.

## Verdict

**Status:** NEEDS_ATTENTION
**Recommended action:** (1) Change `raw_copies < 1` from raising ValueError to returning TransformResult.error() per trust model -- this is row data, not a code bug. (2) Use `copy.deepcopy()` instead of `row.to_dict()` for the output rows to prevent shared mutable references. (3) Add schema homogeneity validation like JSONExplode does. (4) Consider whether `_on_error` should be wired up.
**Confidence:** HIGH -- The shallow copy and ValueError issues are clear trust model violations that can cause production incidents.
